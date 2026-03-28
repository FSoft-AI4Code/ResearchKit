"""Base agent abstractions -- SubAgent ABC, Task, and Result models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from researchkit.memory.memory import Memory
from researchkit.providers.base import LLMProvider


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Artifact:
    type: str  # "bibtex_entries", "evidence_report", "figure", "review", "latex_edit", etc.
    content: str = ""
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """Structured task sent from Main Agent to a Sub-Agent."""

    action: str  # e.g. "find_evidence_for_claim", "generate_figure", "review_section"
    context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """Structured result returned from a Sub-Agent to Main Agent."""

    status: TaskStatus = TaskStatus.COMPLETED
    content: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = False
    error: str = ""


class SubAgent(ABC):
    """Base class for specialized sub-agents (Research, Figure, Review)."""

    name: str
    description: str

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    @abstractmethod
    async def plan(self, task: Task, memory: Memory) -> dict[str, Any]:
        """Create an execution plan for the given task."""
        ...

    @abstractmethod
    async def execute(self, task: Task, memory: Memory) -> Result:
        """Execute the task and return results."""
        ...

    async def validate(self, result: Result) -> Result:
        """Optional validation step. Override in subclasses for quality checks."""
        return result
