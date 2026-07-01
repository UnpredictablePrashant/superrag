from decimal import Decimal

from app.services.chat import (
    ChatCompletionResult,
    ChatModelConfig,
    ChatUsage,
    generate_grounded_answer,
)
from app.services.retrieval import Candidate
from app.services.usage import calculate_chat_cost, pricing_for_model


def test_chat_cost_uses_default_model_pricing() -> None:
    model = ChatModelConfig(provider="OpenAI", model_name="gpt-5.1", api_key="sk-test")
    usage = ChatUsage(input_tokens=1_000_000, output_tokens=500_000, total_tokens=1_500_000, source="provider")

    cost = calculate_chat_cost(model, usage)

    assert cost["cost_usd"] == Decimal("6.250000")
    assert cost["pricing_source"] == "default_pricing"


def test_chat_cost_can_be_overridden_on_model_profile_config() -> None:
    model = ChatModelConfig(
        provider="OpenAI",
        model_name="custom-model",
        config={"pricing": {"input_cost_per_1m": "2.50", "output_cost_per_1m": "9.50"}},
    )

    input_price, output_price, source = pricing_for_model(model)

    assert input_price == Decimal("2.50")
    assert output_price == Decimal("9.50")
    assert source == "model_profile_override"


def test_grounded_answer_carries_provider_usage(monkeypatch) -> None:
    def fake_dispatch(messages, model_config):
        assert model_config.provider == "OpenAI"
        return ChatCompletionResult(
            text="Usage-aware answer [1]",
            usage=ChatUsage(input_tokens=12, output_tokens=4, total_tokens=16, source="provider"),
        )

    monkeypatch.setattr("app.services.chat._dispatch_chat_provider", fake_dispatch)
    answer = generate_grounded_answer(
        "How much did we use?",
        [
            Candidate(
                "chunk-1",
                "doc-1",
                "Usage.pdf",
                "The assistant should report usage.",
                0.9,
                "vector",
                {},
            )
        ],
        ChatModelConfig(provider="OpenAI", model_name="gpt-5.1", api_key="sk-test"),
    )

    assert answer.answer == "Usage-aware answer [1]"
    assert answer.usage is not None
    assert answer.usage.input_tokens == 12
    assert answer.usage.output_tokens == 4
    assert answer.usage.total_tokens == 16
    assert answer.usage.source == "provider"
