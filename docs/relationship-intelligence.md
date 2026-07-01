# Relationship Intelligence

Relationship Intelligence turns indexed knowledge into an investment-banking workspace for clients, investors, people, deals, interactions, evidence, and follow-up actions.

The feature is additive to the existing RAG console. Document Directory, Data Hub, Chat, ingestion, MCP connectors, Telegram ingestion, and company evidence continue to work as before.

## What It Extracts

After a document completes ingestion, the pipeline runs a soft-fail relationship intelligence pass. It looks for:

- Clients and prospective clients.
- Investors, funds, partners, and contact domains.
- People mentioned as founders, management, attendees, or contacts.
- Meeting-note interactions from Granola, Telegram, and uploaded notes.
- Deal signals such as fundraises, M&A, sell-side, buy-side, mandates, stages, and amounts.
- Follow-ups, todos, next steps, and action items.

Each generated record stores evidence excerpts, source type, source URL when available, and document or connector references. The extractor is intentionally tolerant: if relationship extraction fails, ingestion continues and the pipeline records a warning.

## Granola MCP

Data Hub includes a Granola MCP preset using:

```text
https://mcp.granola.ai/mcp
```

Granola MCP uses browser OAuth per user. There is no service-account or API-key authentication mode for MCP, so each banker must authenticate their own Granola access in an MCP-capable client or provide a valid OAuth bearer context through the connector flow when supported.

The preset includes a `sync_tool_calls` entry that asks Granola for recent client, investor, founder, decision, next-step, and action-item context. When the MCP call succeeds, the result is saved as an indexed connector document, then the normal RAG pipeline prepares relationship intelligence from it.

For organization-wide scheduled imports, use Granola's API integration path when available rather than MCP.

## API Surface

- `GET /api/relationships/summary`
- `GET /api/relationships/entities`
- `GET /api/relationships/entities/{entity_id}`
- `GET /api/relationships/interactions`
- `GET /api/relationships/deals`
- `GET /api/relationships/action-items`
- `POST /api/relationships/action-items`
- `PATCH /api/relationships/action-items/{action_item_id}`
- `POST /api/relationships/rescan`

`/api/relationships/rescan` requires ingestion permission and reprocesses already-derived document text into relationship records.
