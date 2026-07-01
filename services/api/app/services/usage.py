from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import UsageMetric, User
from app.services.chat import ChatModelConfig, ChatUsage

MILLION = Decimal("1000000")

DEFAULT_PRICING_USD_PER_1M: dict[str, dict[str, tuple[Decimal, Decimal]]] = {
    "OpenAI": {
        "gpt-5.5-pro": (Decimal("30.00"), Decimal("180.00")),
        "gpt-5.5": (Decimal("5.00"), Decimal("30.00")),
        "gpt-5.4-pro": (Decimal("30.00"), Decimal("180.00")),
        "gpt-5.4-nano": (Decimal("0.20"), Decimal("1.25")),
        "gpt-5.4-mini": (Decimal("0.75"), Decimal("4.50")),
        "gpt-5.4": (Decimal("2.50"), Decimal("15.00")),
        "gpt-5.3-codex": (Decimal("1.75"), Decimal("14.00")),
        "gpt-5-nano": (Decimal("0.05"), Decimal("0.40")),
        "gpt-5-mini": (Decimal("0.25"), Decimal("2.00")),
        "gpt-5": (Decimal("1.25"), Decimal("10.00")),
        "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
        "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
        "gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
        "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
        "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    },
    "Anthropic": {
        "claude-haiku": (Decimal("0.80"), Decimal("4.00")),
        "claude-sonnet": (Decimal("2.00"), Decimal("10.00")),
        "claude-opus": (Decimal("5.00"), Decimal("25.00")),
    },
    "Google Gemini": {
        "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
        "gemini-2.5-pro": (Decimal("1.25"), Decimal("10.00")),
        "gemini-1.5-flash": (Decimal("0.075"), Decimal("0.30")),
        "gemini-1.5-pro": (Decimal("1.25"), Decimal("5.00")),
    },
    "xAI Grok": {
        "grok-4.3": (Decimal("1.25"), Decimal("2.50")),
        "grok-4": (Decimal("3.00"), Decimal("15.00")),
        "grok-3-mini": (Decimal("0.30"), Decimal("0.50")),
        "grok-3": (Decimal("3.00"), Decimal("15.00")),
    },
}


def record_chat_model_usage(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    chat_session_id: UUID,
    user_message_id: UUID,
    assistant_message_id: UUID,
    retrieval_event_id: UUID,
    model_config: ChatModelConfig,
    usage: ChatUsage,
) -> UsageMetric:
    cost = calculate_chat_cost(model_config, usage)
    metric = UsageMetric(
        organization_id=organization_id,
        metric_name="chat_model.cost_usd",
        metric_value=float(cost["cost_usd"]),
        dimensions={
            "user_id": str(user_id),
            "chat_session_id": str(chat_session_id),
            "user_message_id": str(user_message_id),
            "assistant_message_id": str(assistant_message_id),
            "retrieval_event_id": str(retrieval_event_id),
            "provider": model_config.provider,
            "model": model_config.model_name,
            "model_profile_id": model_config.profile_id,
            "connection_name": model_config.connection_name,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "usage_source": usage.source,
            "input_cost_per_1m": float(cost["input_cost_per_1m"]),
            "output_cost_per_1m": float(cost["output_cost_per_1m"]),
            "pricing_source": cost["pricing_source"],
        },
    )
    db.add(metric)
    return metric


def calculate_chat_cost(model_config: ChatModelConfig, usage: ChatUsage) -> dict[str, Any]:
    input_price, output_price, pricing_source = pricing_for_model(model_config)
    input_cost = Decimal(usage.input_tokens) * input_price / MILLION
    output_cost = Decimal(usage.output_tokens) * output_price / MILLION
    return {
        "cost_usd": input_cost + output_cost,
        "input_cost_per_1m": input_price,
        "output_cost_per_1m": output_price,
        "pricing_source": pricing_source,
    }


def pricing_for_model(model_config: ChatModelConfig) -> tuple[Decimal, Decimal, str]:
    override = ((model_config.config or {}).get("pricing") or {}) if isinstance(model_config.config, dict) else {}
    if isinstance(override, dict):
        input_override = override.get("input_cost_per_1m") or override.get("input_usd_per_1m")
        output_override = override.get("output_cost_per_1m") or override.get("output_usd_per_1m")
        if input_override is not None and output_override is not None:
            return Decimal(str(input_override)), Decimal(str(output_override)), "model_profile_override"
    if model_config.provider == "Local":
        return Decimal("0"), Decimal("0"), "local"
    model_key = model_config.model_name.lower()
    provider_prices = DEFAULT_PRICING_USD_PER_1M.get(model_config.provider, {})
    matches = sorted(provider_prices.items(), key=lambda item: len(item[0]), reverse=True)
    for prefix, prices in matches:
        if model_key.startswith(prefix) or prefix in model_key:
            return prices[0], prices[1], "default_pricing"
    return Decimal("0"), Decimal("0"), "unpriced_model"


def ai_usage_summary(db: Session, organization_id: UUID, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    metrics = list(
        db.scalars(
            select(UsageMetric)
            .where(
                UsageMetric.organization_id == organization_id,
                UsageMetric.metric_name == "chat_model.cost_usd",
                UsageMetric.created_at >= since,
            )
            .order_by(UsageMetric.created_at.desc())
        )
    )
    user_ids = {str(metric.dimensions.get("user_id")) for metric in metrics if metric.dimensions.get("user_id")}
    users = {
        str(user.id): user
        for user in db.scalars(select(User).where(User.id.in_([UUID(user_id) for user_id in user_ids]))).all()
    } if user_ids else {}
    totals = _blank_rollup()
    by_user: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for metric in metrics:
        dimensions = metric.dimensions or {}
        rollup = _metric_rollup(metric)
        _add_rollup(totals, rollup)
        user_id = str(dimensions.get("user_id") or "")
        user = users.get(user_id)
        user_row = by_user.setdefault(
            user_id,
            {
                **_blank_rollup(),
                "user_id": user_id,
                "email": user.email if user else None,
                "full_name": user.full_name if user else None,
            },
        )
        _add_rollup(user_row, rollup)
        provider = str(dimensions.get("provider") or "Unknown")
        model = str(dimensions.get("model") or "Unknown")
        model_key = f"{provider}::{model}"
        model_row = by_model.setdefault(
            model_key,
            {
                **_blank_rollup(),
                "provider": provider,
                "model": model,
                "model_profile_id": dimensions.get("model_profile_id"),
                "pricing_source": dimensions.get("pricing_source"),
                "input_cost_per_1m": float(dimensions.get("input_cost_per_1m") or 0),
                "output_cost_per_1m": float(dimensions.get("output_cost_per_1m") or 0),
            },
        )
        _add_rollup(model_row, rollup)
        if len(events) < 25:
            events.append(
                {
                    "created_at": metric.created_at,
                    "user_id": user_id,
                    "email": user.email if user else None,
                    "provider": provider,
                    "model": model,
                    **rollup,
                }
            )
    return {
        "days": days,
        "totals": totals,
        "by_user": sorted(by_user.values(), key=lambda row: row["cost_usd"], reverse=True),
        "by_model": sorted(by_model.values(), key=lambda row: row["cost_usd"], reverse=True),
        "recent_events": events,
    }


def _metric_rollup(metric: UsageMetric) -> dict[str, Any]:
    dimensions = metric.dimensions or {}
    return {
        "request_count": 1,
        "input_tokens": int(dimensions.get("input_tokens") or 0),
        "output_tokens": int(dimensions.get("output_tokens") or 0),
        "total_tokens": int(dimensions.get("total_tokens") or 0),
        "cost_usd": float(metric.metric_value or 0),
    }


def _blank_rollup() -> dict[str, Any]:
    return {
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    }


def _add_rollup(target: dict[str, Any], value: dict[str, Any]) -> None:
    target["request_count"] += int(value["request_count"])
    target["input_tokens"] += int(value["input_tokens"])
    target["output_tokens"] += int(value["output_tokens"])
    target["total_tokens"] += int(value["total_tokens"])
    target["cost_usd"] += float(value["cost_usd"])
