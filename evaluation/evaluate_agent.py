import json
from datetime import datetime, timezone
from pathlib import Path

from agent import MODEL_NAME, run_agent


BASE_DIR = Path(__file__).resolve().parent
TEST_CASES_FILE = BASE_DIR / "test_cases.json"
RESULTS_FILE = BASE_DIR / "results.json"


def load_test_cases():
    """
    Load all agent evaluation cases from test_cases.json.
    """
    with open(
        TEST_CASES_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def get_compliance_calls(trace):
    """
    Extract all check_item_compliance calls
    from an agent execution trace.
    """
    return [
        event
        for event in trace
        if event["tool"] == "check_item_compliance"
    ]


def evaluate_case(test_case):
    """
    Run one evaluation case and check whether the agent:
    - used required discovery tools,
    - checked the expected items,
    - returned the expected deterministic tool outcomes,
    - handled missing items correctly.
    """

    print("\n")
    print("=" * 60)
    print(f"CASE: {test_case['id']}")
    print("=" * 60)

    print("Question:")
    print(test_case["question"])

    # --------------------------------------------------
    # 1. Run the agent
    # --------------------------------------------------

    try:
        agent_result = run_agent(
            test_case["question"],
            return_trace=True
        )

    except Exception as error:

        error_message = (
            f"Agent execution raised "
            f"{type(error).__name__}: {error}"
        )

        print("\nRESULT: FAIL")
        print(f"- {error_message}")

        return {
            "id": test_case["id"],
            "question": test_case["question"],
            "passed": False,
            "errors": [error_message],
            "answer": None,
            "steps": 0,
            "tool_calls": 0,
            "tools_used": []
        }

    trace = agent_result["trace"]

    errors = []

    # --------------------------------------------------
    # 2. Check whether list_items was used when required
    # --------------------------------------------------

    used_list_items = any(
        event["tool"] == "list_items"
        for event in trace
    )

    if (
        test_case.get(
            "requires_list_items",
            False
        )
        and not used_list_items
    ):
        errors.append(
            "Agent should have used list_items."
        )

    # --------------------------------------------------
    # 3. Collect compliance tool calls
    # --------------------------------------------------

    compliance_calls = get_compliance_calls(
        trace
    )

    checked_items = [
        call["arguments"]["item_id"]
        for call in compliance_calls
    ]

    expected_items = test_case.get(
        "expected_checked_items",
        []
    )

    # --------------------------------------------------
    # 4. Check whether all expected items were checked
    # --------------------------------------------------

    for expected_item in expected_items:

        if expected_item not in checked_items:

            errors.append(
                f"Agent did not check "
                f"{expected_item}."
            )

    # --------------------------------------------------
    # 5. Check whether unexpected items were checked
    # --------------------------------------------------

    unexpected_items = [
        item_id
        for item_id in checked_items
        if item_id not in expected_items
    ]

    if unexpected_items:

        errors.append(
            "Agent checked unexpected item(s): "
            + ", ".join(unexpected_items)
        )

    # --------------------------------------------------
    # 6. Check deterministic PASS / FAIL results
    # --------------------------------------------------

    expected_statuses = test_case.get(
        "expected_statuses",
        {}
    )

    for item_id, expected_status in (
        expected_statuses.items()
    ):

        matching_calls = [
            call
            for call in compliance_calls
            if (
                call["arguments"]["item_id"]
                == item_id
            )
        ]

        # Missing calls were already detected above
        if not matching_calls:
            continue

        actual_status = matching_calls[-1][
            "result"
        ].get("overall_status")

        if actual_status != expected_status:

            errors.append(
                f"{item_id}: expected "
                f"{expected_status}, "
                f"got {actual_status}."
            )

    # --------------------------------------------------
    # 7. Check missing-item behaviour
    # --------------------------------------------------

    if test_case.get(
        "expected_error",
        False
    ):

        found_error = any(
            "error" in call["result"]
            for call in compliance_calls
        )

        if not found_error:

            errors.append(
                "Expected missing-item error "
                "was not returned."
            )

    # --------------------------------------------------
    # 8. Determine PASS / FAIL
    # --------------------------------------------------

    passed = len(errors) == 0

    print("\nFinal answer:")
    print(agent_result["answer"])

    print("\nTools used:")

    for event in trace:

        print(
            f"- {event['tool']} "
            f"{event['arguments']}"
        )

    if passed:

        print("\nRESULT: PASS")

    else:

        print("\nRESULT: FAIL")

        for error in errors:

            print(f"- {error}")

    # --------------------------------------------------
    # 9. Save a compact tool trace
    # --------------------------------------------------

    tools_used = [
        {
            "step": event["step"],
            "tool": event["tool"],
            "arguments": event["arguments"]
        }
        for event in trace
    ]

    return {
        "id": test_case["id"],
        "question": test_case["question"],
        "passed": passed,
        "errors": errors,
        "answer": agent_result["answer"],
        "steps": agent_result["steps"],
        "tool_calls": len(trace),
        "tools_used": tools_used
    }


def save_results(results):
    """
    Save a machine-readable evaluation summary
    to evaluation/results.json.
    """

    total_count = len(results)

    passed_count = sum(
        result["passed"]
        for result in results
    )

    failed_count = (
        total_count - passed_count
    )

    success_rate = (
        passed_count / total_count
        if total_count > 0
        else 0
    )

    total_tool_calls = sum(
        result["tool_calls"]
        for result in results
    )

    total_agent_steps = sum(
        result["steps"]
        for result in results
    )

    average_tool_calls = (
        total_tool_calls / total_count
        if total_count > 0
        else 0
    )

    average_agent_steps = (
        total_agent_steps / total_count
        if total_count > 0
        else 0
    )

    output = {
        "evaluation_name": (
            "Mini AEC Compliance Agent "
            "Demonstration Evaluation"
        ),

        "model": MODEL_NAME,

        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "scope_note": (
            "This is a small demonstration benchmark. "
            "It evaluates expected tool use and deterministic "
            "tool outcomes; it is not a general measure of "
            "agent reliability or legal compliance accuracy."
        ),

        "summary": {
            "total_cases": total_count,
            "passed_cases": passed_count,
            "failed_cases": failed_count,
            "success_rate": success_rate,

            "total_tool_calls": (
                total_tool_calls
            ),

            "average_tool_calls_per_case": (
                average_tool_calls
            ),

            "total_agent_steps": (
                total_agent_steps
            ),

            "average_agent_steps_per_case": (
                average_agent_steps
            )
        },

        "results": results
    }

    with open(
        RESULTS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

    return output


def main():
    """
    Run all evaluation cases, print a summary,
    and save results.json.
    """

    test_cases = load_test_cases()

    results = [
        evaluate_case(test_case)
        for test_case in test_cases
    ]

    output = save_results(results)

    summary = output["summary"]

    print("\n")
    print("=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    print(
        f"Passed: "
        f"{summary['passed_cases']}/"
        f"{summary['total_cases']}"
    )

    print(
        f"Success rate: "
        f"{summary['success_rate'] * 100:.1f}%"
    )

    print(
        f"Total tool calls: "
        f"{summary['total_tool_calls']}"
    )

    print(
        f"Average tool calls/case: "
        f"{summary['average_tool_calls_per_case']:.2f}"
    )

    print(
        f"Average agent steps/case: "
        f"{summary['average_agent_steps_per_case']:.2f}"
    )

    print(
        f"Results saved to: "
        f"{RESULTS_FILE}"
    )


if __name__ == "__main__":
    main()