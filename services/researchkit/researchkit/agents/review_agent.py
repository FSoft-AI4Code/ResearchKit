"""Review Agent stub -- placeholder for synthetic peer review.

When fully implemented, this agent will:
- Read each section with Memory context and generate reviewer-style feedback
- Assess claim strength (is evidence sufficient?)
- Detect missing citations for unsupported claims
- Validate venue-specific checklists (NeurIPS reproducibility, ACL responsible NLP, etc.)
- Check consistency across abstract, introduction, and conclusion
- Score readability with section-level breakdown
- Validate rebuttal quality (are all concerns addressed? tone appropriate?)
- Generate predicted reviewer scores with rationale
"""

from __future__ import annotations

from typing import Any

from researchkit.agents.base import Artifact, Result, SubAgent, Task, TaskStatus
from researchkit.memory.memory import Memory
from researchkit.providers.base import LLMProvider


class ReviewAgent(SubAgent):
    name = "review_agent"
    description = "Simulated peer review, quality assurance, and venue checklist validation"

    REQUIRED_TOOLS = [
        "CitationValidatorTool",
        "ChecklistTool",
    ]

    def __init__(self, provider: LLMProvider):
        super().__init__(provider)

    async def plan(self, task: Task, memory: Memory) -> dict[str, Any]:
        return {
            "status": "stub",
            "steps": [
                "1. Read full paper with Memory context",
                "2. Section-by-section review (strengths, weaknesses, questions)",
                "3. Claim strength analysis with evidence assessment",
                "4. Missing citation detection",
                "5. Venue checklist validation",
                "6. Consistency check (abstract vs intro vs conclusion)",
                "7. Generate simulated review with predicted scores",
            ],
            "note": "Review Agent is not yet implemented. This is a planned execution flow.",
        }

    async def execute(self, task: Task, memory: Memory) -> Result:
        user_msg = task.context.get("user_message", "review request")

        return Result(
            status=TaskStatus.COMPLETED,
            content=(
                f"**Review Agent** received your request: \"{user_msg}\"\n\n"
                "This agent is currently a placeholder. When fully implemented, it will:\n\n"
                "1. **Section-by-Section Review** -- Read each section with full Memory context "
                "and generate reviewer-style feedback: strengths, weaknesses, questions\n"
                "2. **Claim Strength Analysis** -- For each claim, assess whether evidence "
                "(experiments, citations, proofs) is sufficient\n"
                "3. **Missing Citation Detection** -- Scan for claims that should be cited "
                "but aren't, delegate to Research Agent if evidence is needed\n"
                "4. **Venue Checklist Validation** -- Validate against venue-specific checklists "
                "(NeurIPS reproducibility, ACL responsible NLP, etc.)\n"
                "5. **Consistency Checking** -- Cross-reference claims in abstract vs introduction "
                "vs conclusion, flag contradictions or drift\n"
                "6. **Simulated Scores** -- Generate predicted reviewer scores (1-10) with "
                "rationale and confidence calibration"
            ),
            artifacts=[
                Artifact(
                    type="placeholder_notice",
                    content="Review Agent tools are defined but deep analysis is not yet implemented.",
                )
            ],
            confidence=0.0,
            needs_human_review=True,
        )
