import json
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent

BUILDING_FILE = BASE_DIR / "data" / "building.json"
REGULATIONS_FILE = BASE_DIR / "data" / "regulations.json"

def load_json(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)

def load_building():
    return load_json(BUILDING_FILE)


def load_regulations():
    return load_json(REGULATIONS_FILE)

def get_item(item_id):
    building = load_building()

    all_items = building["components"] + building["spaces"]

    for item in all_items:
        if item["id"].lower() == item_id.lower():
            return item

    return {
        "error": f"Item '{item_id}' was not found."
    }

def compare_values(actual, operator, threshold):
    if operator == ">=":
        return actual >= threshold

    if operator == "<=":
        return actual <= threshold

    if operator == ">":
        return actual > threshold

    if operator == "<":
        return actual < threshold

    if operator == "==":
        return actual == threshold

    raise ValueError(f"Unsupported operator: {operator}")

def get_applicable_rules(item):
    regulations = load_regulations()
    rules = regulations["rules"]

    item_type = item["type"]

    applicable_rules = []

    for rule in rules:
        if rule["applies_to"] == item_type:
            applicable_rules.append(rule)

        elif (
            rule["applies_to"] == "space"
            and item_type in ["office", "meeting_room"]
        ):
            applicable_rules.append(rule)

    return applicable_rules

def get_applicable_rules(item):
    regulations = load_regulations()
    rules = regulations["rules"]

    item_type = item["type"]

    applicable_rules = []

    for rule in rules:
        if rule["applies_to"] == item_type:
            applicable_rules.append(rule)

        elif (
            rule["applies_to"] == "space"
            and item_type in ["office", "meeting_room"]
        ):
            applicable_rules.append(rule)

    return applicable_rules

def check_item_compliance(item_id):
    item = get_item(item_id)

    if "error" in item:
        return item

    applicable_rules = get_applicable_rules(item)

    results = []

    for rule in applicable_rules:
        field = rule["field"]

        if field not in item:
            results.append(
                {
                    "rule_id": rule["rule_id"],
                    "status": "UNKNOWN",
                    "reason": f"Required field '{field}' is missing."
                }
            )
            continue

        actual_value = item[field]
        passed = compare_values(
            actual_value,
            rule["operator"],
            rule["threshold"]
        )

        results.append(
            {
                "rule_id": rule["rule_id"],
                "description": rule["description"],
                "status": "PASS" if passed else "FAIL",
                "actual_value": actual_value,
                "operator": rule["operator"],
                "required_value": rule["threshold"],
                "unit": rule["unit"]
            }
        )

    overall_status = "PASS"

    if any(result["status"] == "FAIL" for result in results):
        overall_status = "FAIL"

    elif any(result["status"] == "UNKNOWN" for result in results):
        overall_status = "UNKNOWN"

    return {
        "item": item,
        "overall_status": overall_status,
        "checks": results
    }


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]


def list_items(item_type="all"):
    building = load_building()

    all_items = (
        building["components"]
        + building["spaces"]
    )

    if item_type == "all":
        return all_items

    return [
        item
        for item in all_items
        if item["type"] == item_type
    ]

# 
# 
# if __name__ == "__main__":
    # print(list_items("door"))
    # 
    # test_items = [
        # "Door-01",
        # "Door-02",
        # "Room-101",
        # "Room-102"
    # ]
# 
    # for item_id in test_items:
        # result = check_item_compliance(item_id)
# 
        # print("=" * 50)
        # print(f"Checking: {item_id}")
        # print(f"Overall status: {result['overall_status']}")
# 
        # for check in result["checks"]:
            # print(
                # f"- {check['rule_id']}: "
                # f"{check['status']} "
                # f"(actual={check['actual_value']} "
                # f"{check['operator']} "
                # f"required={check['required_value']} "
                # f"{check['unit']})"
            # )