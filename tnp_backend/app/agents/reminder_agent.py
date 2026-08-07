"""
Reminder Agent — FR-13 (WhatsApp message drafting).

Lowest-stakes agent in the system — only drafts human-facing text, never makes
data decisions. Has a full deterministic fallback if the LLM call fails.
"""
from __future__ import annotations

from loguru import logger

from app.services.llm_service import LLMServiceError, llm_service

# ── Fallback template ────────────────────────────────────────────────────────

_FALLBACK_TEMPLATE = """\
Hi! 👋

This is a reminder from the ECE'27 TNP Cell regarding the *{company_name}* placement drive.

{pending_count} student(s) haven't submitted their form yet.

Please fill your details in the form:
{form_url}

*Deadline: {deadline}*

If you've already submitted, please ignore this message.

Thank you,
ECE'27 TNP Cell
"""

# ── Prompt templates ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are drafting a short, friendly WhatsApp reminder message for college students
about a pending placement registration form.

Guidelines:
- Be concise and friendly (3-5 short paragraphs max)
- Include the company name, form link placeholder {form_url}, and deadline clearly
- Use appropriate WhatsApp formatting (*bold* for emphasis)
- Professional but approachable tone
- End with "ECE'27 TNP Cell" sign-off

Output ONLY the message text. No JSON, no metadata.
"""

_USER_PROMPT_TEMPLATE = """\
Draft a WhatsApp reminder message with these details:
- Company: {company_name}
- Deadline: {deadline}
- Number of pending students: {pending_count}
- Form URL: {{form_url}} (use this exact placeholder)
"""


class ReminderAgent:
    """Drafts WhatsApp reminder messages for students with pending form responses."""

    def draft_message(
        self,
        company_name: str,
        deadline: str,
        pending_count: int,
    ) -> str:
        """
        Draft a WhatsApp reminder message.
        Falls back to a static template if the LLM call fails.

        Returns
        -------
        str — the message body (with {form_url} as a placeholder to be filled later).
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            company_name=company_name,
            deadline=deadline,
            pending_count=pending_count,
        )

        try:
            message = llm_service.generate_text(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                use_reminder_temperature=True,
            )
            if message and message.strip():
                logger.debug("Reminder Agent: LLM draft successful.")
                return message.strip()
        except LLMServiceError as exc:
            logger.warning(
                f"Reminder Agent LLM call failed: {exc}. Using static fallback template."
            )

        # Deterministic fallback 
        logger.info("Reminder Agent: Using static fallback template.")
        return _FALLBACK_TEMPLATE.format(
            company_name=company_name,
            pending_count=pending_count,
            deadline=deadline,
            form_url="{form_url}",  # Keep as placeholder
        )


# Singleton
reminder_agent = ReminderAgent()
