"""Agent response contracts shared by mock and future live adapters."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .dashboard import DashboardSpec


class AgentError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    retryable: bool = False


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["needs_clarification", "awaiting_approval", "completed", "failed"]
    message: str
    draft: DashboardSpec | None = None
    error: AgentError | None = None
