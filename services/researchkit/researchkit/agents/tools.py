AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "paraphrase_text",
            "description": (
                "Rewrite the selected LaTeX text to improve clarity and readability "
                "while preserving technical meaning, citations, and mathematical notation. "
                "Return the rewritten text in LaTeX format."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "rewritten_text": {
                        "type": "string",
                        "description": "The paraphrased text in LaTeX format",
                    },
                },
                "required": ["rewritten_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fix_grammar",
            "description": (
                "Correct grammar and style issues in the selected LaTeX text. "
                "Focus on academic writing conventions: fix hedging, passive voice overuse, "
                "vague claims, and grammatical errors. Return the corrected text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "corrected_text": {
                        "type": "string",
                        "description": "The grammar-corrected text in LaTeX format",
                    },
                    "changes_made": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Brief list of changes made",
                    },
                },
                "required": ["corrected_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_section",
            "description": (
                "Draft a LaTeX section based on the given outline, topic, or instructions. "
                "Use the paper's memory context (structure, style, venue constraints) "
                "to ensure consistency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section_content": {
                        "type": "string",
                        "description": "The drafted section content in LaTeX format",
                    },
                },
                "required": ["section_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "format_bibtex",
            "description": (
                "Normalize and format BibTeX entries. Fix formatting, resolve duplicate keys, "
                "standardize field ordering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "formatted_bibtex": {
                        "type": "string",
                        "description": "The normalized BibTeX entries",
                    },
                },
                "required": ["formatted_bibtex"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_subagent",
            "description": (
                "Delegate a task to a specialized sub-agent when the request requires "
                "deep capabilities beyond inline editing. Use this for: "
                "literature search/related work (research), figure/chart generation (figure), "
                "or paper review/quality checking (review)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "enum": ["research", "figure", "review"],
                        "description": "Which sub-agent to delegate to",
                    },
                    "task_description": {
                        "type": "string",
                        "description": "What the sub-agent should do",
                    },
                },
                "required": ["agent_type", "task_description"],
            },
        },
    },
]
