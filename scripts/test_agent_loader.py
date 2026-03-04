"""
Smoke test for the AgentLoader.

Verifies that all three markdown files can be read and assembled
into a system prompt without needing any API keys or a running bot.

Usage:
    python scripts/test_agent_loader.py

Run from the project root directory.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent_loader import AgentLoader


def main():
    print("=" * 60)
    print("AgentLoader Smoke Test")
    print("=" * 60)

    loader = AgentLoader(agents_dir="0. Agents")

    # List available agents
    agents = loader.list_agents()
    print(f"\nAvailable agents: {agents}")

    if not agents:
        print("\nERROR: No agents found. Check that '0. Agents/' exists and")
        print("contains subdirectories with SOUL.md, RULES.md, SKILLS.md.")
        sys.exit(1)

    # Load and display each agent's system prompt
    for agent_name in agents:
        print(f"\n{'─' * 60}")
        print(f"Agent: {agent_name}")
        print(f"{'─' * 60}")

        try:
            prompt = loader.get_system_prompt(agent_name)
            print(f"System prompt length: {len(prompt)} characters")
            print(f"\nFirst 400 characters:")
            print(prompt[:400])
            print("...")

            # Test reload (cache invalidation)
            reloaded = loader.reload_agent(agent_name)
            assert reloaded == prompt, "Reloaded prompt differs from original!"
            print("\nCache reload: OK")

        except FileNotFoundError as e:
            print(f"\nERROR: {e}")
            sys.exit(1)

    print(f"\n{'=' * 60}")
    print("All agents loaded successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
