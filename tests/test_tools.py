from tools import (
    check_item_compliance,
    get_item,
    list_items
)


def test_door_01_should_fail():
    result = check_item_compliance("Door-01")

    assert result["overall_status"] == "FAIL"

    checks = result["checks"]

    assert len(checks) == 1

    check = checks[0]

    assert check["rule_id"] == "DOOR-WIDTH-001"
    assert check["status"] == "FAIL"
    assert check["actual_value"] == 850
    assert check["required_value"] == 900
    assert check["unit"] == "mm"


def test_door_02_should_pass():
    result = check_item_compliance("Door-02")

    assert result["overall_status"] == "PASS"

    checks = result["checks"]

    assert len(checks) == 1

    check = checks[0]

    assert check["rule_id"] == "DOOR-WIDTH-001"
    assert check["status"] == "PASS"
    assert check["actual_value"] == 1000
    assert check["required_value"] == 900


def test_door_03_should_pass():
    result = check_item_compliance("Door-03")

    assert result["overall_status"] == "PASS"

    checks = result["checks"]

    assert len(checks) == 1

    check = checks[0]

    assert check["rule_id"] == "DOOR-WIDTH-001"
    assert check["status"] == "PASS"
    assert check["actual_value"] == 920
    assert check["required_value"] == 900


def test_room_101_should_fail():
    result = check_item_compliance("Room-101")

    assert result["overall_status"] == "FAIL"

    checks = result["checks"]

    assert len(checks) == 2

    check_map = {
        check["rule_id"]: check
        for check in checks
    }

    area_check = check_map["OFFICE-AREA-001"]

    assert area_check["status"] == "FAIL"
    assert area_check["actual_value"] == 8.5
    assert area_check["required_value"] == 10.0
    assert area_check["unit"] == "m2"

    height_check = check_map["SPACE-HEIGHT-001"]

    assert height_check["status"] == "FAIL"
    assert height_check["actual_value"] == 2.3
    assert height_check["required_value"] == 2.4
    assert height_check["unit"] == "m"


def test_room_102_should_pass():
    result = check_item_compliance("Room-102")

    assert result["overall_status"] == "PASS"

    checks = result["checks"]

    assert len(checks) == 2

    check_map = {
        check["rule_id"]: check
        for check in checks
    }

    area_check = check_map["OFFICE-AREA-001"]

    assert area_check["status"] == "PASS"
    assert area_check["actual_value"] == 12.5
    assert area_check["required_value"] == 10.0

    height_check = check_map["SPACE-HEIGHT-001"]

    assert height_check["status"] == "PASS"
    assert height_check["actual_value"] == 2.6
    assert height_check["required_value"] == 2.4


def test_room_201_should_pass():
    result = check_item_compliance("Room-201")

    assert result["overall_status"] == "PASS"

    checks = result["checks"]

    assert len(checks) == 1

    check = checks[0]

    assert check["rule_id"] == "SPACE-HEIGHT-001"
    assert check["status"] == "PASS"
    assert check["actual_value"] == 2.7
    assert check["required_value"] == 2.4


def test_nonexistent_item():
    result = check_item_compliance("Door-99")

    assert "error" in result
    assert result["error"] == "Item 'Door-99' was not found."


def test_list_all_doors():
    doors = list_items("door")

    assert len(doors) == 3

    door_ids = [
        door["id"]
        for door in doors
    ]

    assert "Door-01" in door_ids
    assert "Door-02" in door_ids
    assert "Door-03" in door_ids


def test_get_item():
    item = get_item("Room-101")

    assert item["id"] == "Room-101"
    assert item["type"] == "office"
    assert item["location"] == "Level 1"
    assert item["area_m2"] == 8.5
    assert item["ceiling_height_m"] == 2.3