AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a shell command in the project workspace. Use this for reading files, "
                "searching, refactoring, formatting, and other codebase-style operations "
                "on paper files. "
                "Prefer short deterministic commands and avoid interactive shells."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 300,
                        "description": "Optional command timeout in seconds",
                    },
                    "working_subdir": {
                        "type": "string",
                        "description": (
                            "Optional subdirectory inside workspace to run command in"
                        ),
                    },
                    "expect_file_changes": {
                        "type": "boolean",
                        "description": (
                            "Set true for edit/refactor commands that should modify files"
                        ),
                    },
                },
                "required": ["command"],
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
