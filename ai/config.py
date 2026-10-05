from functools import cached_property

from crewai import LLM, Task
from crewai.agents.agent_builder.base_agent import BaseAgent

from settings import Config


class AgentConfig:

    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config: dict = "config/agents.yaml"
    tasks_config: dict = "config/tasks.yaml"

    @cached_property
    def llm(self) -> LLM:
        """Build the configured LLM once per crew instance."""
        return LLM(model=Config.OPENAI_MODEL)
