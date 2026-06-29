# API

OpenAPI docs are available at `/docs` when the API is running.

Primary route groups:

- `/api/auth/*`: OTP, verification, logout, current session.
- `/api/organizations/*`: current organization, invitations, members.
- `/api/knowledge-bases/*`: knowledge bases and nested categories.
- `/api/uploads/*`: presigned upload and completion.
- `/api/documents/*`: document metadata, preview, quality report, review actions.
- `/api/pipeline-runs/*`: run creation, listing, cancellation, retry, SSE events.
- `/api/provider-connections/*`: encrypted provider credentials and connection tests.
- `/api/chat-sessions/*`: sessions, messages, streaming answers.
- `/api/retrieval/*`: search and admin debug.
- `/api/notifications/*`: in-app notifications.
- `/api/audit-logs`: admin audit log view.

All tenant-scoped routes require a valid session cookie and enforce organization membership server-side.
