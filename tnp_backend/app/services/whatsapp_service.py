"""
WhatsApp Service — formats and (in future) sends WhatsApp messages.

MVP behaviour: generates message text only, returns it for manual copy-paste.
A WhatsAppSender protocol is defined so that a future Twilio / WhatsApp Business
API / Playwright integration can be plugged in without changing calling code.
"""
from __future__ import annotations

from typing import Protocol

from loguru import logger


# ── Sender protocol (for future integrations) ────────────────────────────────

class WhatsAppSender(Protocol):
    """Protocol for a pluggable WhatsApp send backend."""

    def send(self, message: str, recipients: list[str]) -> None:
        """Send `message` to each recipient (phone number or group ID)."""
        ...


class StubSender:
    """MVP no-op sender — logs the message, returns it for manual copy-paste."""

    def send(self, message: str, recipients: list[str]) -> None:
        logger.info(
            f"[STUB] WhatsApp message NOT sent "
            f"(sending is out of scope for MVP). "
            f"Recipients: {recipients}\n"
            f"Message:\n{message}"
        )


# ── Static fallback template ─────────────────────────────────────────────────
_FALLBACK_TEMPLATE = """\
📢 *{company_name} Placement Drive — Action Required*

Hi! The TNP Cell needs a few additional details for the {company_name} placement process.

👉 Please fill this form before *{deadline}*:
{form_url}

If you've already submitted, ignore this message.

— TNP Cell
"""


class WhatsAppService:
    """
    Formats WhatsApp messages from Reminder Agent output or a static template.
    In the MVP, `send()` is a no-op; the formatted message is returned to the
    coordinator for manual distribution.
    """

    def __init__(self, sender: WhatsAppSender | None = None) -> None:
        self._sender: WhatsAppSender = sender or StubSender()

    def format_message(
        self,
        company_name: str,
        form_url: str,
        deadline: str,
        agent_message: str | None = None,
    ) -> str:
        """
        Build the final WhatsApp message string.
        If `agent_message` is provided (from the Reminder Agent), use it.
        Otherwise fall back to the static template.
        """
        if agent_message and agent_message.strip():
            # Replace the form URL placeholder if the agent left one in
            msg = agent_message.replace("{form_url}", form_url)
            logger.debug("Using Reminder Agent message for WhatsApp.")
            return msg

        logger.debug("Using static fallback template for WhatsApp message.")
        return _FALLBACK_TEMPLATE.format(
            company_name=company_name,
            deadline=deadline,
            form_url=form_url,
        )

    def send(self, message: str, recipients: list[str] | None = None) -> None:
        """
        Attempt to send the message via the configured sender.
        In MVP, this is always the StubSender (no-op + log).
        """
        self._sender.send(message, recipients or [])


# Singleton
whatsapp_service = WhatsAppService()
