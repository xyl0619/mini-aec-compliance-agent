import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import together

from agent import MAX_AGENT_STEPS, MODEL_NAME, MODEL_SEED, MODEL_TEMPERATURE, run_agent
from mini_aec_agent.exceptions import DataSourceError
from mini_aec_agent.io_utils import atomic_write_text
from mini_aec_agent.json_utils import reject_duplicate_keys, reject_non_finite_number

# ============================================================
# Paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TEST_CASES_FILE = BASE_DIR / "test_cases.json"

RESULTS_FILE = BASE_DIR / "results.json"
MAX_EVALUATION_FILE_BYTES = 4 * 1024 * 1024
MAX_EVALUATION_CASES = 10_000


# ============================================================
# Error categories
# ============================================================

INFRASTRUCTURE_ERRORS = (
    together.APIConnectionError,
    together.APITimeoutError,
    together.RateLimitError,
    together.InternalServerError,
)


# ============================================================
# Load test cases
# ============================================================


def load_test_cases():
    """
    Load the agent evaluation cases.
    """

    try:
        if TEST_CASES_FILE.stat().st_size > MAX_EVALUATION_FILE_BYTES:
            raise DataSourceError(
                "Agent evaluation case file exceeds the safety limit."
            )
        payload = json.loads(
            TEST_CASES_FILE.read_text(encoding="utf-8"),
            parse_constant=reject_non_finite_number,
            object_pairs_hook=reject_duplicate_keys,
        )
    except DataSourceError:
        raise
    except (OSError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise DataSourceError(
            f"Could not load agent evaluation cases: {TEST_CASES_FILE}"
        ) from error
    if (
        not isinstance(payload, list)
        or len(payload) > MAX_EVALUATION_CASES
        or any(
            not isinstance(case, dict)
            or not isinstance(case.get("id"), str)
            or not isinstance(case.get("question"), str)
            or not case["id"].strip()
            or not case["question"].strip()
            or len(case["id"]) > 128
            or len(case["question"]) > 4000
            or not isinstance(case.get("expected_checked_items", []), list)
            or len(case.get("expected_checked_items", [])) > 500
            or any(
                not isinstance(item_id, str) or not item_id or len(item_id) > 128
                for item_id in case.get("expected_checked_items", [])
            )
            or len(case.get("expected_checked_items", []))
            != len(set(case.get("expected_checked_items", [])))
            or not isinstance(case.get("expected_statuses", {}), dict)
            or len(case.get("expected_statuses", {})) > 500
            or any(
                not isinstance(item_id, str)
                or status not in {"PASS", "FAIL", "UNKNOWN"}
                for item_id, status in case.get("expected_statuses", {}).items()
            )
            or not isinstance(case.get("requires_list_items", False), bool)
            or not isinstance(case.get("expected_error", False), bool)
            for case in payload
        )
    ):
        raise DataSourceError("Agent evaluation cases must contain id and question.")
    case_ids = [case["id"].casefold() for case in payload]
    if len(case_ids) != len(set(case_ids)):
        raise DataSourceError("Agent evaluation case IDs must be unique.")
    return payload


# ============================================================
# Trace helpers
# ============================================================


def get_compliance_calls(trace):
    """
    Return only check_item_compliance
    events from the agent trace.
    """

    return [event for event in trace if event["tool"] == "check_item_compliance"]


def get_list_calls(trace):
    """
    Return only list_items events.
    """

    return [event for event in trace if event["tool"] == "list_items"]


# ============================================================
# Error result helper
# ============================================================


def make_error_result(test_case, error, error_category):
    """
    Create a standard result for a case that
    could not be evaluated because execution failed.
    """

    error_message = type(error).__name__

    return {
        "id": test_case["id"],
        "question": (test_case["question"]),
        "outcome": "ERROR",
        "error_category": (error_category),
        "passed": False,
        "errors": [error_message],
        "warnings": [],
        "answer": None,
        "steps": 0,
        "tool_calls": 0,
        "tools_used": [],
    }


# ============================================================
# Evaluate one case
# ============================================================


def evaluate_case(test_case):
    """
    Evaluate one agent task.

    PASS:
        Agent completed the expected tool-grounded task.

    FAIL:
        Agent ran successfully but its behaviour did not
        satisfy the benchmark expectations.

    ERROR:
        The case could not be evaluated because of
        infrastructure or execution failure.
    """

    print("\n" + "=" * 60)

    print(f"CASE: {test_case['id']}")

    print("=" * 60)

    print("Question:")

    print(test_case["question"])

    # --------------------------------------------------------
    # Run the agent
    # --------------------------------------------------------

    try:
        agent_result = run_agent(test_case["question"], return_trace=True)

    except INFRASTRUCTURE_ERRORS as error:
        print("\nRESULT: ERROR")

        print("Category: infrastructure")

        print(f"- {type(error).__name__}")

        return make_error_result(
            test_case=test_case, error=error, error_category="infrastructure"
        )

    except Exception as error:
        print("\nRESULT: ERROR")

        print("Category: execution")

        print(f"- {type(error).__name__}")

        return make_error_result(
            test_case=test_case, error=error, error_category="execution"
        )

    if not isinstance(agent_result, dict):
        return make_error_result(
            test_case=test_case,
            error=TypeError("Trace-enabled agent run did not return a result object."),
            error_category="execution",
        )

    trace = agent_result["trace"]

    errors = []
    warnings = []

    # --------------------------------------------------------
    # 1. Check discovery behaviour
    # --------------------------------------------------------

    list_calls = get_list_calls(trace)

    used_list_items = len(list_calls) > 0

    requires_list_items = test_case.get("requires_list_items", False)

    if requires_list_items and not used_list_items:
        errors.append(
            "Agent should have used list_items before checking a multi-item category."
        )

    # --------------------------------------------------------
    # 2. Collect compliance checks
    # --------------------------------------------------------

    compliance_calls = get_compliance_calls(trace)

    checked_items = [call["arguments"].get("item_id") for call in compliance_calls]

    checked_items = [item_id for item_id in checked_items if item_id is not None]

    expected_items = test_case.get("expected_checked_items", [])

    # --------------------------------------------------------
    # 3. Check whether every expected item was inspected
    # --------------------------------------------------------

    for expected_item in expected_items:
        if expected_item not in (checked_items):
            errors.append(f"Agent did not check {expected_item}.")

    # --------------------------------------------------------
    # 4. Extra checks are warnings, not hard failures
    # --------------------------------------------------------
    #
    # An agent may occasionally gather extra evidence.
    # This can be inefficient but does not necessarily mean
    # the task itself was completed incorrectly.
    # --------------------------------------------------------

    unexpected_items = [
        item_id for item_id in checked_items if item_id not in expected_items
    ]

    if unexpected_items:
        unique_unexpected = sorted(set(unexpected_items))

        warnings.append(
            "Agent checked additional item(s): " + ", ".join(unique_unexpected)
        )

    # --------------------------------------------------------
    # 5. Detect duplicate compliance checks
    # --------------------------------------------------------

    duplicate_items = sorted(
        {item_id for item_id in checked_items if checked_items.count(item_id) > 1}
    )

    if duplicate_items:
        warnings.append(
            "Agent repeated compliance checks for: " + ", ".join(duplicate_items)
        )

    # --------------------------------------------------------
    # 6. Verify deterministic PASS / FAIL outcomes
    # --------------------------------------------------------

    expected_statuses = test_case.get("expected_statuses", {})

    for item_id, expected_status in expected_statuses.items():
        matching_calls = [
            call
            for call in compliance_calls
            if (call["arguments"].get("item_id") == item_id)
        ]

        # Missing call was already reported above.
        if not matching_calls:
            continue

        actual_status = matching_calls[-1]["result"].get("overall_status")

        if actual_status != expected_status:
            errors.append(
                f"{item_id}: expected {expected_status}, got {actual_status}."
            )

    # --------------------------------------------------------
    # 7. Verify missing-item handling
    # --------------------------------------------------------

    expected_error = test_case.get("expected_error", False)

    if expected_error:
        found_error = any(
            isinstance(call.get("result"), dict) and ("error" in call["result"])
            for call in compliance_calls
        )

        if not found_error:
            errors.append("Expected missing-item error was not returned.")

    # --------------------------------------------------------
    # 8. Check final-answer availability
    # --------------------------------------------------------

    final_answer = agent_result.get("answer")

    if not final_answer:
        errors.append("Agent produced no final answer.")

    # --------------------------------------------------------
    # 9. Detect max-step termination
    # --------------------------------------------------------

    if (
        agent_result.get("steps") >= MAX_AGENT_STEPS
        and final_answer
        and ("step limit" in final_answer.lower())
    ):
        errors.append(
            "Agent reached the maximum step limit without completing the task."
        )

    # --------------------------------------------------------
    # 10. Determine behavioural outcome
    # --------------------------------------------------------

    passed = len(errors) == 0

    outcome = "PASS" if passed else "FAIL"

    print("\nFinal answer:")

    print(final_answer)

    print("\nTools used:")

    if not trace:
        print("- No tools used")

    else:
        for event in trace:
            print(f"- Step {event['step']}: {event['tool']} {event['arguments']}")

    if warnings:
        print("\nWarnings:")

        for warning in warnings:
            print(f"- {warning}")

    print(f"\nRESULT: {outcome}")

    if errors:
        print("Behaviour errors:")

        for error in errors:
            print(f"- {error}")

    # --------------------------------------------------------
    # 11. Compact tool trace for results.json
    # --------------------------------------------------------

    tools_used = [
        {
            "step": (event["step"]),
            "tool": (event["tool"]),
            "arguments": (event["arguments"]),
        }
        for event in trace
    ]

    return {
        "id": (test_case["id"]),
        "question": (test_case["question"]),
        "outcome": (outcome),
        "error_category": None,
        "passed": (passed),
        "errors": (errors),
        "warnings": (warnings),
        "answer": (final_answer),
        "steps": (agent_result["steps"]),
        "tool_calls": (len(trace)),
        "tools_used": (tools_used),
        "metrics": agent_result.get("metrics", {}),
    }


# ============================================================
# Save evaluation results
# ============================================================


def save_results(results: list[dict[str, Any]]):
    """
    Save evaluation metadata, summary metrics,
    and per-case results to results.json.
    """

    total_count = len(results)

    passed_count = sum(result["outcome"] == "PASS" for result in results)

    failed_count = sum(result["outcome"] == "FAIL" for result in results)

    infrastructure_error_count = sum(
        (result["outcome"] == "ERROR")
        and (result.get("error_category") == "infrastructure")
        for result in results
    )

    execution_error_count = sum(
        (result["outcome"] == "ERROR") and (result.get("error_category") == "execution")
        for result in results
    )

    error_count = infrastructure_error_count + execution_error_count

    evaluable_count = passed_count + failed_count

    behavior_success_rate = (
        passed_count / evaluable_count if evaluable_count > 0 else None
    )

    # --------------------------------------------------------
    # Metrics over evaluable cases only
    # --------------------------------------------------------

    evaluable_results = [
        result for result in results if result["outcome"] in ["PASS", "FAIL"]
    ]

    total_tool_calls = sum(result["tool_calls"] for result in evaluable_results)

    total_agent_steps = sum(result["steps"] for result in evaluable_results)

    average_tool_calls = (
        total_tool_calls / evaluable_count if evaluable_count > 0 else None
    )

    average_agent_steps = (
        total_agent_steps / evaluable_count if evaluable_count > 0 else None
    )
    total_tokens = sum(
        int(result.get("metrics", {}).get("total_tokens", 0))
        for result in evaluable_results
    )
    total_duration_ms = sum(
        float(result.get("metrics", {}).get("duration_ms", 0))
        for result in evaluable_results
    )

    # --------------------------------------------------------
    # Output artifact
    # --------------------------------------------------------

    output = {
        "evaluation_name": ("Mini AEC Compliance Agent Demonstration Evaluation"),
        "timestamp_utc": (datetime.now(timezone.utc).isoformat()),
        "configuration": {
            "model": (MODEL_NAME),
            "temperature": (MODEL_TEMPERATURE),
            "seed": (MODEL_SEED),
            "max_agent_steps": (MAX_AGENT_STEPS),
        },
        "scope_note": (
            "This is a small demonstration benchmark. "
            "Behavior success is calculated only over "
            "cases that completed without infrastructure "
            "or execution errors. Infrastructure errors "
            "are reported separately and are not treated "
            "as agent reasoning failures. The benchmark "
            "does not constitute a general measure of "
            "agent reliability or legal compliance accuracy."
        ),
        "summary": {
            "total_cases": (total_count),
            "evaluable_cases": (evaluable_count),
            "passed_cases": (passed_count),
            "behavior_failures": (failed_count),
            "infrastructure_errors": (infrastructure_error_count),
            "execution_errors": (execution_error_count),
            "total_errors": (error_count),
            "behavior_success_rate": (behavior_success_rate),
            "total_tool_calls_evaluable": (total_tool_calls),
            "average_tool_calls_per_evaluable_case": (average_tool_calls),
            "total_agent_steps_evaluable": (total_agent_steps),
            "average_agent_steps_per_evaluable_case": (average_agent_steps),
            "total_tokens_evaluable": total_tokens,
            "average_tokens_per_evaluable_case": (
                total_tokens / evaluable_count if evaluable_count else None
            ),
            "average_duration_ms_per_evaluable_case": (
                total_duration_ms / evaluable_count if evaluable_count else None
            ),
        },
        "results": (results),
    }

    atomic_write_text(
        RESULTS_FILE,
        json.dumps(output, indent=2, ensure_ascii=False),
    )

    return output


# ============================================================
# Main evaluation runner
# ============================================================


def main() -> int:

    test_cases = load_test_cases()

    results = []

    for test_case in test_cases:
        result = evaluate_case(test_case)

        results.append(result)

    output = save_results(results)

    summary = output["summary"]

    print("\n" + "=" * 60)

    print("EVALUATION SUMMARY")

    print("=" * 60)

    print(f"Total cases: {summary['total_cases']}")

    print(f"Evaluable cases: {summary['evaluable_cases']}")

    print(f"Passed: {summary['passed_cases']}")

    print(f"Behavior failures: {summary['behavior_failures']}")

    print(f"Infrastructure errors: {summary['infrastructure_errors']}")

    print(f"Execution errors: {summary['execution_errors']}")

    behavior_rate = summary["behavior_success_rate"]

    if behavior_rate is None:
        print("Behavior success rate: N/A")

    else:
        print(f"Behavior success rate: {behavior_rate * 100:.1f}%")

    average_tool_calls = summary["average_tool_calls_per_evaluable_case"]

    if average_tool_calls is not None:
        print(f"Average tool calls / evaluable case: {average_tool_calls:.2f}")

    average_steps = summary["average_agent_steps_per_evaluable_case"]

    if average_steps is not None:
        print(f"Average agent steps / evaluable case: {average_steps:.2f}")

    print(f"Results saved to: {RESULTS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
