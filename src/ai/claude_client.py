"""
Claude API client with web search.

The system prompt is assembled entirely by AgentLoader from:
    0. Agents/News Agent/SOUL.md
    0. Agents/News Agent/RULES.md
    0. Agents/News Agent/SKILLS.md

To change agent behavior, edit those markdown files — no Python changes needed.

This module handles the three call types:
    - generate_digest:    daily news digest for a user's interests
    - answer_question:    follow-up Q&A with recent conversation context
    - get_topic_news:     on-demand news for a specific topic
"""
import logging
from datetime import date
from typing import Optional

from anthropic import Anthropic, APIError

from config.settings import settings
from src.agent_loader import agent_loader
from src.ai.agent_tools import MANAGEMENT_TOOLS, AgentToolExecutor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User-turn prompt templates
#
# These are the "what to do right now" instructions, sent as the user message.
# The "who you are and how to behave" part lives in SOUL.md / RULES.md / SKILLS.md.
# ---------------------------------------------------------------------------

DIGEST_USER_PROMPT = """\
Today's date: {today}

Generate my personalized daily news digest.

My interests: {interests}

For each interest, search the web for the most important news published today ({today}) \
or yesterday. Only include stories with a publication date of {today} or the day before. \
Discard any results older than 2 days.
Find 1-2 significant stories per interest (total: 5-7 stories).
Follow the Daily Digest Generation skill format defined in your skills.\
"""

FOLLOWUP_USER_PROMPT = """\
Today's date: {today}

Follow-up question: {question}

Recent conversation context (last few exchanges):
{recent_context}

Search the web for current information published today ({today}) or yesterday, and answer with sources.
Follow the Follow-up Q&A skill format defined in your skills.\
"""

ONDEMAND_USER_PROMPT = """\
Today's date: {today}

On-demand news request: What is the latest on {topic}?

Search the web for the most recent 2-3 developments published today ({today}) or yesterday. \
Only include stories dated {today} or the day before.
Follow the On-Demand News Request skill format defined in your skills.\
"""


class ClaudeClient:
    """
    Wraps the Anthropic Messages API.

    The system prompt comes entirely from the agent definition markdown files,
    loaded via AgentLoader. All calls include the web_search tool so Claude
    can retrieve real-time information.
    """

    def __init__(self, agent_name: Optional[str] = None):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL
        self.web_search_tool = settings.WEB_SEARCH_TOOL
        self.agent_name = agent_name or settings.DEFAULT_AGENT_NAME

    @property
    def system_prompt(self) -> str:
        """
        Lazily assembled system prompt from the agent definition markdown files.
        Cached in memory by AgentLoader after first access.
        Edit SOUL.md, RULES.md, or SKILLS.md and call /reload (or restart) to update.
        """
        return agent_loader.get_system_prompt(self.agent_name)

    def _call_claude(self, messages: list, max_tokens: int, extra_tools: list = None):
        """
        Core Claude API call. Always includes the web_search tool.
        Optionally includes extra_tools (e.g. management tools for agentic mode).

        Args:
            messages: Full messages list in Anthropic format.
            max_tokens: Token limit for the response.
            extra_tools: Additional tool schemas beyond web_search.

        Returns:
            Raw Anthropic API response object.

        Raises:
            APIError: On Anthropic API failures (propagated to callers).
        """
        tools = [self.web_search_tool]
        if extra_tools:
            tools.extend(extra_tools)

        return self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self.system_prompt,
            tools=tools,
            messages=messages,
        )

    def generate_digest(self, user_interests: list[str]) -> str:
        """
        Generate a personalized daily news digest using web search.

        Args:
            user_interests: List of topics the user wants news about.

        Returns:
            Formatted digest string with headlines, summaries, and source URLs.
        """
        try:
            interests_str = ", ".join(user_interests)
            logger.info(f"Generating digest for interests: {interests_str}")

            today = date.today().strftime("%Y-%m-%d")
            response = self._call_claude(
                messages=[{"role": "user", "content": DIGEST_USER_PROMPT.format(interests=interests_str, today=today)}],
                max_tokens=settings.MAX_TOKENS_DIGEST,
            )
            result = self._extract_text(response)

            logger.info(f"Digest generated: {len(result)} chars")
            return result

        except APIError as e:
            logger.error(f"Anthropic API error generating digest: {e}")
            return (
                "Sorry, I couldn't generate your digest right now due to an API issue. "
                "Please try again in a few minutes."
            )
        except Exception as e:
            logger.error(f"Unexpected error generating digest: {e}")
            return "Sorry, something went wrong generating your digest. Please try again."

    def answer_question(
        self,
        question: str,
        recent_context: str = "",
        tool_executor: Optional[AgentToolExecutor] = None,
    ) -> str:
        """
        Answer a follow-up question with web search and optional management tools.

        When tool_executor is provided, Claude can call management tools
        (add_interest, remove_interest, set_interests, get_interests,
        update_delivery_time) to actually modify the user's environment.
        The agentic loop runs until Claude returns end_turn or the safety
        cap of 5 iterations is reached.

        Args:
            question: The user's message.
            recent_context: Recent conversation context for follow-ups.
            tool_executor: If provided, enables management tool use.

        Returns:
            Answer string (text from Claude's final response).
        """
        try:
            logger.info(f"Answering question: {question[:80]}...")

            today = date.today().strftime("%Y-%m-%d")
            user_content = FOLLOWUP_USER_PROMPT.format(
                question=question,
                recent_context=recent_context or "(no recent conversation context)",
                today=today,
            )
            messages = [{"role": "user", "content": user_content}]
            extra_tools = MANAGEMENT_TOOLS if tool_executor else None

            response = None
            for _ in range(5):  # safety cap — prevents runaway loops
                response = self._call_claude(
                    messages=messages,
                    max_tokens=settings.MAX_TOKENS_FOLLOWUP,
                    extra_tools=extra_tools,
                )

                if response.stop_reason != "tool_use" or not tool_executor:
                    break

                # Execute all pending custom tool calls
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = tool_executor.execute(block.name, block.input)
                        logger.info(f"Tool '{block.name}' → {result[:80]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                if not tool_results:
                    break
                messages.append({"role": "user", "content": tool_results})

            logger.info("Follow-up answer generated")
            return self._extract_text(response)

        except APIError as e:
            logger.error(f"Anthropic API error answering question: {e}")
            return "Sorry, I couldn't search for an answer right now. Please try again."
        except Exception as e:
            logger.error(f"Unexpected error answering question: {e}")
            return "Sorry, something went wrong. Please try again."

    def get_topic_news(self, topic: str) -> str:
        """
        Get on-demand news for a specific topic.

        Args:
            topic: The topic to search for (e.g., "climate tech", "OpenAI").

        Returns:
            Compact news summary with source URLs.
        """
        try:
            logger.info(f"On-demand news request for: {topic}")

            today = date.today().strftime("%Y-%m-%d")
            response = self._call_claude(
                messages=[{"role": "user", "content": ONDEMAND_USER_PROMPT.format(topic=topic, today=today)}],
                max_tokens=settings.MAX_TOKENS_ONDEMAND,
            )
            result = self._extract_text(response)

            logger.info(f"On-demand news generated for: {topic}")
            return result

        except APIError as e:
            logger.error(f"Anthropic API error for on-demand topic news: {e}")
            return f"Sorry, I couldn't fetch news about '{topic}' right now. Please try again."
        except Exception as e:
            logger.error(f"Unexpected error getting topic news: {e}")
            return f"Sorry, something went wrong fetching news about '{topic}'."

    @staticmethod
    def _extract_text(response) -> str:
        """
        Extract all text blocks from a Claude API response.
        Non-text blocks (tool_use, tool_result) are skipped — we only want
        Claude's final text output, not the intermediate tool calls.
        """
        return "\n".join(
            block.text
            for block in response.content
            if block.type == "text"
        )


# Module-level singleton
claude_client = ClaudeClient()
