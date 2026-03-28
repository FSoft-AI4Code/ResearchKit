"""Pydantic schema for .researchkit/config.yaml."""

from pydantic import BaseModel, Field


class VenueConfig(BaseModel):
    name: str = ""
    type: str = "long-paper"
    page_limit: int = 8
    required_sections: list[str] = Field(default_factory=list)
    anonymous: bool = True


class ProjectConfig(BaseModel):
    name: str = "Untitled Paper"
    venue: str = ""
    type: str = "long-paper"
    page_limit: int = 8
    anonymous: bool = True


class ProvidersConfig(BaseModel):
    """Per-agent model names. Each value is a model string like 'claude-sonnet-4'."""

    main_agent: str = "claude-sonnet-4-20250514"
    research_agent: str = "claude-sonnet-4-20250514"
    figure_agent: str = "claude-sonnet-4-20250514"
    review_agent: str = "claude-sonnet-4-20250514"
    api_key: str | None = None
    base_url: str | None = None


class ResearchAgentConfig(BaseModel):
    sources: list[str] = Field(
        default_factory=lambda: ["semantic_scholar", "arxiv"]
    )
    search_strategy: str = "survey_first"
    read_depth: str = "full"
    citation_graph_hops: int = 2
    max_papers: int = 50
    recency_weight: float = 0.7


class FigureAgentConfig(BaseModel):
    default_style: str = "matplotlib"
    color_palette: str = "colorblind_safe"
    output_format: str = "pdf"
    save_scripts: bool = True


class ReviewAgentConfig(BaseModel):
    simulate_reviewers: int = 3
    venue_checklist: str = "auto"
    severity_threshold: str = "minor"


class AgentsConfig(BaseModel):
    research: ResearchAgentConfig = Field(default_factory=ResearchAgentConfig)
    figure: FigureAgentConfig = Field(default_factory=FigureAgentConfig)
    review: ReviewAgentConfig = Field(default_factory=ReviewAgentConfig)


class OverleafIntegration(BaseModel):
    project_id: str = ""
    sync_mode: str = "bidirectional"


class IntegrationsConfig(BaseModel):
    overleaf: OverleafIntegration = Field(default_factory=OverleafIntegration)


class ResearchKitConfig(BaseModel):
    """Top-level configuration schema matching .researchkit/config.yaml."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
