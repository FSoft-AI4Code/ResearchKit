"""Real literature search and citation management for ResearchKit.

Provides API clients for Semantic Scholar, OpenAlex, and arXiv, plus
unified search with deduplication and BibTeX generation.

Adopted from https://github.com/aiming-lab/AutoResearchClaw/tree/main/researchclaw/literature
"""

from researchkit.literature.models import Author, Paper
from researchkit.literature.search import papers_to_bibtex, search_papers
from researchkit.literature.verify import (
    CitationResult,
    VerificationReport,
    VerifyStatus,
    verify_citations,
)

__all__ = [
    "Author",
    "CitationResult",
    "Paper",
    "VerificationReport",
    "VerifyStatus",
    "papers_to_bibtex",
    "search_papers",
    "verify_citations",
]
