import json

from dotenv import load_dotenv
from together import Together

from tools import (
    check_item_compliance,
    list_items
)

load_dotenv()

MODEL_NAME = "Qwen/Qwen3.5-9B"

client = Together()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_items",
            "description": (
                "List building items of a specified type. "
                "Use this tool when you need to discover "
                "which items exist in the building."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {
                        "type": "string",
                        "description": (
                            "The type of building item to list."
                        ),
                        "enum": [
                            "all",
                            "door",
                            "office",
                            "meeting_room"
                        ]
                    }
                },
                "required": ["item_type"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "check_item_compliance",
            "description": (
                "Check whether one specific building item "
                "complies with the fictional demonstration rules. "
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
                "required": ["item_id"]
            }
        }
    }
]


SYSTEM_PROMPT = """
You are an AI agent for analysing a small demonstration building.

You have tools for:
- listing building items
- checking individual items for compliance

When answering questions:

1. Use tools whenever factual building information is required.

2. If the user asks about multiple building items but does not
   provide their exact IDs, first discover the relevant items
   using list_items.

3. Use check_item_compliance for compliance decisions.

4. Never calculate or invent compliance results yourself.
   Treat Python tool outputs as the source of truth.

5. You may call multiple tools when necessary.

6. Continue gathering information until you have enough evidence
   to answer the user's question.

7. Clearly distinguish PASS, FAIL, and UNKNOWN.

8. The rules in this project are fictional demonstration rules
   and are not real building regulations.

Keep the final answer concise and evidence-based.
"""


def execute_tool(function_name, arguments):

    if function_name == "list_items":
        return list_items(
            arguments["item_type"]
        )

    if function_name == "check_item_compliance":
        return check_item_compliance(
            arguments["item_id"]
        )

    return {
        "error": f"Unknown tool: {function_name}"
    }

def run_agent(user_message, return_trace=False):

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

    max_steps = 8

    trace = []

    for step in range(max_steps):

        print(
            f"\n========== Agent Step {step + 1} =========="
        )

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS
        )

        assistant_message = (
            response.choices[0].message
        )

        tool_calls = assistant_message.tool_calls

        # 没有更多工具调用：
        # Agent 准备给最终答案
        if not tool_calls:

            print("\nAgent has enough information.")

            result = {
                "answer": assistant_message.content,
                "trace": trace,
                "steps": step + 1
            }

            if return_trace:
                return result

            return assistant_message.content

        messages.append(
            {
                "role": "assistant",
                "content": (
                    assistant_message.content or ""
                ),
                "tool_calls": [
                    tool_call.model_dump()
                    for tool_call in tool_calls
                ]
            }
        )

        for tool_call in tool_calls:

            function_name = (
                tool_call.function.name
            )

            arguments = json.loads(
                tool_call.function.arguments
            )

            print("\nTool selected:")
            print(function_name)

            print("Arguments:")
            print(arguments)

            result = execute_tool(
                function_name,
                arguments
            )

            print("Tool result:")
            print(result)

            # 新增：
            # 保存这一次工具调用
            trace.append(
                {
                    "step": step + 1,
                    "tool": function_name,
                    "arguments": arguments,
                    "result": result
                }
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False
                    )
                }
            )

    final_result = {
        "answer": (
            "The agent stopped because it reached "
            "the maximum number of steps."
        ),
        "trace": trace,
        "steps": max_steps
    }

    if return_trace:
        return final_result

    return final_result["answer"]

if __name__ == "__main__":

    answer = run_agent(
        "Is Door-99 compliant?"
    )

    print("\n")
    print("=" * 50)
    print("FINAL ANSWER")
    print("=" * 50)
    print(answer)