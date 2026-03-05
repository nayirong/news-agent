"""
Secretary (Donna) Claude API client with vision support and calendar tools.

The system prompt is assembled from:
    0. Agents/Calendar Agent/SOUL.md
    0. Agents/Calendar Agent/RULES.md
    0. Agents/Calendar Agent/SKILLS.md

Key differences from ClaudeClient (Atlas):
  - Supports image content (base64) for event invite screenshots
  - Uses CALENDAR_TOOLS instead of MANAGEMENT_TOOLS
  - No web_search tool — Donna is focused purely on calendar management
  - Single method: handle_request() covers all interaction types
"""
import logging
from typing import Optional

from anthropic import Anthropic, APIError

from config.settings import settings
from src.agent_loader import agent_loader
from src.calendar.calendar_tools import CALENDAR_TOOLS, CalendarToolExecutor

logger = logging.getLogger(__name__)

SECRETARY_AGENT_NAME = "Calendar Agent"

# ---------------------------------------------------------------------------
# User-turn prompt templates
# ---------------------------------------------------------------------------

TEXT_REQUEST_PROMPT = """\
{message}

Today's date and time (UTC): {now}
"""

IMAGE_REQUEST_PROMPT = """\
The user has sent an image (likely an event invite, calendar screenshot, or email screenshot).

Please analyze the image and extract all calendar event details you can find:
- Event title/name
- Date and time (start and end)
- Location
- Description or agenda
- Organizer or attendees (if visible)

Then apply your scheduling skills: check for conflicts, show the extracted details to the user,
and ask for confirmation before adding to the calendar.

Additional context from the user: {user_text}

Today's date and time (UTC): {now}
"""


class SecretaryClient:
    """
    Wraps the Anthropic Messages API for Aria (calendar secretary).

    Supports:
      - Text requests (calendar queries, scheduling from text)
      - Image requests (event invite screenshots via vision)
      - Calendar tool use (agentic loop with CalendarToolExecutor)
    """

    def __init__(self):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL

    @property
    def system_prompt(self) -> str:
        """
        Assembled system prompt from Calendar Agent markdown files.
        Cached by AgentLoader. Edit SOUL.md, RULES.md, SKILLS.md to update.
        """
        return agent_loader.get_system_prompt(SECRETARY_AGENT_NAME)

    def _call_claude(
        self,
        messages: list,
        max_tokens: int = 2000,
        extra_tools: Optional[list] = None,
    ):
        """
        Core Claude API call. Optionally includes calendar tools.

        Args:
            messages:    Full messages list in Anthropic format.
            max_tokens:  Token limit for the response.
            extra_tools: Tool schemas to include (calendar tools).

        Returns:
            Raw Anthropic API response object.
        """
        tools = extra_tools or []
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        return self.client.messages.create(**kwargs)

    def handle_request(
        self,
        text: str,
        image_b64: Optional[str] = None,
        mime_type: str = "image/jpeg",
        tool_executor: Optional[CalendarToolExecutor] = None,
        conversation_history: Optional[list] = None,
    ) -> str:
        """
        Handle a secretary request — text, image, or both.

        If image_b64 is provided, Claude will analyze the image using vision.
        If tool_executor is provided, Claude can call calendar tools to read/write
        the user's calendar in an agentic loop (up to 8 iterations).
        If conversation_history is provided, prior exchanges are included as
        multi-turn messages so Claude remembers context (e.g. "yes" confirmations).

        Args:
            text:                 The user's text message (may be empty if image-only).
            image_b64:            Base64-encoded image string (optional).
            mime_type:            MIME type of the image (default: image/jpeg).
            tool_executor:        If provided, enables calendar tool calls.
            conversation_history: List of prior {"role": ..., "content": ...} dicts.

        Returns:
            Donna's response string.
        """
        try:
            from datetime import datetime, timezone
            now_str = datetime.now(tz=timezone.utc).strftime("%A, %Y-%m-%d %H:%M UTC")

            # Build the current user message content
            if image_b64:
                prompt = IMAGE_REQUEST_PROMPT.format(
                    user_text=text or "(no additional context)",
                    now=now_str,
                )
                content = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ]
            else:
                prompt = TEXT_REQUEST_PROMPT.format(message=text, now=now_str)
                content = prompt

            # Prepend conversation history so Claude has full context for
            # short replies like "yes", "no", "make it 3pm instead", etc.
            messages = list(conversation_history) if conversation_history else []
            messages.append({"role": "user", "content": content})

            extra_tools = CALENDAR_TOOLS if tool_executor else None

            response = None
            for iteration in range(8):  # safety cap — prevents runaway loops
                response = self._call_claude(
                    messages=messages,
                    max_tokens=2000,
                    extra_tools=extra_tools,
                )

                if response.stop_reason != "tool_use" or not tool_executor:
                    break

                # Execute all pending calendar tool calls
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = tool_executor.execute(block.name, block.input)
                        logger.info(f"Calendar tool '{block.name}' → {result[:120]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                if not tool_results:
                    break
                messages.append({"role": "user", "content": tool_results})

            logger.info(f"Secretary handled request in {iteration + 1} iteration(s)")
            return self._extract_text(response)

        except APIError as e:
            logger.error(f"Anthropic API error in secretary: {e}")
            return "Sorry, I had trouble connecting to my AI service. Please try again."
        except Exception as e:
            logger.error(f"Unexpected error in secretary: {e}", exc_info=True)
            return "Sorry, something went wrong. Please try again."

    @staticmethod
    def _extract_text(response) -> str:
        """Extract all text blocks from a Claude API response."""
        return "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )


# Module-level singleton
secretary_client = SecretaryClient()
