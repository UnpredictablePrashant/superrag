# Telegram Integration

The Telegram integration lets approved Telegram users add content to a knowledge base and ask grounded questions from Telegram.

## Prerequisites

- A running API with `API_BASE_URL` set to the public HTTPS base URL that Telegram can reach.
- A knowledge base for Telegram-ingested content.
- A configured chat model profile for answer/refine actions, such as an OpenAI profile using `gpt-5.1`.
- An OpenAI provider connection if you want Telegram voice notes transcribed.

For local development, expose the API with a tunnel such as ngrok and set `API_BASE_URL` to that HTTPS URL before registering the webhook.

## Create the Telegram Bot

1. Open Telegram and message `@BotFather`.
2. Run `/newbot`.
3. Choose the bot display name and username.
4. Copy the bot token.

## Configure RAG Console

1. Open `Settings -> AI Providers`.
2. Add an LLM provider connection, then test it.
3. Open `Settings -> Model Profiles`.
4. Create a chat model profile from the provider model list.
5. Open `Settings -> Telegram`.
6. Paste the bot token, set the bot username, choose the default knowledge base, choose the answer/refine model, and enable the integration.
7. Save, then click `Test`.
8. Click `Register webhook`.

The webhook registered with Telegram is:

```text
{API_BASE_URL}/api/integrations/telegram/webhook/{integration_id}
```

The app sends Telegram the integration's webhook secret token during registration, and the webhook route verifies it on every incoming Telegram update.

## Allow Telegram Users

In `Settings -> Telegram`, add each approved user by at least one identifier:

- Telegram user ID
- Telegram username
- Phone number

Linking the entry to a RAG user ID is required for `/ask`, because chat retrieval needs the user's organization membership and document permissions. Ingestion can work without a linked RAG user when `Can ingest` is enabled.

Admins can also enter Telegram identifiers while inviting a teammate from `Team Management`. When the invite is accepted, the app creates or links the Telegram allow-list entry to that RAG account automatically.

## Telegram Commands

```text
/help
/add your note
/ask your question
```

Plain text messages are treated as ingestable notes when text ingestion is enabled. Documents are uploaded to the default knowledge base when document ingestion is enabled. Voice/audio messages are transcribed with the configured OpenAI provider, refined with the selected chat model, and ingested when voice ingestion is enabled.

## Troubleshooting

- `Telegram bot token is not configured`: save the bot token before testing or registering the webhook.
- `Invalid Telegram webhook`: make sure the integration is enabled and the webhook was registered after the current `API_BASE_URL` was set.
- `This Telegram account is not allowed`: add the sender to the allowed users list by username, Telegram ID, or phone number.
- `/ask` fails for a user: link that Telegram entry to an active RAG user ID in the same organization.
- Voice transcription fails: add and enable an OpenAI provider connection.
