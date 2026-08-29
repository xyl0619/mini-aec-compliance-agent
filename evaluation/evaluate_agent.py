import json
from datetime import datetime, timezone
from pathlib import Path

import together

from agent import (
    MAX_AGENT_STEPS,
    MODEL_NAME,
    MODEL_SEED,
    MODEL_TEMPERATURE,
    run_agent
)


# ============================================================
# Paths
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

TEST_CASES_FILE = (
    BASE_DIR
    / "test_cases.json"
)

RESULTS_FILE = (
    BASE_DIR
    / "results.json"
)


# ============================================================
# Error categories
# ============================================================

INFRASTRUCTURE_ERRORS = (
    together.APIConnectionError,
    together.APITimeoutError,
    together.RateLimitError,
    together.InternalServerError
)


# ============================================================
# Load test cases
# ============================================================

def load_test_cases():
    """
    Load the agent evaluation cases.
    """

    with open(
        TEST_CASES_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


# ============================================================
# Trace helpers
# ============================================================

def get_compliance_calls(
    trace
):
    """
    Return only check_item_compliance
    events from the agent trace.
    """

    return [
        event
        for event in trace

        if event["tool"]
        == "check_item_compliance"
    ]


def get_list_calls(
    trace
):
    """
    Return only list_items events.
    """

    return [
        event
        for event in trace

        if event["tool"]
        == "list_items"
    ]


# ============================================================
# Error result helper
# ============================================================

def make_error_result(
    test_case,
    error,
    error_category
):
    """
    Create a standard result for a case that
    could not be evaluated because execution failed.
    """

    error_message = (
        f"{type(error).__name__}: "
        f"{error}"
    )

    return {
        "id": test_case["id"],

        "question": (
            test_case["question"]
        ),

        "outcome": "ERROR",

        "error_category": (
            error_category
        ),

        "passed": False,

        "errors": [
            error_message
        ],

        "warnings": [],

        "answer": None,

        "steps": 0,

        "tool_calls": 0,

        "tools_used": []
    }


# ============================================================
# Evaluate one case
# ============================================================

def evaluate_case(
    test_case
):
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

    print(
        "\n"
        + "=" * 60
    )

    print(
        f"CASE: "
        f"{test_case['id']}"
    )

    print(
        "=" * 60
    )

    print(
        "Question:"
    )

    print(
        test_case[
            "question"
        ]
    )

    # --------------------------------------------------------
    # Run the agent
    # --------------------------------------------------------

    try:

        agent_result = run_agent(
            test_case["question"],
            return_trace=True
        )

    except INFRASTRUCTURE_ERRORS as error:

        print(
            "\nRESULT: ERROR"
        )

        print(
            "Category: infrastructure"
        )

        print(
            f"- {type(error).__name__}: "
            f"{error}"
        )

        return make_error_result(
            test_case=test_case,
            error=error,
            error_category="infrastructure"
        )

    except Exception as error:

        print(
            "\nRESULT: ERROR"
        )

        print(
            "Category: execution"
        )

        print(
            f"- {type(error).__name__}: "
            f"{error}"
        )

        return make_error_result(
            test_case=test_case,
            error=error,
            error_category="execution"
        )

    trace = (
        agent_result[
            "trace"
        ]
    )

    errors = []
    warnings = []

    # --------------------------------------------------------
    # 1. Check discovery behaviour
    # --------------------------------------------------------

    list_calls = (
        get_list_calls(
            trace
        )
    )

    used_list_items = (
        len(list_calls) > 0
    )

    requires_list_items = (
        test_case.get(
            "requires_list_items",
            False
        )
    )

    if (
        requires_list_items
        and not used_list_items
    ):

        errors.append(
            "Agent should have used "
            "list_items before checking "
            "a multi-item category."
        )

    # --------------------------------------------------------
    # 2. Collect compliance checks
    # --------------------------------------------------------

    compliance_calls = (
        get_compliance_calls(
            trace
        )
    )

    checked_items = [
        call[
            "arguments"
        ].get(
            "item_id"
        )

        for call
        in compliance_calls
    ]

    checked_items = [
        item_id

        for item_id
        in checked_items

        if item_id
        is not None
    ]

    expected_items = (
        test_case.get(
            "expected_checked_items",
            []
        )
    )

    # --------------------------------------------------------
    # 3. Check whether every expected item was inspected
    # --------------------------------------------------------

    for expected_item in (
        expected_items
    ):

        if expected_item not in (
            checked_items
        ):

            errors.append(
                f"Agent did not check "
                f"{expected_item}."
            )

    # --------------------------------------------------------
    # 4. Extra checks are warnings, not hard failures
    # --------------------------------------------------------
    #
    # An agent may occasionally gather extra evidence.
    # This can be inefficient but does not necessarily mean
    # the task itself was completed incorrectly.
    # --------------------------------------------------------

    unexpected_items = [
        item_id

        for item_id
        in checked_items

        if item_id
        not in expected_items
    ]

    if unexpected_items:

        unique_unexpected = sorted(
            set(
                unexpected_items
            )
        )

        warnings.append(
            "Agent checked additional "
            "item(s): "
            + ", ".join(
                unique_unexpected
            )
        )

    # --------------------------------------------------------
    # 5. Detect duplicate compliance checks
    # --------------------------------------------------------

    duplicate_items = sorted(
        {
            item_id

            for item_id
            in checked_items

            if checked_items.count(
                item_id
            ) > 1
        }
    )

    if duplicate_items:

        warnings.append(
            "Agent repeated compliance "
            "checks for: "
            + ", ".join(
                duplicate_items
            )
        )

    # --------------------------------------------------------
    # 6. Verify deterministic PASS / FAIL outcomes
    # --------------------------------------------------------

    expected_statuses = (
        test_case.get(
            "expected_statuses",
            {}
        )
    )

    for (
        item_id,
        expected_status
    ) in expected_statuses.items():

        matching_calls = [
            call

            for call
            in compliance_calls

            if (
                call[
                    "arguments"
                ].get(
                    "item_id"
                )
                == item_id
            )
        ]

        # Missing call was already reported above.
        if not matching_calls:
            continue

        actual_status = (
            matching_calls[-1][
                "result"
            ].get(
                "overall_status"
            )
        )

        if (
            actual_status
            != expected_status
        ):

            errors.append(
                f"{item_id}: "
                f"expected "
                f"{expected_status}, "
                f"got "
                f"{actual_status}."
            )

    # --------------------------------------------------------
    # 7. Verify missing-item handling
    # --------------------------------------------------------

    expected_error = (
        test_case.get(
            "expected_error",
            False
        )
    )

    if expected_error:

        found_error = any(
            isinstance(
                call.get(
                    "result"
                ),
                dict
            )
            and (
                "error"
                in call[
                    "result"
                ]
            )

            for call
            in compliance_calls
        )

        if not found_error:

            errors.append(
                "Expected missing-item "
                "error was not returned."
            )

    # --------------------------------------------------------
    # 8. Check final-answer availability
    # --------------------------------------------------------

    final_answer = (
        agent_result.get(
            "answer"
        )
    )

    if not final_answer:

        errors.append(
            "Agent produced no final answer."
        )

    # --------------------------------------------------------
    # 9. Detect max-step termination
    # --------------------------------------------------------

    if (
        agent_result.get(
            "steps"
        )
        >= MAX_AGENT_STEPS
        and final_answer
        and (
            "maximum number"
            in final_answer.lower()
        )
    ):

        errors.append(
            "Agent reached the maximum "
            "step limit without completing "
            "the task."
        )

    # --------------------------------------------------------
    # 10. Determine behavioural outcome
    # --------------------------------------------------------

    passed = (
        len(errors) == 0
    )

    outcome = (
        "PASS"
        if passed
        else "FAIL"
    )

    print(
        "\nFinal answer:"
    )

    print(
        final_answer
    )

    print(
        "\nTools used:"
    )

    if not trace:

        print(
            "- No tools used"
        )

    else:

        for event in trace:

            print(
                f"- Step "
                f"{event['step']}: "
                f"{event['tool']} "
                f"{event['arguments']}"
            )

    if warnings:

        print(
            "\nWarnings:"
        )

        for warning in warnings:

            print(
                f"- {warning}"
            )

    print(
        f"\nRESULT: "
        f"{outcome}"
    )

    if errors:

        print(
            "Behaviour errors:"
        )

        for error in errors:

            print(
                f"- {error}"
            )

    # --------------------------------------------------------
    # 11. Compact tool trace for results.json
    # --------------------------------------------------------

    tools_used = [
        {
            "step": (
                event["step"]
            ),

            "tool": (
                event["tool"]
            ),

            "arguments": (
                event["arguments"]
            )
        }

        for event
        in trace
    ]

    return {
        "id": (
            test_case["id"]
        ),

        "question": (
            test_case[
                "question"
            ]
        ),

        "outcome": (
            outcome
        ),

        "error_category": None,

        "passed": (
            passed
        ),

        "errors": (
            errors
        ),

        "warnings": (
            warnings
        ),

        "answer": (
            final_answer
        ),

        "steps": (
            agent_result[
                "steps"
            ]
        ),

        "tool_calls": (
            len(trace)
        ),

        "tools_used": (
            tools_used
        )
    }


# ============================================================
# Save evaluation results
# ============================================================

def save_results(
    results
):
    """
    Save evaluation metadata, summary metrics,
    and per-case results to results.json.
    """

    total_count = (
        len(results)
    )

    passed_count = sum(
        result[
            "outcome"
        ] == "PASS"

        for result
        in results
    )

    failed_count = sum(
        result[
            "outcome"
        ] == "FAIL"

        for result
        in results
    )

    infrastructure_error_count = sum(
        (
            result[
                "outcome"
            ] == "ERROR"
        )
        and (
            result.get(
                "error_category"
            )
            == "infrastructure"
        )

        for result
        in results
    )

    execution_error_count = sum(
        (
            result[
                "outcome"
            ] == "ERROR"
        )
        and (
            result.get(
                "error_category"
            )
            == "execution"
        )

        for result
        in results
    )

    error_count = (
        infrastructure_error_count
        + execution_error_count
    )

    evaluable_count = (
        passed_count
        + failed_count
    )

    behavior_success_rate = (
        passed_count
        / evaluable_count

        if evaluable_count > 0

        else None
    )

    # --------------------------------------------------------
    # Metrics over evaluable cases only
    # --------------------------------------------------------

    evaluable_results = [
        result

        for result
        in results

        if result[
            "outcome"
        ] in [
            "PASS",
            "FAIL"
        ]
    ]

    total_tool_calls = sum(
        result[
            "tool_calls"
        ]

        for result
        in evaluable_results
    )

    total_agent_steps = sum(
        result[
            "steps"
        ]

        for result
        in evaluable_results
    )

    average_tool_calls = (
        total_tool_calls
        / evaluable_count

        if evaluable_count > 0

        else None
    )

    average_agent_steps = (
        total_agent_steps
        / evaluable_count

        if evaluable_count > 0

        else None
    )

    # --------------------------------------------------------
    # Output artifact
    # --------------------------------------------------------

    output = {
        "evaluation_name": (
            "Mini AEC Compliance Agent "
            "Demonstration Evaluation"
        ),

        "timestamp_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "configuration": {
            "model": (
                MODEL_NAME
            ),

            "temperature": (
                MODEL_TEMPERATURE
            ),

            "seed": (
                MODEL_SEED
            ),

            "max_agent_steps": (
                MAX_AGENT_STEPS
            )
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
            "total_cases": (
                total_count
            ),

            "evaluable_cases": (
                evaluable_count
            ),

            "passed_cases": (
                passed_count
            ),

            "behavior_failures": (
                failed_count
            ),

            "infrastructure_errors": (
                infrastructure_error_count
            ),

            "execution_errors": (
                execution_error_count
            ),

            "total_errors": (
                error_count
            ),

            "behavior_success_rate": (
                behavior_success_rate
            ),

            "total_tool_calls_evaluable": (
                total_tool_calls
            ),

            "average_tool_calls_per_evaluable_case": (
                average_tool_calls
            ),

            "total_agent_steps_evaluable": (
                total_agent_steps
            ),

            "average_agent_steps_per_evaluable_case": (
                average_agent_steps
            )
        },

        "results": (
            results
        )
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


# ============================================================
# Main evaluation runner
# ============================================================

def main():

    test_cases = (
        load_test_cases()
    )

    results = []

    for test_case in (
        test_cases
    ):

        result = (
            evaluate_case(
                test_case
            )
        )

        results.append(
            result
        )

    output = (
        save_results(
            results
        )
    )

    summary = (
        output[
            "summary"
        ]
    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "EVALUATION SUMMARY"
    )

    print(
        "=" * 60
    )

    print(
        f"Total cases: "
        f"{summary['total_cases']}"
    )

    print(
        f"Evaluable cases: "
        f"{summary['evaluable_cases']}"
    )

    print(
        f"Passed: "
        f"{summary['passed_cases']}"
    )

    print(
        f"Behavior failures: "
        f"{summary['behavior_failures']}"
    )

    print(
        f"Infrastructure errors: "
        f"{summary['infrastructure_errors']}"
    )

    print(
        f"Execution errors: "
        f"{summary['execution_errors']}"
    )

    behavior_rate = (
        summary[
            "behavior_success_rate"
        ]
    )

    if behavior_rate is None:

        print(
            "Behavior success rate: "
            "N/A"
        )

    else:

        print(
            f"Behavior success rate: "
            f"{behavior_rate * 100:.1f}%"
        )

    average_tool_calls = (
        summary[
            "average_tool_calls_per_evaluable_case"
        ]
    )

    if average_tool_calls is not None:

        print(
            f"Average tool calls / "
            f"evaluable case: "
            f"{average_tool_calls:.2f}"
        )

    average_steps = (
        summary[
            "average_agent_steps_per_evaluable_case"
        ]
    )

    if average_steps is not None:

        print(
            f"Average agent steps / "
            f"evaluable case: "
            f"{average_steps:.2f}"
        )

    print(
        f"Results saved to: "
        f"{RESULTS_FILE}"
    )


if __name__ == "__main__":
    main()