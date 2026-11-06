from pathlib import Path

import pandas as pd
import pytest

from app.services.quality_engine import (
    MAX_VIOLATING_INDICES,
    YAMLRuleParsingError,
    validate_dataframe,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _violation_counts(result):
    return {
        violation["column"]: violation["violation_count"]
        for violation in result["violations"]
    }


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
    # 3 total rows, 1 duplicate row => N_pr = 1
    # Score = 100 * (3 - 1) / 3 = 66.666... -> one decimal place
    assert res["Score"] == 66.7


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


def test_quality_engine_missing_column_raises():
    """A rule for an absent column is a configuration error, not a score of 0."""
    df = pd.DataFrame({"name": ["Alice", "Bob"]})
    rules = [
        {
            "column": "missing_column",
            "condition": "not_null",
            "action": "reject",
        }
    ]

    with pytest.raises(YAMLRuleParsingError) as exc_info:
        validate_dataframe(df, rules)

    assert exc_info.value.status_code == 400
    assert "missing_column" in exc_info.value.detail
    assert "name" in exc_info.value.detail


def test_quality_engine_has_no_duplicate_response_keys(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(
        """
- column: val
  condition: not_null
  action: reject
""",
        encoding="utf-8",
    )
    df = pd.DataFrame({"val": [1, None]})

    result = validate_dataframe(df, yaml_file)

    assert "Score" in result
    assert "score" not in result
    assert "violation_count" in result
    assert "total_violations" not in result


def test_quality_engine_limits_violating_indices(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(
        """
- column: val
  condition: not_null
  action: flag
""",
        encoding="utf-8",
    )
    df = pd.DataFrame({"val": [None] * (MAX_VIOLATING_INDICES + 25)})

    result = validate_dataframe(df, yaml_file)
    violation = result["violations"][0]

    assert violation["violation_count"] == MAX_VIOLATING_INDICES + 25
    assert len(violation["violating_indices"]) == MAX_VIOLATING_INDICES
    assert violation["violating_indices_truncated"] is True


def test_payroll_real_data_matches_defects_manifest():
    """SCRUM-40: payroll.csv -> 91.8 and documented per-rule counts."""
    df = pd.read_csv(DATA_DIR / "payroll.csv", dtype={"ipn": str})
    result = validate_dataframe(df, DATA_DIR / "payroll_rules.yaml")

    assert result["Score"] == 91.8
    assert result["total_rows"] == 500
    assert result["duplicated_rows_count"] == 10

    counts = _violation_counts(result)
    assert counts["ipn"] == 15
    assert counts["amount_uah"] == 8
    assert counts["payment_date"] == 8
    assert counts["*"] == 10


def test_customers_real_data_matches_defects_manifest():
    """SCRUM-40: customers.json -> 87.0 and documented per-rule counts."""
    df = pd.read_json(DATA_DIR / "customers.json")
    result = validate_dataframe(df, DATA_DIR / "customers_rules.yaml")

    assert result["Score"] == 87.0
    assert result["total_rows"] == 1000
    assert result["duplicated_rows_count"] == 15

    counts = _violation_counts(result)
    assert counts["age"] == 20
    assert counts["email"] == 25
    assert counts["registration_date"] == 30
    assert counts["city"] == 40
    assert counts["*"] == 15
