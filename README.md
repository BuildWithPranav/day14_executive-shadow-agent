# 🕴️ Executive Shadow Agent

> **A production-grade AI agent that drafts replies to your Slack and Email messages in your own voice — grounded in your knowledge base, triaged by urgency, and held for your approval before anything sends.**

---

## 📸 Overview

Founders and execs drown in repetitive Slack threads and emails. This agent watches inbound messages, retrieves relevant context from your knowledge base and past sent messages, drafts a reply that sounds like you, classifies urgency, and queues it for one-click approval. You stay in control — nothing sends without your sign-off.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            Slack Events API · Email Webhook (inbound)        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    ShadowService                             │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. Ingest — store incoming message + thread context  │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  2. Retrieve — pull relevant knowledge base docs +    │   │
│  │     style-matched historical sent messages            │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  3. Shadow Model — LLM (or heuristic fallback) drafts │   │
│  │     AgentDecision: urgency, intent, draft reply,      │   │
│  │     confidence, reasoning                              │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  4. Approval Queue — dashboard shows pending drafts   │   │
│  │     pending → approved/rejected → sent                │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │  5. Dispatch — SlackConnector / EmailConnector sends  │   │
│  │     the approved reply on your behalf                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤖 How It Works

1. **Connect channels** — Slack Events API and/or inbound email webhook feed the agent
2. **Build your knowledge base** — ingest policies, FAQs, product docs (`source_type`, `title`, `content`, `tags`)
3. **Teach it your voice** — ingest historical sent messages so the drafter mirrors your tone
4. **Message arrives** → agent retrieves relevant knowledge + style examples → drafts a reply
5. **Triage** — every draft is classified: urgency (`low`/`normal`/`high`/`critical`) and intent (pricing, support, delivery planning, etc.)
6. **You review** in the dashboard — approve, reject, or edit
7. **On approval** — the agent sends the reply via Slack or Email automatically

Falls back to a deterministic `HeuristicShadowModel` with zero API key required — useful for local dev and testing the pipeline end-to-end.

---

## 📁 Folder Structure

```
executive-shadow-agent/
├── app/
│   ├── service.py            # ShadowService — core orchestration
│   ├── llm.py                 # BaseShadowModel: LLM + Heuristic fallback
│   ├── repositories.py        # SQLite persistence (knowledge, messages, drafts)
│   ├── schemas.py              # Pydantic models (AgentDecision, DraftDetailResponse, etc.)
│   ├── models.py               # Domain models
│   ├── connectors/
│   │   ├── slack.py            # Slack Events API + send
│   │   └── email.py            # Email inbound + send
│   ├── ui/dashboard.html       # Approval queue dashboard
│   ├── api.py                  # FastAPI routes
│   ├── security.py             # Webhook signature verification
│   ├── seed.py                  # Demo data seeding
│   ├── db.py                    # SQLite setup
│   └── config.py                # Settings
├── .env.example
├── Dockerfile
└── pyproject.toml
```

---

## ⚡ Quick Start

### 1. Clone & Configure
```bash
git clone <repo-url>
cd executive-shadow-agent
cp .env.example .env
# Add OPENAI_API_KEY, SLACK_BOT_TOKEN, EMAIL credentials
```

### 2. Install & Run
```bash
pip install -e .
uvicorn app.main:app --reload
```

### 3. Seed Demo Data
```bash
python -m app.seed
```

### 4. Run with Docker
```bash
docker build -t executive-shadow-agent .
docker run -p 8000:8000 --env-file .env executive-shadow-agent
```

Open dashboard: http://localhost:8000/ui/dashboard.html

---

## 📡 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/knowledge` | Ingest a knowledge base document |
| `POST` | `/sent-messages` | Ingest a historical sent message (style learning) |
| `POST` | `/webhook/slack` | Inbound Slack event → generates draft |
| `POST` | `/webhook/email` | Inbound email event → generates draft |
| `GET` | `/drafts` | List pending/approved/rejected drafts |
| `GET` | `/drafts/{id}` | Get a specific draft |
| `POST` | `/drafts/{id}/approve` | Approve → dispatch the reply |
| `POST` | `/drafts/{id}/reject` | Reject a draft |
| `GET` | `/health` | Health check |

### AgentDecision Output
```json
{
  "urgency": "high",
  "intent": "pricing",
  "draft_reply": "Hey Raj — thanks for following up! Our Pro plan is...",
  "confidence": 0.87,
  "reasoning": "Sender asked a direct pricing question with an EOD deadline."
}
```

---

## ⚙️ Configuration

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | LLM drafting backend (optional — falls back to heuristic) |
| `SLACK_BOT_TOKEN` | Slack send permission |
| `SLACK_SIGNING_SECRET` | Webhook signature verification |
| `EMAIL_PROVIDER` | SMTP / SendGrid |
| `DATABASE_PATH` | SQLite file path |

---

## 🚀 Scaling Path

| Stage | Upgrade |
|-------|---------|
| **Now** | SQLite + single user |
| **Founder/exec** | Multi-channel (Slack + Email + WhatsApp), mobile approval app |
| **Team** | Multi-user shadow profiles, per-person voice learning |
| **Enterprise** | Auto-approve low-risk replies, escalation routing, audit trail |

---

## 📦 Built With

- **FastAPI** — REST API + webhooks
- **LLM (with heuristic fallback)** — Drafting + urgency/intent triage
- **SQLite** — Knowledge base + message + draft storage
- **Slack Events API** — Inbound/outbound Slack integration
- **Email (SMTP/SendGrid)** — Inbound/outbound email integration
- **Tenacity** — Retry with exponential backoff
- **structlog** — Structured logging

---

*Day 14/27 — Built by Pranav | IIT Kharagpur · AI Automation Agency*
