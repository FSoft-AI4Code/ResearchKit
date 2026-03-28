from researchkit.agents.base import Result, SubAgent, Task
from researchkit.memory.schema import PaperMemory


class ResearchAgent(SubAgent):
    name = "Research Agent"
    description = "Deep literature discovery with full-paper reading, citation graph traversal"

    async def execute(self, task: Task, memory: PaperMemory | None) -> Result:
        return Result(
            status="placeholder",
            content=(
                "**Research Agent** is coming soon.\n\n"
                "Planned capabilities:\n"
                "- Web search for seed papers and survey papers\n"
                "- Full-paper reading (not just abstracts)\n"
                "- Forward and backward citation graph traversal\n"
                "- Claim-evidence matching\n"
                "- Related work section generation with proper citations\n"
                "- Citation validation (detect hallucinated references)\n\n"
                f"*Your request:* {task.description}"
            ),
        )
