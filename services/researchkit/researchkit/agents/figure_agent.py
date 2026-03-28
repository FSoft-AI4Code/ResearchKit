"""Figure Agent stub -- placeholder for visual asset generation via code execution.

When fully implemented, this agent will:
- Generate publication-quality plots from data (matplotlib, seaborn, plotly)
- Create TikZ/pgfplots diagrams from natural language descriptions
- Convert whiteboard sketches to structured diagrams
- Ensure style consistency across all figures (colors, fonts, sizing)
- Generate descriptive captions following venue conventions
- Check accessibility (colorblind-safe palettes, contrast, font sizes)
- Save generation scripts for reproducible re-runs
"""

from __future__ import annotations

from typing import Any

from researchkit.agents.base import Artifact, Result, SubAgent, Task, TaskStatus
from researchkit.memory.memory import Memory
from researchkit.providers.base import LLMProvider


class FigureAgent(SubAgent):
    name = "figure_agent"
    description = "Code execution for figures, plots, and TikZ diagram generation"

    REQUIRED_TOOLS = [
        "PythonExecutorTool",
        "TikZCompilerTool",
        "ExternalAPITool",
    ]

    def __init__(self, provider: LLMProvider):
        super().__init__(provider)

    async def plan(self, task: Task, memory: Memory) -> dict[str, Any]:
        return {
            "status": "stub",
            "steps": [
                "1. Read Memory for experiment data location and style profile",
                "2. Generate Python/TikZ code for the requested figure",
                "3. Execute code in sandbox",
                "4. Generate LaTeX include block and caption",
                "5. Save generation script for re-runs",
            ],
            "note": "Figure Agent is not yet implemented. This is a planned execution flow.",
        }

    async def execute(self, task: Task, memory: Memory) -> Result:
        user_msg = task.context.get("user_message", "figure request")

        return Result(
            status=TaskStatus.COMPLETED,
            content=(
                f"**Figure Agent** received your request: \"{user_msg}\"\n\n"
                "This agent is currently a placeholder. When fully implemented, it will:\n\n"
                "1. **Data Analysis** -- Read experiment data (CSV, JSON) and Memory style profile\n"
                "2. **Code Generation** -- Write Python (matplotlib/seaborn) or TikZ code "
                "for the requested visualization\n"
                "3. **Execution** -- Run the code in a sandboxed environment and produce "
                "PDF/PNG output in the figures/ directory\n"
                "4. **LaTeX Integration** -- Generate a complete \\\\begin{{figure}} environment "
                "with \\\\includegraphics, caption, and label\n"
                "5. **Style Consistency** -- Apply the paper's color scheme, fonts, and sizing "
                "from the style profile\n"
                "6. **Script Saving** -- Save the generation script to figures/scripts/ for "
                "reproducible re-runs with updated data"
            ),
            artifacts=[
                Artifact(
                    type="placeholder_notice",
                    content="Figure Agent tools are defined but sandbox execution is not yet available.",
                )
            ],
            confidence=0.0,
            needs_human_review=True,
        )
