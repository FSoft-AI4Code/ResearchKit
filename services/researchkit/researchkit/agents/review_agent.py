from researchkit.agents.base import Result, SubAgent, SubAgentContext, Task
from researchkit.memory.schema import PaperMemory


class ReviewAgent(SubAgent):
    name = "Review Agent"
    description = "Simulated peer review, claim strength analysis, venue checklist validation"

    async def execute(
        self,
        task: Task,
        memory: PaperMemory | None,
        context: SubAgentContext | None = None,
    ) -> Result:
        return Result(
            status="placeholder",
            content=(
                "**Review Agent** is coming soon.\n\n"
                "Planned capabilities:\n"
                "- Section-by-section simulated peer review\n"
                "- Claim strength analysis with evidence assessment\n"
                "- Missing citation detection\n"
                "- Venue checklist validation (NeurIPS, ACL, AAAI, etc.)\n"
                "- Consistency checking across abstract, intro, and conclusion\n"
                "- Predicted reviewer scores with rationale\n\n"
                f"*Your request:* {task.description}"
            ),
        )
