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


@dataclass
class SubAgentContext:
    project_id: str | None = None
    workspace_path: str | None = None
    file_path: str | None = None
    selected_text: str | None = None
    cursor_line: int | None = None
    line_from: int | None = None
    line_to: int | None = None
    tool_output_max_chars: int = 12000


class SubAgent(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(
        self,
        task: Task,
        memory: PaperMemory | None,
        context: SubAgentContext | None = None,
    ) -> Result: ...
