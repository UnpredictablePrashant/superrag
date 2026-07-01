# Relationship Intelligence

Relationship Intelligence turns indexed knowledge into an investment-banking workspace for clients, investors, people, deals, interactions, evidence, and follow-up actions.

The feature is additive to the existing RAG console. Document Directory, Data Hub, Chat, ingestion, MCP connectors, Telegram ingestion, and company evidence continue to work as before.

## What It Extracts

After a document completes ingestion, the pipeline proposes relationship candidates and then verifies them with the organization's enabled OpenAI provider connection before writing records. If no OpenAI provider key is configured, Relationship Intelligence does not add guessed entities.

The candidate pass looks for:

- Clients and prospective clients.
- Investors, funds, partners, and contact domains.
- People mentioned as founders, management, attendees, or contacts.
- Meeting-note interactions from Granola, Telegram, and uploaded notes.
- Deal signals such as fundraises, M&A, sell-side, buy-side, mandates, stages, and amounts.
- Follow-ups, todos, next steps, and action items.

Each generated record stores evidence excerpts, source type, source URL when available, and document or connector references. The extraction step is intentionally tolerant: if OpenAI verification or relationship extraction fails, ingestion continues and the pipeline records a warning.

## Scan Runs

Relationship scans run in the background. Starting a scan creates a scan-run record with:

- `queued`, `running`, `completed`, or `failed` status.
- Total and processed counts.
- Last scanned document ID and name.
- Result counts for entities, interactions, actions, and deals.

Only one relationship scan can be queued or running at a time for an organization. The UI polls the latest scan and disables scan buttons while the background process is active.

Incremental rescans use the last completed scan timestamp, so new document scans do not have to start from scratch. The **Delete All** action clears relationship records and scan history only; it does not delete indexed documents or other app data.

## Internet Discovery

The Relationship workspace can queue an OpenAI web discovery scan. It uses the current relationship list to form a search query, or an optional user-provided query, then asks OpenAI web search for relevant companies and investors. Returned candidates still pass through OpenAI verification before insertion, and public sector, geography, website, and contact email values are stored only when supported by search output.

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
- `POST /api/relationships/web-discovery`
- `GET /api/relationships/scan-runs/latest`
- `DELETE /api/relationships/all`

`/api/relationships/rescan` requires ingestion permission and reprocesses already-derived document text into relationship records.
