# ResearchKit Roadmap

## Summary

The next phase should build on the current architecture rather than adding parallel systems. The highest-value work is to deepen the existing research workflow, finish the placeholder agents, and tighten the end-to-end writing loop in the editor.

## Near-Term Priorities

### 1. Deepen the Research Agent

What exists now:

- literature search
- citation verification
- BibTeX output
- read-only workspace context

What is missing:

- stronger related-work synthesis tied directly to the current draft
- better paper ranking and grouping for section-level writing tasks
- improved transfer of research artifacts back into the Main Agent workflow

Likely implementation areas:

- `services/researchkit/researchkit/agents/research_agent.py`
- `services/researchkit/researchkit/literature/`
- frontend rendering for richer research artifacts

### 2. Finish the Figure Agent

What exists now:

- delegation hook in the Main Agent
- placeholder `FigureAgent` class

What is missing:

- real execution flow for figure generation
- file outputs and patch/diff integration
- support for code-driven plot generation, TikZ, or diagram assets

Likely implementation areas:

- `services/researchkit/researchkit/agents/figure_agent.py`
- runner integration for controlled figure-generation commands
- frontend handling for non-text artifacts

### 3. Finish the Review Agent

What exists now:

- delegation hook in the Main Agent
- placeholder `ReviewAgent` class

What is missing:

- structured review prompts and rubric outputs
- section-by-section issue reporting
- links between review findings and actionable edits or citations

Likely implementation areas:

- `services/researchkit/researchkit/agents/review_agent.py`
- UI support for review summaries and issue navigation

### 4. Strengthen Memory and Draft Understanding

What exists now:

- section structure
- abstract
- venue hint
- citations
- summary generation

What is missing:

- better extraction of research questions and contributions
- stronger handling of multi-file paper layouts
- richer style and terminology profiling

Likely implementation areas:

- `services/researchkit/researchkit/memory/`

### 5. Improve Workspace and Runner Ergonomics

What exists now:

- guarded editor operations
- runner-backed command execution
- overlay diff capture

What is missing:

- clearer workspace setup guidance in the product
- better handling of nested project directories
- broader command-result UX for execution-heavy flows

Likely implementation areas:

- `services/researchkit/researchkit/agents/main_agent.py`
- `services/researchkit/researchkit/runner/main.py`
- provider settings UI and editor-side action rendering

## Product Direction Defaults

- Keep the Overleaf module thin and let the Python service own agent logic.
- Reuse the existing runner plus patch pipeline instead of introducing a separate execution path.
- Treat the Research Agent as the first fully operational specialized agent and use it as the pattern for Figure and Review.
