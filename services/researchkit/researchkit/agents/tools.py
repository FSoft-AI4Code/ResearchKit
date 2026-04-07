AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "str_replace_editor",
            "description": (
                "View and edit files inside the configured workspace. "
                "Use this for reading directories or files, creating files, "
                "replacing unique strings, inserting text, and undoing the last edit. "
                "`create` is only for brand-new files. If an edit fails, use `view` on the "
                "same path before trying another edit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
                        "description": "Editor command to run",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Path to a file or directory inside the configured workspace. "
                            "Prefer workspace-relative paths; absolute workspace "
                            "paths are also allowed."
                        ),
                    },
                    "file_text": {
                        "type": "string",
                        "description": (
                            "Required for `create`; full file contents to write for a new file"
                        ),
                    },
                    "view_range": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": (
                            "Optional line range for `view`, formatted as [start_line, end_line]. "
                            "Use -1 for the end line to read through EOF."
                        ),
                    },
                    "old_str": {
                        "type": "string",
                        "description": (
                            "Required for `str_replace`; must match exactly once in the current file"
                        ),
                    },
                    "new_str": {
                        "type": "string",
                        "description": (
                            "Replacement text for `str_replace`, or inserted text for `insert`"
                        ),
                    },
                    "insert_line": {
                        "type": "integer",
                        "description": (
                            "Required for `insert`; zero-based line index where "
                            "new text is inserted"
                        ),
                    },
                },
                "required": ["command", "path"],
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
