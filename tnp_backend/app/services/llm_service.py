"""
LLM Service — single point of contact with the Ollama server via LangChain.

Owns:
- Prompt execution with timeout and retry-with-backoff
- Structured output validation against a Pydantic schema
- A uniform interface so every agent reuses the same retry/error-handling logic

All agents call `llm_service.generate_structured(prompt, schema)` or
`llm_service.generate_text(prompt)` — they never touch Ollama directly.
"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from loguru import logger
from pydantic import BaseModel, ValidationError

from app.config import settings

if TYPE_CHECKING:
    pass

T = TypeVar("T", bound=BaseModel)


class LLMServiceError(Exception):
    """Raised when the LLM service fails after all retries."""


class LLMService:
    """
    Thin wrapper around ChatOllama with structured output support.
    One instance is shared across all agents.
    """

    def __init__(self) -> None:
        self._chat_llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            num_predict=settings.llm_max_tokens,
        )
        self._reminder_llm = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.llm_reminder_temperature,
            num_predict=settings.llm_max_tokens,
        )

    def _call_with_retry(
        self,
        llm: ChatOllama,
        messages: list[Any],
        max_retries: int = 2,
    ) -> str:
        """Call the LLM with exponential-backoff retry. Returns raw text content."""
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = llm.invoke(messages)
                return str(response.content)
            except Exception as exc:
                last_error = exc
                wait = 2 ** attempt
                logger.warning(
                    f"LLM call failed (attempt {attempt + 1}/{max_retries + 1}): {exc}. "
                    f"Retrying in {wait}s…"
                )
                if attempt < max_retries:
                    time.sleep(wait)
        raise LLMServiceError(
            f"LLM call failed after {max_retries + 1} attempts: {last_error}"
        )

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        use_reminder_temperature: bool = False,
    ) -> str:
        """Generate plain text output (e.g., for the Reminder Agent)."""
        llm = self._reminder_llm if use_reminder_temperature else self._chat_llm
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        return self._call_with_retry(llm, messages)

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        max_retries: int = 2,
    ) -> T:
        """
        Generate LLM output and validate it against a Pydantic schema.

        If JSON parsing or schema validation fails, retries with a correction
        prompt up to `max_retries` times. Raises LLMServiceError on persistent failure.
        """
        messages: list[Any] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        last_error: str = ""
        for attempt in range(max_retries + 1):
            try:
                raw = self._call_with_retry(self._chat_llm, messages, max_retries=1)
                # Extract JSON from the response (model may wrap it in markdown)
                json_str = self._extract_json(raw)
                data = json.loads(json_str)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = str(exc)
                logger.warning(
                    f"Structured output parse failed (attempt {attempt + 1}): {exc}"
                )
                if attempt < max_retries:
                    # Append a correction turn to the conversation
                    correction = (
                        f"Your previous response was invalid. Error: {exc}\n\n"
                        f"Return ONLY a valid JSON object matching this schema:\n"
                        f"{schema.model_json_schema()}\n\n"
                        "No markdown, no prose, no code fences — ONLY the JSON object."
                    )
                    messages.append(HumanMessage(content=correction))

        raise LLMServiceError(
            f"Structured generation failed after {max_retries + 1} attempts. "
            f"Last error: {last_error}"
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Extract the first JSON object from a string that may contain
        markdown code fences (```json ... ```) or prose around it.
        """
        text = text.strip()
        # Remove common markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        # Find the first { ... } block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text  # Fall through — let json.loads raise if still invalid


# Singleton instance
llm_service = LLMService()
