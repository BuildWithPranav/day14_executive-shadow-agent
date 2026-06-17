import asyncio

from app.config import get_settings
from app.db import init_db
from app.repositories import ShadowRepository


async def seed() -> None:
    """Load sample knowledge and sent-message style exemplars."""

    settings = get_settings()
    await init_db(settings)
    repository = ShadowRepository(settings.database_path)

    knowledge_docs = [
        {
            "source_type": "policy",
            "title": "Launch Commitments Policy",
            "content": "Never promise accelerated launch dates externally until engineering confirms capacity and dependencies are cleared.",
            "tags": ["launch", "delivery", "commitments"],
        },
        {
            "source_type": "faq",
            "title": "Enterprise Pricing FAQ",
            "content": "Enterprise pricing includes premium onboarding only when explicitly included on the order form. Custom implementation work is scoped separately.",
            "tags": ["pricing", "sales", "enterprise"],
        },
        {
            "source_type": "policy",
            "title": "Refund Escalation",
            "content": "Refunds above $5,000 require CFO approval and a written root-cause summary from the account owner.",
            "tags": ["refund", "finance", "approval"],
        },
    ]
    sent_messages = [
        {
            "channel": "email",
            "sender": "ceo@company.com",
            "recipient": "client@acme.com",
            "subject": "Re: Launch timeline",
            "body": "Thanks for the note. Here is the cleanest path forward: we can move quickly, but I do not want to overcommit before the team clears the remaining dependency chain.",
        },
        {
            "channel": "email",
            "sender": "ceo@company.com",
            "recipient": "buyer@globex.com",
            "subject": "Re: Enterprise pricing",
            "body": "Short version: premium onboarding is included only when it is written into the order form. If you want that packaged in, we can scope it explicitly and keep the rollout predictable.",
        },
        {
            "channel": "slack",
            "sender": "ceo",
            "recipient": "#leadership",
            "subject": None,
            "body": "Keep the answer tight. Clarify what we know, what still needs confirmation, and what next step we are taking.",
        },
    ]

    for doc in knowledge_docs:
        await repository.ingest_knowledge(**doc)
    for message in sent_messages:
        await repository.ingest_sent_message(created_at=None, **message)

    print("Seed complete.")


def run() -> None:
    """CLI entry point."""

    asyncio.run(seed())


if __name__ == "__main__":
    run()
