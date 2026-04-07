from researchkit.agents.base import Result, SubAgent, SubAgentContext, Task
from researchkit.memory.schema import PaperMemory


class FigureAgent(SubAgent):
    name = "Figure Agent"
    description = "Code execution for figures, TikZ generation, data visualization"

    async def execute(
        self,
        task: Task,
        memory: PaperMemory | None,
        context: SubAgentContext | None = None,
    ) -> Result:
        return Result(
            status="placeholder",
            content=(
                "**Figure Agent** is coming soon.\n\n"
                "Planned capabilities:\n"
                "- Data-to-plots via Python (matplotlib, seaborn, plotly)\n"
                "- TikZ / pgfplots generation from natural language\n"
                "- Architecture diagram generation\n"
                "- Figure captioning following venue conventions\n"
                "- Style consistency across all paper figures\n\n"
                f"*Your request:* {task.description}"
            ),
        )
