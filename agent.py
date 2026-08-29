import json
import time

import together
from dotenv import load_dotenv
from together import Together

from tools import (
    check_item_compliance,
    list_items
)


# ============================================================
# Configuration
# ============================================================

load_dotenv()

MODEL_NAME = "Qwen/Qwen3.5-9B"

# Make evaluation runs as stable as reasonably possible.
MODEL_TEMPERATURE = 0
MODEL_SEED = 42

# Prevent an agent from looping indefinitely.
MAX_AGENT_STEPS = 8

# Retry delays for temporary API / network failures.
# This means:
# initial request
# -> retry after 1 sec
# -> retry after 2 sec
# -> retry after 4 sec
RETRY_DELAYS = [1, 2, 4]


client = Together()


# ============================================================
# Tool definitions shown to the LLM
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_items",
            "description": (
                "List building items of a specified type. "
                "Use this tool whenever the user asks about a category "
                "or multiple building items and their exact item IDs "
                "are not already given. "
                "For example, use it before checking all doors "
                "or all offices."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {
                        "type": "string",
                        "description": (
                            "The category of building items to retrieve."
                        ),
                        "enum": [
                            "all",
                            "door",
                            "office",
                            "meeting_room"
                        ]
                    }
                },
                "required": [
                    "item_type"
                ],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "check_item_compliance",
            "description": (
                "Check one specific building item against all "
                "applicable fictional demonstration compliance rules. "
                "The deterministic Python result is the source of truth "
                "for PASS, FAIL, UNKNOWN, and missing-item outcomes. "
                "Use an exact item ID such as Door-01 or Room-101."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": (
                            "The exact building item ID, "
                            "for example Door-01 or Room-101."
                        )
                    }
                },
                "required": [
                    "item_id"
                ],
                "additionalProperties": False
            }
        }
    }
]


# ============================================================
# System prompt
# ============================================================

SYSTEM_PROMPT = """
You are a small AI agent for analysing a demonstration
architecture, engineering and construction (AEC) building dataset.

You have access to deterministic Python tools.

Your responsibilities are:
- understand the user's request,
- decide which tools are required,
- gather sufficient evidence,
- and explain the tool results clearly.

IMPORTANT RULES

1. Never invent building items, dimensions, locations,
   compliance rules, or compliance results.

2. The Python tools are the source of truth for factual
   building information and compliance decisions.

3. If the user provides one exact item ID, such as Door-01
   or Room-101, use check_item_compliance directly when
   compliance information is requested.

4. If the user asks about a category or multiple items,
   such as:
   - all doors,
   - which doors fail,
   - which offices pass,
   first use list_items to discover the actual items
   in that category.

5. After discovering a group of relevant items,
   check EVERY relevant item needed to answer the question.

6. Do not stop after checking only one item when the user's
   request concerns multiple items.

7. Never perform the numerical compliance decision yourself.
   Use check_item_compliance.

8. If a tool reports that an item does not exist,
   report that it could not be found.
   Do not invent substitute data.

9. Clearly distinguish PASS, FAIL, UNKNOWN, and not-found cases.

10. Continue using tools until you have enough evidence
    to answer the full user request.

11. Keep the final answer concise and evidence-based.

12. The compliance rules in this repository are fictional
    demonstration rules. They are not real statutory
    building regulations and must not be presented as legal advice.
"""


# ============================================================
# Together API helper
# ============================================================

TRANSIENT_API_ERRORS = (
    together.APIConnectionError,
    together.APITimeoutError,
    together.RateLimitError,
    together.InternalServerError
)


def call_model(messages, tools=None):
    """
    Call Together AI with a small retry policy.

    Temporary network, timeout, rate-limit, and server errors
    are retried. Authentication errors and invalid requests
    are not retried because repeating them would not fix them.
    """

    for attempt in range(
        len(RETRY_DELAYS) + 1
    ):

        try:

            request_args = {
                "model": MODEL_NAME,
                "messages": messages,

                # Reduce sampling randomness.
                "temperature": MODEL_TEMPERATURE,

                # Improve repeatability across evaluation runs.
                "seed": MODEL_SEED,

                # We only need tool orchestration here.
                "reasoning": {
                    "enabled": False
                }
            }

            if tools is not None:
                request_args["tools"] = tools

            return client.chat.completions.create(
                **request_args
            )

        except TRANSIENT_API_ERRORS as error:

            # No retry slots remain.
            if attempt >= len(RETRY_DELAYS):
                print(
                    "\nAPI request failed after all retries."
                )
                raise

            wait_seconds = RETRY_DELAYS[
                attempt
            ]

            print(
                "\nTemporary Together API error:"
            )

            print(
                f"{type(error).__name__}: {error}"
            )

            print(
                f"Retrying in "
                f"{wait_seconds} second(s)..."
            )

            time.sleep(
                wait_seconds
            )


# ============================================================
# Tool dispatcher
# ============================================================

def execute_tool(
    function_name,
    arguments
):
    """
    Execute the Python function requested by the LLM.
    """

    if function_name == "list_items":

        return list_items(
            arguments["item_type"]
        )

    if function_name == "check_item_compliance":

        return check_item_compliance(
            arguments["item_id"]
        )

    return {
        "error": (
            f"Unknown tool: "
            f"{function_name}"
        )
    }


# ============================================================
# Agent
# ============================================================

def run_agent(
    user_message,
    return_trace=False
):
    """
    Run a multi-step tool-using AI agent.

    The loop continues until:
    - the model produces a final answer without requesting tools, or
    - MAX_AGENT_STEPS is reached.

    When return_trace=True, the function returns:
    {
        "answer": ...,
        "trace": [...],
        "steps": ...
    }
    """

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    trace = []

    for step in range(
        MAX_AGENT_STEPS
    ):

        print(
            "\n"
            + "=" * 50
        )

        print(
            f"Agent Step {step + 1}"
        )

        print(
            "=" * 50
        )

        # ------------------------------------------------
        # Ask the model what to do next
        # ------------------------------------------------

        response = call_model(
            messages=messages,
            tools=TOOLS
        )

        assistant_message = (
            response
            .choices[0]
            .message
        )

        tool_calls = (
            assistant_message.tool_calls
        )

        # ------------------------------------------------
        # No tool call = final answer
        # ------------------------------------------------

        if not tool_calls:

            print(
                "\nAgent has enough information."
            )

            final_result = {
                "answer": (
                    assistant_message.content
                    or ""
                ),
                "trace": trace,
                "steps": step + 1
            }

            if return_trace:
                return final_result

            return final_result[
                "answer"
            ]

        # ------------------------------------------------
        # Save assistant tool-call message
        # ------------------------------------------------

        messages.append(
            {
                "role": "assistant",

                "content": (
                    assistant_message.content
                    or ""
                ),

                "tool_calls": [
                    tool_call.model_dump()
                    for tool_call
                    in tool_calls
                ]
            }
        )

        # ------------------------------------------------
        # Execute every requested tool
        # ------------------------------------------------

        for tool_call in tool_calls:

            function_name = (
                tool_call
                .function
                .name
            )

            # Parse arguments safely.
            try:

                arguments = json.loads(
                    tool_call
                    .function
                    .arguments
                )

            except json.JSONDecodeError:

                arguments = {}

                tool_result = {
                    "error": (
                        "The model returned "
                        "invalid JSON tool arguments."
                    )
                }

            else:

                print(
                    "\nTool selected:"
                )

                print(
                    function_name
                )

                print(
                    "Arguments:"
                )

                print(
                    arguments
                )

                try:

                    tool_result = (
                        execute_tool(
                            function_name,
                            arguments
                        )
                    )

                except Exception as error:

                    tool_result = {
                        "error": (
                            "Tool execution failed: "
                            f"{type(error).__name__}: "
                            f"{error}"
                        )
                    }

            print(
                "Tool result:"
            )

            print(
                tool_result
            )

            # ------------------------------------------------
            # Record trace
            # ------------------------------------------------

            trace.append(
                {
                    "step": step + 1,

                    "tool": (
                        function_name
                    ),

                    "arguments": (
                        arguments
                    ),

                    "result": (
                        tool_result
                    )
                }
            )

            # ------------------------------------------------
            # Return tool output to the LLM
            # ------------------------------------------------

            messages.append(
                {
                    "role": "tool",

                    "tool_call_id": (
                        tool_call.id
                    ),

                    "name": (
                        function_name
                    ),

                    "content": json.dumps(
                        tool_result,
                        ensure_ascii=False
                    )
                }
            )

    # ====================================================
    # Safety stop
    # ====================================================

    final_result = {
        "answer": (
            "The agent stopped because it "
            "reached the maximum number "
            "of allowed steps."
        ),

        "trace": trace,

        "steps": MAX_AGENT_STEPS
    }

    if return_trace:
        return final_result

    return final_result[
        "answer"
    ]