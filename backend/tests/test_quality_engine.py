import pandas as pd
import pytest

from app.services.quality_engine import (
    YAMLRuleParsingError,
    validate_dataframe,
)


def test_quality_engine_basic_rules(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(
        r"""
- column: age
  condition: between(0, 120)
  action: reject
- column: email
  condition: 'regex(r"^[\w\.-]+@[\w\.-]+\.\w+$")'
  action: flag
- column: name
  condition: not_null
  action: block
""",
        encoding="utf-8",
    )

    df = pd.DataFrame(
        {
            "name": ["Alice", "Bob", None, "Dave"],
            "age": [25, -5, 130, 40],
            "email": [
                "alice@example.com",
                "bad_email",
                "bob@test.org",
                "dave@example.com",
            ],
        }
    )

    res = validate_dataframe(df, yaml_file)
    assert "Score" in res
    assert "violations" in res
    assert res["total_rows"] == 4
    assert res["unique_violating_rows"] == 2
    assert res["Score"] == 50.0
    assert res["has_blocking_violations"] is True
    assert res["can_publish"] is False


def test_quality_engine_block_does_not_reduce_score(tmp_path):
    """Jira Requirement: 'Дія block не змінює оцінку, а блокує публікацію'."""
    yaml_file = tmp_path / "block_rule.yaml"
    yaml_file.write_text(
        """
- column: status
  condition: not_null
  action: block
""",
        encoding="utf-8",
    )

    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "status": ["active", None, "active", None],
        }
    )

    res = validate_dataframe(df, yaml_file)
    # Block rule should NOT decrease Quality Score
    assert res["Score"] == 100.0
    assert res["unique_violating_rows"] == 0
    # But it MUST flag blocking violations and halt publication
    assert res["has_blocking_violations"] is True
    assert res["can_publish"] is False
    assert res["violation_count"] == 2


def test_quality_engine_duplicates(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(
        """
- column: val
  condition: not_null
  action: flag
""",
        encoding="utf-8",
    )

    df = pd.DataFrame(
        {
            "val": [10, 20, 10],
        }
    )

    res = validate_dataframe(df, yaml_file)
    assert res["duplicated_rows_count"] == 1
    # 3 total rows, 1 duplicate row => N_pr = 1 => Score = 100 * (3 - 1) / 3 = 66.67
    assert res["Score"] == 66.67


def test_quality_engine_invalid_yaml(tmp_path):
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text("not a valid yaml: [", encoding="utf-8")

    df = pd.DataFrame({"col": [1]})
    with pytest.raises(YAMLRuleParsingError) as exc_info:
        validate_dataframe(df, yaml_file)
    assert exc_info.value.status_code == 400


def test_quality_engine_missing_file():
    df = pd.DataFrame({"col": [1]})
    with pytest.raises(YAMLRuleParsingError) as exc_info:
        validate_dataframe(df, "non_existent_rules_file.yaml")
    assert exc_info.value.status_code == 404
