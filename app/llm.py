import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.schemas import AgentDecision, ContextSnippet, IncomingMessageRecord


class LLMError(RuntimeError):
    """Raised when the LLM backend fails."""


class BaseShadowModel(ABC):
    """Abstract drafting backend."""

    @abstractmethod
    async def generate_draft(
        self,
        *,
        incoming_message: IncomingMessageRecord,
        retrieved_context: list[ContextSnippet],
    ) -> AgentDecision:
        """Generate triage and a proposed response draft."""


class HeuristicShadowModel(BaseShadowModel):
    """Fallback backend for local development without API keys."""

    def _urgency(self, text: str) -> str:
        lowered = text.lower()
        if any(token in lowered for token in ["critical", "outage", "breach"]):
            return "critical"
        if any(token in lowered for token in ["urgent", "asap", "today", "blocker", "eod"]):
            return "high"
        if any(token in lowered for token in ["when", "timeline", "price", "pricing", "question"]):
            return "normal"
        return "low"

    def _intent(self, text: str) -> str:
        lowered = text.lower()
        if "price" in lowered or "pricing" in lowered:
            return "pricing"
        if "bug" in lowered or "issue" in lowered or "error" in lowered:
            return "support"
        if "launch" in lowered or "timeline" in lowered:
            return "delivery_planning"
        if "refund" in lowered:
            return "refund_request"
        return "general_response"

    def _subject(self, incoming_message: IncomingMessageRecord) -> str | None:
        if incoming_message.channel == "email":
            subject = incoming_message.subject or "Follow-up"
            return subject if subject.lower().startswith("re:") else f"Re: {subject}"
        return None

    async def generate_draft(
        self,
        *,
        incoming_message: IncomingMessageRecord,
        retrieved_context: list[ContextSnippet],
    ) -> AgentDecision:
        """Generate a deterministic draft from the retrieved context."""

        urgency = self._urgency(f"{incoming_message.subject or ''} {incoming_message.body}")
        intent = self._intent(f"{incoming_message.subject or ''} {incoming_message.body}")
        recipient_name = incoming_message.sender.split("@")[0].replace(".", " ").title()
        context_lines = []
        for item in retrieved_context[:3]:
            excerpt = item.content.strip().replace("\n", " ")
            context_lines.append(f"- {item.title}: {excerpt[:180]}")
        context_block = "\n".join(context_lines) if context_lines else "- No exact doc match found. Use conservative language."

        if incoming_message.channel == "email":
            greeting = f"Hi {recipient_name},"
            signoff = "\n\nBest,\nExecutive Office"
        else:
            greeting = f"{recipient_name} —"
            signoff = ""

        body = (
            f"{greeting}\n\n"
            f"Thanks for the note. I reviewed the latest internal guidance and here is the cleanest response path.\n\n"
            f"Relevant context:\n{context_block}\n\n"
            f"Proposed response: We can address this, but I want to keep the commitment precise. "
            f"Based on the current operating guidance, we should confirm scope, timing, and any approval dependencies before locking a promise. "
            f"If you want, I can send the exact external-facing version once you confirm there are no last-minute blockers on our side."
            f"{signoff}"
        )
        rationale = (
            "Draft built from retrieved policy/style snippets. Tone stays measured, avoids overcommitting, "
            "and pushes toward a clear next step."
        )
        confidence = 0.55 if retrieved_context else 0.35
        return AgentDecision(
            urgency=urgency,
            intent=intent,
            subject=self._subject(incoming_message),
            body=body,
            rationale=rationale,
            confidence=confidence,
        )


class OpenAIShadowModel(BaseShadowModel):
    """OpenAI-backed drafting backend with JSON-only output."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.base_url = settings.openai_base_url.rstrip("/")

    async def generate_draft(
        self,
        *,
        incoming_message: IncomingMessageRecord,
        retrieved_context: list[ContextSnippet],
    ) -> AgentDecision:
        """Generate a structured ghost draft via OpenAI chat completions."""

        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is required when LLM_BACKEND=openai.")

        system_prompt = (
            "You are Executive Shadow, a secure drafting agent for a senior executive. "
            "Your job is to triage inbound communication and produce a draft reply in the executive's voice. "
            "Never promise anything unsupported by the provided context. "
            "Return JSON only with keys: urgency, intent, subject, body, rationale, confidence. "
            "Confidence must be a float between 0 and 1."
        )
        context_block = "\n\n".join(
            f"[{item.source.upper()}] {item.title}\n{item.content[:1200]}" for item in retrieved_context
        ) or "No retrieved context available. Be conservative and explicit about uncertainty."
        user_prompt = (
            f"CHANNEL: {incoming_message.channel}\n"
            f"FROM: {incoming_message.sender}\n"
            f"TO: {incoming_message.recipient}\n"
            f"SUBJECT: {incoming_message.subject}\n"
            f"THREAD: {incoming_message.thread_key}\n\n"
            f"INBOUND MESSAGE:\n{incoming_message.body}\n\n"
            f"RETRIEVED CONTEXT:\n{context_block}\n\n"
            "Write a response draft that is crisp, high-agency, and context-aware. "
            "If the channel is email, include a suitable reply subject."
        )
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "executive_shadow_draft",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "urgency": {
                                "type": "string",
                                "enum": ["low", "normal", "high", "critical"]
                            },
                            "intent": {"type": "string"},
                            "subject": {"type": ["string", "null"]},
                            "body": {"type": "string"},
                            "rationale": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["urgency", "intent", "subject", "body", "rationale", "confidence"]
                    }
                }
            }
        }

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, LLMError)),
            reraise=True,
        ):
            with attempt:
                return await self._chat_once(payload)

        raise LLMError("OpenAI retry loop exited unexpectedly.")

    async def _chat_once(self, payload: dict[str, Any]) -> AgentDecision:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            raise LLMError(f"OpenAI request failed: {response.status_code} {response.text}")

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("OpenAI response contained no choices.")
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            content = "".join(parts)
        payload_text = self._extract_json(str(content))
        return AgentDecision.model_validate(json.loads(payload_text))

    def _extract_json(self, text: str) -> str:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise LLMError("Could not parse JSON from LLM response.")
        return match.group(0)


def build_shadow_model(settings: Settings) -> BaseShadowModel:
    """Factory for the configured drafting backend."""

    if settings.llm_backend == "openai":
        return OpenAIShadowModel(settings)
    return HeuristicShadowModel()
