# Executive Shadow Agent

FastAPI starter repo for an **Executive Shadow** agent that watches inbound Slack and email traffic, learns your communication patterns from prior messages and internal docs, drafts responses, and requires a one-click approval before anything is sent.

## What this ships

- Async FastAPI backend
- SQLite-backed knowledge capture and draft queue
- Full-text retrieval over policies, product docs, and sent messages
- Heuristic drafting backend for zero-key local development
- OpenAI drafting backend for higher-quality ghost drafts
- Slack preview connector
- SMTP send connector for approved email sends
- Inline dashboard with approve / reject actions
- Docker-ready layout

## Architecture

1. **Knowledge Capture**
   - Ingest policy docs, FAQs, and prior sent messages.
   - Store them in SQLite + FTS5.
2. **Triage**
   - Receive inbound Slack or email events.
   - Retrieve matching context and classify urgency.
3. **Ghost Draft**
   - Generate a draft reply using internal docs plus style exemplars.
   - Save it in the dashboard and optionally mirror a Slack preview.
4. **1-Click Send**
   - Approve from the dashboard.
   - Slack replies post to thread.
   - Email replies send over SMTP.

## Repo layout

```text
executive-shadow-agent/
├── app/
│   ├── api.py
│   ├── config.py
│   ├── db.py
│   ├── llm.py
│   ├── logging.py
│   ├── models.py
│   ├── repositories.py
│   ├── schemas.py
│   ├── security.py
│   ├── seed.py
│   ├── service.py
│   ├── connectors/
│   │   ├── email.py
│   │   └── slack.py
│   └── ui/
│       └── dashboard.html
├── data/
├── .env.example
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Quick start

### 1) Install

```bash
uv sync
```

### 2) Configure env

```bash
cp .env.example .env
```

Minimum local-dev setup:

- `ADMIN_TOKEN=change-me`
- `LLM_BACKEND=heuristic`
- `DRY_RUN_SENDS=true`

For OpenAI drafts:

- `LLM_BACKEND=openai`
- `OPENAI_API_KEY=...`

For real sends:

- set SMTP credentials
- set `DRY_RUN_SENDS=false`

### 3) Seed sample knowledge

```bash
uv run shadow-seed
```

### 4) Start the API

```bash
uv run shadow-api
```

Open:

- Health: `http://127.0.0.1:8000/health`
- Dashboard: `http://127.0.0.1:8000/dashboard`

## API examples

### Ingest knowledge

```bash
curl -X POST http://127.0.0.1:8000/ingest/knowledge \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: change-me" \
  -d '{
    "source_type": "policy",
    "title": "Escalation Policy",
    "content": "Refunds above $5,000 require CFO approval.",
    "tags": ["finance", "refund"]
  }'
```

### Ingest past sent message

```bash
curl -X POST http://127.0.0.1:8000/ingest/sent-message \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: change-me" \
  -d '{
    "channel": "email",
    "sender": "ceo@company.com",
    "recipient": "client@acme.com",
    "subject": "Re: Launch timeline",
    "body": "Thanks for the note. Here is the cleanest path forward..."
  }'
```

### Trigger a Slack draft

```bash
curl -X POST http://127.0.0.1:8000/events/slack \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "C123456",
    "channel_name": "client-success",
    "user_id": "U234567",
    "user_name": "sarah",
    "text": "Urgent: client wants to know if we can move launch up by 2 weeks.",
    "ts": "1712345678.000100",
    "thread_ts": "1712345678.000100"
  }'
```

### Trigger an email draft

```bash
curl -X POST http://127.0.0.1:8000/events/email \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "msg-001",
    "from_address": "client@acme.com",
    "to_address": "ceo@company.com",
    "subject": "Need revised pricing today",
    "body": "Can you confirm if enterprise pricing includes premium onboarding?"
  }'
```

### Approve and send

```bash
curl -X POST http://127.0.0.1:8000/drafts/1/approve \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: change-me" \
  -d '{"actor": "founder", "note": "Looks good"}'
```

## Security notes

- The dashboard requires `X-Admin-Token` for draft listing and approval actions.
- Slack request verification is supported when `SLACK_SIGNING_SECRET` is configured.
- Generic inbound email providers can use `X-Event-Secret` when `INBOUND_EVENT_SECRET` is set.
- Keep `DRY_RUN_SENDS=true` until you've validated outbound routing.

## Production upgrades

1. Replace SQLite with Postgres + pgvector.
2. Add Gmail or Microsoft Graph draft creation.
3. Add SSO and per-user approval policies.
4. Add Redis queues for bursty traffic.
5. Add OpenTelemetry tracing and audit logs.

## Zip output

A GitHub-ready zip is generated in this workspace as:

- `executive-shadow-agent.zip`
