"""Agent registry: maps StepId to agent class, instantiates agents for projects."""

from __future__ import annotations

from mycroft.shared.protocol import StepId
from mycroft.server.agents.base import BaseAgent
from mycroft.server.agents.scoper import IdeaScopingAgent
from mycroft.server.agents.product_manual import ManualUseCaseAgent
from mycroft.server.agents.product_auto import AutoUseCaseAgent
from mycroft.server.agents.architect_manual import ManualArchitectAgent
from mycroft.server.agents.architect_auto import AutoArchitectAgent
from mycroft.server.state.project import ProjectState

AGENT_MAP: dict[StepId, type[BaseAgent]] = {
    StepId.IDEA_SCOPING: IdeaScopingAgent,
    StepId.USE_CASES_MANUAL: ManualUseCaseAgent,
    StepId.USE_CASES_AUTO: AutoUseCaseAgent,
    StepId.ARCHITECTURE_MANUAL: ManualArchitectAgent,
    StepId.ARCHITECTURE_AUTO: AutoArchitectAgent,
}


def get_agent(project: ProjectState) -> BaseAgent:
    """Get the agent for the project's current step."""
    agent_cls = AGENT_MAP[project.current_step]
    return agent_cls(project)
