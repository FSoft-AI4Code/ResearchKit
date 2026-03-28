from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from researchkit.memory.schema import PaperMemory


@dataclass
class Task:
    type: str
    description: str
    context: dict = field(default_factory=dict)


@dataclass
class Result:
    status: str  # "completed" | "placeholder"
    content: str
    artifacts: list[dict] = field(default_factory=list)


class SubAgent(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, task: Task, memory: PaperMemory | None) -> Result: ...
