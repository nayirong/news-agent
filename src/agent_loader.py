"""
AgentLoader: Reads SOUL.md, RULES.md, and SKILLS.md from the 0. Agents directory
and assembles them into a complete system prompt for Claude.

Design principle: Agent behavior is defined entirely in markdown files.
Changing agent personality, rules, or skills requires ONLY editing those files —
no Python changes needed.

Usage:
    from src.agent_loader import agent_loader

    system_prompt = agent_loader.get_system_prompt("News Agent")
    # Pass system_prompt to Claude as the system parameter
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AgentLoader:
    """
    Loads and assembles agent definition files into a system prompt.

    Directory structure expected:
        <agents_dir>/
            <agent_name>/
                SOUL.md      — personality, tone, values
                RULES.md     — hard constraints
                SKILLS.md    — capabilities and output formats

    The three files are assembled in order: SOUL → RULES → SKILLS,
    separated by double newlines. The result is passed as the Claude
    system prompt.
    """

    REQUIRED_FILES = ["SOUL.md", "RULES.md", "SKILLS.md"]

    def __init__(self, agents_dir: str = "0. Agents"):
        self.agents_dir = agents_dir
        self._cache: dict[str, str] = {}

    def _read_markdown_file(self, file_path: str) -> str:
        """
        Read a markdown file and return its contents.
        Raises FileNotFoundError with a descriptive message if missing.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Agent definition file not found: {file_path}\n"
                f"Expected absolute path: {os.path.abspath(file_path)}\n"
                f"Please create this file to define the agent."
            )
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        logger.debug(f"Loaded agent file: {file_path} ({len(content)} chars)")
        return content

    def load_agent(self, agent_name: str) -> str:
        """
        Load and assemble the system prompt from SOUL.md, RULES.md, SKILLS.md.

        Assembly order: SOUL → RULES → SKILLS
        Each section is separated by a double newline.

        Args:
            agent_name: The name of the agent folder (e.g., "News Agent")

        Returns:
            A single assembled system prompt string.

        Raises:
            FileNotFoundError: If any of the three required files are missing.
        """
        agent_dir = os.path.join(self.agents_dir, agent_name)

        sections = []
        for filename in self.REQUIRED_FILES:
            file_path = os.path.join(agent_dir, filename)
            content = self._read_markdown_file(file_path)
            sections.append(content)

        system_prompt = "\n\n".join(sections)

        logger.info(
            f"Assembled system prompt for agent '{agent_name}': "
            f"{len(system_prompt)} chars from {len(self.REQUIRED_FILES)} files"
        )
        return system_prompt

    def get_system_prompt(self, agent_name: str) -> str:
        """
        Return the assembled system prompt, using in-memory cache.

        Files are read from disk only once per process lifetime.
        To reload after editing markdown files, use reload_agent() or restart.

        Args:
            agent_name: The name of the agent folder.

        Returns:
            Cached or freshly assembled system prompt string.
        """
        if agent_name not in self._cache:
            self._cache[agent_name] = self.load_agent(agent_name)
        return self._cache[agent_name]

    def reload_agent(self, agent_name: str) -> str:
        """
        Force-reload an agent's system prompt from disk, bypassing cache.

        Useful in development after editing SOUL.md, RULES.md, or SKILLS.md
        without restarting the process. Also accessible via /reload command.

        Args:
            agent_name: The name of the agent folder.

        Returns:
            Freshly assembled system prompt string.
        """
        if agent_name in self._cache:
            del self._cache[agent_name]
            logger.info(f"Cache cleared for agent '{agent_name}'")
        return self.get_system_prompt(agent_name)

    def list_agents(self) -> list[str]:
        """
        List all available agents by scanning the agents directory.

        An agent is valid if its directory contains all three required files.

        Returns:
            List of agent names (directory names that have all required files).
        """
        if not os.path.exists(self.agents_dir):
            logger.warning(f"Agents directory not found: {self.agents_dir}")
            return []

        agents = []
        for entry in os.scandir(self.agents_dir):
            if entry.is_dir():
                has_all = all(
                    os.path.exists(os.path.join(entry.path, f))
                    for f in self.REQUIRED_FILES
                )
                if has_all:
                    agents.append(entry.name)
        return sorted(agents)


# Module-level singleton.
# Uses the default "0. Agents" path, relative to wherever the process starts.
# Start the process from the project root directory.
agent_loader = AgentLoader(agents_dir="0. Agents")
