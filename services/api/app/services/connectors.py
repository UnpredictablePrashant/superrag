from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID, uuid4

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, sha256_bytes
from app.models.entities import (
    CompanyEvidence,
    CompanyProfile,
    ConnectorConnection,
    ConnectorItem,
    ConnectorRun,
    Document,
    DocumentAccessRule,
)
from app.services.audit import write_audit_log
from app.services.document_ingestion import (
    create_uploaded_document_from_bytes,
    queue_pipeline_for_documents,
)
from app.services.retrieval import Candidate


@dataclass(frozen=True)
class ConnectorDocument:
    external_id: str
    title: str
    source_url: str | None
    filename: str
    content_type: str
    data: bytes
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MCPStdioServerConfig:
    name: str | None
    command: list[str]
    env: dict[str, str]


class ConnectorAdapter:
    def __init__(self, connection: ConnectorConnection):
        self.connection = connection

    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def discover(self) -> dict[str, Any]:
        raise NotImplementedError

    def fetch(self, options: dict[str, Any]) -> list[ConnectorDocument]:
        raise NotImplementedError

    def normalize(self, payload: Any, source_url: str | None = None) -> ConnectorDocument:
        raise NotImplementedError


class WebConnector(ConnectorAdapter):
    def test_connection(self) -> dict[str, Any]:
        urls = _seed_urls(self.connection, {})
        if not urls:
            return {"status": "error", "message": "Add at least one seed URL."}
        document = self._fetch_url(urls[0])
        return {
            "status": "ok",
            "title": document.title,
            "source_url": document.source_url,
            "bytes": len(document.data),
        }

    def discover(self) -> dict[str, Any]:
        urls = _seed_urls(self.connection, {})
        return {"status": "ok", "seed_urls": urls, "allowlist_domains": _allowlist_domains(self.connection, urls)}

    def fetch(self, options: dict[str, Any]) -> list[ConnectorDocument]:
        seeds = _seed_urls(self.connection, options)
        if not seeds:
            raise ValueError("Add at least one seed URL before syncing.")
        allowlist = _allowlist_domains(self.connection, seeds)
        max_pages = int(options.get("max_pages") or self.connection.config.get("max_pages") or settings.connector_max_pages)
        max_depth = int(options.get("max_depth") or self.connection.config.get("max_depth") or 0)
        queue: list[tuple[str, int]] = [(url, 0) for url in seeds]
        seen: set[str] = set()
        documents: list[ConnectorDocument] = []
        while queue and len(documents) < max_pages:
            url, depth = queue.pop(0)
            normalized_url = _normalize_url(url)
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            if not _url_allowed(normalized_url, allowlist, bool(self.connection.config.get("allow_private_network"))):
                continue
            try:
                document = self._fetch_url(normalized_url)
            except Exception:
                continue
            documents.append(document)
            if depth < max_depth and document.content_type.startswith("text/html"):
                for link in _extract_links(document.data, normalized_url):
                    if len(queue) + len(documents) >= max_pages:
                        break
                    if link not in seen and _url_allowed(link, allowlist, bool(self.connection.config.get("allow_private_network"))):
                        queue.append((link, depth + 1))
        return documents

    def normalize(self, payload: Any, source_url: str | None = None) -> ConnectorDocument:
        data = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        return normalize_web_document(data, source_url or "web://inline")

    def _fetch_url(self, url: str) -> ConnectorDocument:
        with httpx.Client(timeout=settings.connector_request_timeout_seconds, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "RAG Console Connector/0.1"})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "text/html").split(";")[0].strip() or "text/html"
        return normalize_web_document(response.content, str(response.url), content_type)


class MCPConnector(ConnectorAdapter):
    def test_connection(self) -> dict[str, Any]:
        discovered = self.discover()
        return {
            "status": "ok",
            "tools": len(discovered.get("tools", [])),
            "resources": len(discovered.get("resources", [])),
        }

    def discover(self) -> dict[str, Any]:
        tools = _mcp_request(self.connection, "tools/list", {})
        resources = _mcp_request(self.connection, "resources/list", {}, allow_failure=True)
        return {
            "status": "ok",
            "tools": tools.get("tools", []),
            "resources": resources.get("resources", []),
        }

    def fetch(self, options: dict[str, Any]) -> list[ConnectorDocument]:
        resource_uris = [
            str(uri).strip()
            for uri in options.get("resource_uris", self.connection.config.get("resource_uris", []))
            if str(uri).strip()
        ]
        documents: list[ConnectorDocument] = []
        for uri in resource_uris:
            result = _mcp_request(self.connection, "resources/read", {"uri": uri})
            text = _mcp_result_text(result)
            if text.strip():
                documents.append(self.normalize(text, uri))
        return documents

    def normalize(self, payload: Any, source_url: str | None = None) -> ConnectorDocument:
        text = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
        uri = source_url or "mcp://resource"
        title = _title_from_url(uri) or "MCP resource"
        return ConnectorDocument(
            external_id=uri,
            title=title,
            source_url=uri,
            filename=f"{_safe_filename(title)}.md",
            content_type="text/markdown",
            data=text.encode("utf-8"),
            metadata={"source_type": "mcp_resource"},
        )

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _mcp_request(self.connection, "tools/call", {"name": tool_name, "arguments": arguments})


def get_connector_adapter(connection: ConnectorConnection) -> ConnectorAdapter:
    if connection.kind == "web":
        return WebConnector(connection)
    if connection.kind == "mcp":
        return MCPConnector(connection)
    raise ValueError(f"Unsupported connector kind: {connection.kind}")


def sync_connector_connection(
    db: Session,
    *,
    connection_id: UUID,
    requested_by_user_id: UUID,
    options: dict[str, Any],
    run_id: UUID | None = None,
) -> ConnectorRun:
    connection = db.get(ConnectorConnection, connection_id)
    if not connection or connection.deleted_at is not None or not connection.is_enabled:
        raise ValueError("Connector connection is not available.")
    run = db.get(ConnectorRun, run_id) if run_id else None
    if not run:
        run = ConnectorRun(
            organization_id=connection.organization_id,
            connector_connection_id=connection.id,
            requested_by_user_id=requested_by_user_id,
            status="queued",
            options=options,
        )
        db.add(run)
        db.flush()
    run.status = "running"
    run.started_at = datetime.now(UTC)
    run.options = options
    db.commit()

    try:
        adapter = get_connector_adapter(connection)
        fetched = adapter.fetch(options)
        run.total_items = len(fetched)
        db.commit()
        document_ids: list[UUID] = []
        knowledge_base_id = UUID(str(options["knowledge_base_id"]))
        for document in fetched:
            item, created_document = _upsert_connector_document(
                db,
                connection=connection,
                run=run,
                document=document,
                knowledge_base_id=knowledge_base_id,
                requested_by_user_id=requested_by_user_id,
                share_with_organization=bool(options.get("share_with_organization")),
            )
            if created_document:
                document_ids.append(created_document.id)
                _upsert_company_profile_from_item(db, connection, item, created_document, document, options)
            run.processed_items += 1
            db.commit()
        if document_ids:
            queue_pipeline_for_documents(
                db,
                organization_id=connection.organization_id,
                knowledge_base_id=knowledge_base_id,
                document_ids=document_ids,
                cleanup_profile_id=_uuid_or_none(options.get("cleanup_profile_id")),
                chunking_profile_id=_uuid_or_none(options.get("chunking_profile_id")),
                embedding_profile_id=_uuid_or_none(options.get("embedding_profile_id")),
                retrieval_index_config={"max_chunks": 8, "rrf_constant": 60, "source": "connector_sync"},
            )
        connection.last_synced_at = datetime.now(UTC)
        connection.status = "ok"
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.logs = [
            *run.logs[-100:],
            {"message": f"Synced {run.processed_items}/{run.total_items} item(s).", "at": datetime.now(UTC).isoformat()},
        ]
        db.commit()
        return run
    except Exception as exc:
        connection.status = "error"
        run.status = "failed"
        run.error = str(exc)[:1000]
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise


def live_connector_candidates(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    query: str,
    use_web_search: bool,
    use_mcp_tools: bool,
    connector_connection_ids: list[str] | None,
    chat_session_id: UUID | None = None,
) -> list[Candidate]:
    if not use_web_search and not use_mcp_tools:
        return []
    connections = _accessible_mcp_connections(db, organization_id, user_id, connector_connection_ids)
    candidates: list[Candidate] = []
    for connection in connections:
        adapter = MCPConnector(connection)
        try:
            discovered = adapter.discover()
        except Exception as exc:
            write_audit_log(
                db,
                organization_id=organization_id,
                actor_user_id=user_id,
                action="connector.live_tool_discovery_failed",
                resource_type="connector_connection",
                resource_id=str(connection.id),
                metadata={"error": str(exc)[:500], "chat_session_id": str(chat_session_id) if chat_session_id else None},
            )
            continue
        for tool in discovered.get("tools", []):
            if not should_use_mcp_tool(tool, connection.config, use_web_search, use_mcp_tools):
                continue
            if not is_mcp_tool_read_only(tool, connection.config):
                write_audit_log(
                    db,
                    organization_id=organization_id,
                    actor_user_id=user_id,
                    action="connector.live_tool_skipped_non_read_only",
                    resource_type="connector_connection",
                    resource_id=str(connection.id),
                    metadata={"tool_name": tool.get("name"), "chat_session_id": str(chat_session_id) if chat_session_id else None},
                )
                continue
            tool_name = str(tool.get("name") or "")
            if not tool_name:
                continue
            arguments = select_mcp_tool_arguments(tool, query)
            try:
                result = adapter.call_tool(tool_name, arguments)
            except Exception as exc:
                write_audit_log(
                    db,
                    organization_id=organization_id,
                    actor_user_id=user_id,
                    action="connector.live_tool_call_failed",
                    resource_type="connector_connection",
                    resource_id=str(connection.id),
                    metadata={"tool_name": tool_name, "error": str(exc)[:500]},
                )
                continue
            text = _mcp_result_text(result).strip()
            if not text:
                continue
            source_url = _first_url(text)
            source_type = "Live Web" if _tool_has_tag(tool, connection.config, "web_search") else "MCP"
            candidates.append(
                Candidate(
                    chunk_id=f"live:{connection.id}:{tool_name}:{uuid4()}",
                    document_id=f"live:{connection.id}",
                    document_name=f"{connection.name} / {tool_name}",
                    text=text[:6000],
                    score=0.72,
                    source="live_mcp",
                    metadata={
                        "source_type": source_type,
                        "source_url": source_url,
                        "connector_connection_id": str(connection.id),
                        "tool_name": tool_name,
                        "live": True,
                    },
                )
            )
            write_audit_log(
                db,
                organization_id=organization_id,
                actor_user_id=user_id,
                action="connector.live_tool_call",
                resource_type="connector_connection",
                resource_id=str(connection.id),
                metadata={"tool_name": tool_name, "chat_session_id": str(chat_session_id) if chat_session_id else None},
            )
    return candidates


def save_live_result_as_document(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    knowledge_base_id: UUID,
    title: str,
    content: str,
    source_url: str | None,
    source_type: str,
    confidentiality,
    tags: list[str],
    share_with_organization: bool,
    custom_metadata: dict[str, Any],
) -> Document:
    filename = f"{_safe_filename(title)}.md"
    document = create_uploaded_document_from_bytes(
        db,
        organization_id=organization_id,
        knowledge_base_id=knowledge_base_id,
        filename=filename,
        data=content.encode("utf-8"),
        content_type="text/markdown",
        uploaded_by_user_id=user_id,
        tags=tags,
        confidentiality=confidentiality,
        source_url=source_url,
        custom_metadata={**custom_metadata, "source_type": source_type, "saved_from_live_result": True},
    )
    if not share_with_organization:
        db.add(
            DocumentAccessRule(
                organization_id=organization_id,
                document_id=document.id,
                principal_type="user",
                principal_id=str(user_id),
                permission="read",
            )
        )
    queue_pipeline_for_documents(
        db,
        organization_id=organization_id,
        knowledge_base_id=knowledge_base_id,
        document_ids=[document.id],
        retrieval_index_config={"max_chunks": 8, "rrf_constant": 60, "source": "saved_live_result"},
    )
    return document


def normalize_web_document(
    data: bytes,
    source_url: str,
    content_type: str = "text/html",
) -> ConnectorDocument:
    title = _title_from_url(source_url) or "Web page"
    if content_type.startswith("text/html"):
        soup = BeautifulSoup(data, "html.parser")
        if soup.title and soup.title.string:
            title = unescape(soup.title.string.strip()) or title
    suffix = ".html" if content_type.startswith("text/html") else ".txt"
    return ConnectorDocument(
        external_id=_normalize_url(source_url),
        title=title[:500],
        source_url=source_url,
        filename=f"{_safe_filename(title)}{suffix}",
        content_type=content_type,
        data=data,
        metadata={"source_type": "synced_web", "content_type": content_type},
    )


def select_mcp_tool_arguments(tool: dict[str, Any], query: str) -> dict[str, Any]:
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    if isinstance(properties, dict):
        for key in ("query", "q", "search", "question", "text"):
            if key in properties:
                return {key: query}
    return {"query": query}


def should_use_mcp_tool(
    tool: dict[str, Any],
    connection_config: dict[str, Any],
    use_web_search: bool,
    use_mcp_tools: bool,
) -> bool:
    name = str(tool.get("name") or "").lower()
    enabled_names = {str(value).lower() for value in connection_config.get("enabled_tool_names", [])}
    if enabled_names and name not in enabled_names:
        return False
    if use_web_search and _tool_has_tag(tool, connection_config, "web_search"):
        return True
    return bool(
        use_mcp_tools
        and (_tool_has_tag(tool, connection_config, "knowledge_lookup") or _looks_like_lookup_tool(name))
    )


def is_mcp_tool_read_only(tool: dict[str, Any], connection_config: dict[str, Any] | None = None) -> bool:
    connection_config = connection_config or {}
    if connection_config.get("allow_write_tools") is True:
        return False
    annotations = tool.get("annotations") or {}
    if annotations.get("destructiveHint") or annotations.get("destructive_hint"):
        return False
    if annotations.get("readOnlyHint") is True or annotations.get("read_only_hint") is True:
        return True
    name = str(tool.get("name") or "").lower()
    return not re.search(r"(^|[_\-\s])(create|delete|remove|update|write|send|post|patch|put|mutate|insert)($|[_\-\s])", name)


def _upsert_connector_document(
    db: Session,
    *,
    connection: ConnectorConnection,
    run: ConnectorRun,
    document: ConnectorDocument,
    knowledge_base_id: UUID,
    requested_by_user_id: UUID,
    share_with_organization: bool,
) -> tuple[ConnectorItem, Document | None]:
    checksum = sha256_bytes(document.data)
    item = db.scalar(
        select(ConnectorItem).where(
            ConnectorItem.connector_connection_id == connection.id,
            ConnectorItem.external_id == document.external_id,
        )
    )
    if item and item.checksum == checksum and item.document_id:
        item.connector_run_id = run.id
        item.status = "unchanged"
        item.metadata_json = {**(item.metadata_json or {}), **document.metadata}
        return item, None
    created = create_uploaded_document_from_bytes(
        db,
        organization_id=connection.organization_id,
        knowledge_base_id=knowledge_base_id,
        filename=document.filename,
        data=document.data,
        content_type=document.content_type,
        uploaded_by_user_id=requested_by_user_id,
        tags=list({*connection.config.get("tags", []), *document.metadata.get("tags", [])}),
        source_url=document.source_url,
        custom_metadata={
            **document.metadata,
            "connector_connection_id": str(connection.id),
            "connector_kind": connection.kind,
            "connector_scope": connection.scope,
            "external_id": document.external_id,
        },
    )
    if connection.scope == "user" and not share_with_organization:
        db.add(
            DocumentAccessRule(
                organization_id=connection.organization_id,
                document_id=created.id,
                principal_type="user",
                principal_id=str(requested_by_user_id),
                permission="read",
            )
        )
    if not item:
        item = ConnectorItem(
            organization_id=connection.organization_id,
            connector_connection_id=connection.id,
            external_id=document.external_id,
            title=document.title,
        )
        db.add(item)
    item.connector_run_id = run.id
    item.document_id = created.id
    item.title = document.title
    item.source_url = document.source_url
    item.content_type = document.content_type
    item.checksum = checksum
    item.status = "synced"
    item.metadata_json = document.metadata
    db.flush()
    return item, created


def _upsert_company_profile_from_item(
    db: Session,
    connection: ConnectorConnection,
    item: ConnectorItem,
    document: Document,
    connector_document: ConnectorDocument,
    options: dict[str, Any],
) -> None:
    company_name = (
        options.get("company_name")
        or connection.config.get("company_name")
        or connector_document.metadata.get("company_name")
    )
    if not company_name:
        return
    normalized = _normalize_company_name(str(company_name))
    profile = db.scalar(
        select(CompanyProfile).where(
            CompanyProfile.organization_id == connection.organization_id,
            CompanyProfile.normalized_name == normalized,
            CompanyProfile.deleted_at.is_(None),
        )
    )
    if not profile:
        profile = CompanyProfile(
            organization_id=connection.organization_id,
            name=str(company_name),
            normalized_name=normalized,
            website_url=connector_document.source_url,
            metadata_json={"created_from_connector_id": str(connection.id)},
        )
        db.add(profile)
        db.flush()
    if not profile.website_url and connector_document.source_url:
        profile.website_url = connector_document.source_url
    if not profile.description:
        profile.description = _text_excerpt(connector_document.data, connector_document.content_type, 700)
    db.add(
        CompanyEvidence(
            organization_id=connection.organization_id,
            company_profile_id=profile.id,
            document_id=document.id,
            connector_item_id=item.id,
            field_name="description",
            source_type=connector_document.metadata.get("source_type", connection.kind),
            source_url=connector_document.source_url,
            excerpt=_text_excerpt(connector_document.data, connector_document.content_type, 500),
            confidence=0.6,
            metadata_json={"connector_connection_id": str(connection.id)},
        )
    )


def _mcp_request(
    connection: ConnectorConnection,
    method: str,
    params: dict[str, Any],
    *,
    allow_failure: bool = False,
) -> dict[str, Any]:
    transport = str(
        connection.config.get("transport")
        or ("stdio" if isinstance(connection.config.get("mcpServers"), dict) else "streamable_http")
    )
    try:
        if transport == "stdio":
            return _mcp_stdio_request(connection, method, params)
        return _mcp_http_request(connection, method, params)
    except Exception:
        if allow_failure:
            return {}
        raise


def _mcp_http_request(connection: ConnectorConnection, method: str, params: dict[str, Any]) -> dict[str, Any]:
    if not connection.base_url:
        raise ValueError("MCP Streamable HTTP endpoint is required.")
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **{str(k): str(v) for k, v in (connection.config.get("headers") or {}).items()},
    }
    if connection.encrypted_secret:
        headers.setdefault("Authorization", f"Bearer {decrypt_secret(connection.encrypted_secret)}")
    with httpx.Client(timeout=settings.connector_request_timeout_seconds) as client:
        session_id: str | None = None
        if not connection.config.get("skip_initialize"):
            initialized, session_id = _mcp_http_jsonrpc(
                client,
                connection.base_url,
                headers,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "rag-console", "version": "0.1.0"},
                },
                1,
            )
            _ = initialized
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            client.post(
                connection.base_url,
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )
        result, _ = _mcp_http_jsonrpc(client, connection.base_url, headers, method, params, 2)
        return result


def _mcp_http_jsonrpc(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    method: str,
    params: dict[str, Any],
    request_id: int,
) -> tuple[dict[str, Any], str | None]:
    response = client.post(
        url,
        headers=headers,
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
    )
    response.raise_for_status()
    payload = _parse_json_or_sse(response)
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    return dict(payload.get("result") or {}), response.headers.get("Mcp-Session-Id")


def _mcp_stdio_request(connection: ConnectorConnection, method: str, params: dict[str, Any]) -> dict[str, Any]:
    server_config = _mcp_stdio_server_config(connection)
    _validate_stdio_command(server_config.command)
    payloads = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "rag-console", "version": "0.1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
    ]
    env = os.environ.copy()
    env.update(server_config.env)
    process = subprocess.Popen(
        server_config.command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        shell=False,
    )
    request_body = "".join(json.dumps(payload) + "\n" for payload in payloads)
    try:
        stdout, stderr = process.communicate(request_body, timeout=settings.connector_request_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise TimeoutError("MCP stdio request timed out.") from exc
    for line in stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("id") == 2:
            if payload.get("error"):
                raise ValueError(str(payload["error"]))
            return dict(payload.get("result") or {})
    raise ValueError((stderr or "MCP stdio server returned no response.").strip()[:500])


def _mcp_stdio_server_config(connection: ConnectorConnection) -> MCPStdioServerConfig:
    config = connection.config or {}
    root_env = _mcp_env(config.get("env") or {})
    if isinstance(config.get("command"), list):
        command = config["command"]
        if not command or not all(isinstance(part, str) and part.strip() for part in command):
            raise ValueError("MCP stdio transport requires config.command as a string array.")
        return MCPStdioServerConfig(name=None, command=command, env=root_env)
    if isinstance(config.get("command"), str):
        return _mcp_stdio_from_server_object(config, name=str(config.get("name") or "") or None, root_env={})

    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError("MCP stdio transport requires config.mcpServers or config.command.")
    selected_name = str(config.get("mcp_server_name") or config.get("server_name") or "").strip()
    if selected_name:
        selected = servers.get(selected_name)
        if not isinstance(selected, dict):
            raise ValueError(f"MCP server {selected_name} was not found in config.mcpServers.")
        return _mcp_stdio_from_server_object(selected, selected_name, root_env)
    for name, value in servers.items():
        if isinstance(value, dict) and value.get("disabled") is not True:
            return _mcp_stdio_from_server_object(value, str(name), root_env)
    raise ValueError("Cursor-style MCP config contains no enabled mcpServers entry.")


def _mcp_stdio_from_server_object(
    server: dict[str, Any],
    name: str | None,
    root_env: dict[str, str],
) -> MCPStdioServerConfig:
    if server.get("disabled") is True:
        raise ValueError(f"MCP server {name or 'stdio'} is disabled.")
    command = server.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Cursor-style MCP server config requires a command string.")
    args = server.get("args") or []
    if not isinstance(args, list) or not all(isinstance(part, str) for part in args):
        raise ValueError("Cursor-style MCP server args must be a string array.")
    return MCPStdioServerConfig(
        name=name,
        command=[command, *args],
        env={**root_env, **_mcp_env(server.get("env") or {})},
    )


def _mcp_env(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("MCP stdio env must be an object.")
    return {str(key): str(env_value) for key, env_value in value.items()}


def _validate_stdio_command(command: list[str]) -> None:
    if settings.app_env in {"local", "test"}:
        return
    allowed = settings.mcp_stdio_allowlist_values
    executable = command[0]
    full = " ".join(command)
    if executable not in allowed and full not in allowed:
        raise ValueError("MCP stdio command is not allowlisted in this environment.")


def _parse_json_or_sse(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data:"):
            data = line.removeprefix("data:").strip()
            if data:
                return json.loads(data)
    return {}


def _mcp_result_text(result: dict[str, Any]) -> str:
    if not result:
        return ""
    content = result.get("content") or result.get("contents") or []
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("text"):
                    parts.append(str(item["text"]))
                elif item.get("uri") and item.get("mimeType"):
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
    if parts:
        return "\n\n".join(parts)
    return json.dumps(result, indent=2, ensure_ascii=False)


def _accessible_mcp_connections(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    connector_connection_ids: list[str] | None,
) -> list[ConnectorConnection]:
    query = select(ConnectorConnection).where(
        ConnectorConnection.organization_id == organization_id,
        ConnectorConnection.kind == "mcp",
        ConnectorConnection.is_enabled.is_(True),
        ConnectorConnection.deleted_at.is_(None),
    )
    if connector_connection_ids:
        parsed = [UUID(str(value)) for value in connector_connection_ids]
        query = query.where(ConnectorConnection.id.in_(parsed))
    connections = list(db.scalars(query))
    return [
        connection
        for connection in connections
        if connection.scope == "organization" or connection.user_id == user_id
    ]


def _tool_has_tag(tool: dict[str, Any], connection_config: dict[str, Any], tag: str) -> bool:
    name = str(tool.get("name") or "").lower()
    tags = {str(value).lower() for value in tool.get("tags", [])}
    configured = connection_config.get("tool_tags", {})
    if isinstance(configured, dict):
        tags.update(str(value).lower() for value in configured.get(name, []))
    description = str(tool.get("description") or "").lower()
    if tag in tags:
        return True
    if tag == "web_search" and ("web" in tags or "search" in name or "web search" in description):
        return True
    return bool(tag == "knowledge_lookup" and ("lookup" in name or "knowledge" in description))


def _looks_like_lookup_tool(name: str) -> bool:
    return bool(re.search(r"(search|lookup|query|retrieve|find|get)", name))


def _seed_urls(connection: ConnectorConnection, options: dict[str, Any]) -> list[str]:
    values = options.get("seed_urls") or connection.config.get("seed_urls") or []
    return [_normalize_url(str(value)) for value in values if str(value).strip()]


def _allowlist_domains(connection: ConnectorConnection, seed_urls: list[str]) -> set[str]:
    configured = {str(value).lower() for value in connection.config.get("allowlist_domains", []) if str(value).strip()}
    if configured:
        return configured
    return {urlparse(url).netloc.lower() for url in seed_urls if urlparse(url).netloc}


def _url_allowed(url: str, allowlist: set[str], allow_private_network: bool) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    if allowlist and host.lower() not in allowlist and parsed.netloc.lower() not in allowlist:
        return False
    return bool(allow_private_network or not _is_private_host(host))


def _is_private_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _normalize_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def _extract_links(data: bytes, base_url: str) -> list[str]:
    soup = BeautifulSoup(data, "html.parser")
    links = []
    for anchor in soup.find_all("a", href=True):
        links.append(_normalize_url(urljoin(base_url, str(anchor["href"]))))
    return links


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (cleaned or "connector-document")[:120]


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").split("/")[-1]
    return unescape(path.replace("-", " ").replace("_", " ")).strip() or parsed.netloc


def _first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s)>\]]+", text)
    return match.group(0).rstrip(".,;") if match else None


def _uuid_or_none(value: Any) -> UUID | None:
    return UUID(str(value)) if value else None


def _normalize_company_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _text_excerpt(data: bytes, content_type: str, limit: int) -> str:
    if content_type.startswith("text/html"):
        soup = BeautifulSoup(data, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "aside"]):
            element.decompose()
        text = " ".join(line.strip() for line in soup.get_text(" ").split() if line.strip())
    else:
        text = data.decode("utf-8", errors="replace")
    return text[:limit]
