"""Data Clean Room Quality Engine module (SCRUM-11/40).

Validates a Pandas DataFrame against rules defined in a YAML configuration file.
Calculates Quality Score according to the formula:
    Score = 100 * (N - N_пр) / N
where:
    - N is total rows count (len(df)).
    - N_пр is count of unique rows with 'reject' or 'flag' violations plus
      duplicate rows.

Important Domain Rules:
    - Action 'block': does NOT decrease Quality Score, but sets 'can_publish = False'
      and 'has_blocking_violations = True'.
    - Duplicates: detected via df.duplicated(keep='first') and included in N_пр.
    - Supported conditions: not_null, between(min, max), email, regex(...),
      comparison operators (<= today, > 0, etc.).
"""

from __future__ import annotations

import re
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
import yaml
from fastapi import HTTPException, status


class QualityEngineException(HTTPException):
    """Base exception for Quality Engine errors, compatible with FastAPI."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)


class YAMLRuleParsingError(QualityEngineException):
    """Raised when YAML structure or rule definition is invalid."""

    pass


ALLOWED_ACTIONS: Set[str] = {"reject", "flag", "block"}
EMAIL_REGEX_PATTERN = r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$"
MAX_VIOLATING_INDICES = 100


def parse_yaml_rules(yaml_source: Union[str, Path, dict, list]) -> List[Dict[str, Any]]:
    """Loads and validates quality rules from a YAML file or raw data structure.

    Args:
        yaml_source: Path to YAML file (str/Path), or loaded dict/list of rules.

    Returns:
        List of rule dictionaries.

    Raises:
        YAMLRuleParsingError: If file is missing, YAML syntax is invalid,
                              or required rule fields are absent.
    """
    raw_data: Any

    if isinstance(yaml_source, (str, Path)):
        file_path = Path(yaml_source)
        if not file_path.exists() or not file_path.is_file():
            raise YAMLRuleParsingError(
                f"YAML rules file not found: {file_path}",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise YAMLRuleParsingError(f"YAML syntax error: {exc}") from exc
        except Exception as exc:
            raise YAMLRuleParsingError(
                f"Failed to read YAML rules file: {exc}"
            ) from exc
    else:
        raw_data = yaml_source

    if raw_data is None:
        return []

    if isinstance(raw_data, dict):
        if "rules" in raw_data and isinstance(raw_data["rules"], list):
            rules_list = raw_data["rules"]
        else:
            raise YAMLRuleParsingError(
                "Invalid YAML structure: expected a list of rules "
                "or a dictionary with 'rules' key."
            )
    elif isinstance(raw_data, list):
        rules_list = raw_data
    else:
        raise YAMLRuleParsingError(
            "Invalid YAML structure: expected list or dict, "
            f"got {type(raw_data).__name__}."
        )

    validated_rules: List[Dict[str, Any]] = []
    for idx, rule in enumerate(rules_list):
        if not isinstance(rule, dict):
            raise YAMLRuleParsingError(
                f"Rule at index {idx} must be a dictionary, got {type(rule).__name__}."
            )

        column = rule.get("column")
        condition = rule.get("condition")
        action = rule.get("action")

        if not column or not isinstance(column, str):
            raise YAMLRuleParsingError(
                f"Rule at index {idx} is missing a valid 'column' field: {rule}"
            )
        if not condition or not isinstance(condition, str):
            raise YAMLRuleParsingError(
                f"Rule at index {idx} is missing a valid 'condition' field: {rule}"
            )
        if not action or not isinstance(action, str):
            raise YAMLRuleParsingError(
                f"Rule at index {idx} is missing a valid 'action' field: {rule}"
            )

        norm_action = action.strip().lower()
        if norm_action not in ALLOWED_ACTIONS:
            raise YAMLRuleParsingError(
                f"Rule at index {idx} has unsupported action '{action}'. "
                f"Allowed actions: {', '.join(sorted(ALLOWED_ACTIONS))}."
            )

        validated_rules.append(
            {
                "column": column.strip(),
                "condition": condition.strip(),
                "action": norm_action,
                "name": rule.get("name"),
                "description": rule.get("description"),
            }
        )

    return validated_rules


def _evaluate_condition(
    series: pd.Series, condition_str: str
) -> Tuple[pd.Series, Optional[str]]:
    """Evaluates condition string on a Series and returns a violation mask.

    Returns:
        (violation_mask, error_message): violation_mask is True for rows that
        fail the condition.
    """
    cond = condition_str.strip()
    cond_lower = cond.lower()

    # 1. not_null / is_not_null / not_empty
    if cond_lower in {"not_null", "is_not_null", "not_empty"}:
        is_na = series.isna()
        is_empty_str = series.astype(str).str.strip().str.lower().isin(
            {"", "nan", "none", "null"}
        )
        violation_mask = is_na | is_empty_str
        return violation_mask, None

    # 2. email condition
    if cond_lower in {"email", "is_email", "email_format"}:
        compiled = re.compile(EMAIL_REGEX_PATTERN)
        str_series = series.astype(str)
        valid_mask = series.notna() & str_series.str.match(compiled, na=False)
        return ~valid_mask, None

    # 3. between(min_val, max_val)
    between_match = re.match(
        r"^between\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)$",
        cond,
        re.IGNORECASE,
    )
    if between_match:
        low_val = float(between_match.group(1))
        high_val = float(between_match.group(2))
        num_series = pd.to_numeric(series, errors="coerce")
        valid_mask = (
            num_series.notna()
            & (num_series >= low_val)
            & (num_series <= high_val)
        )
        return ~valid_mask, None

    # 4. regex(...)
    regex_match = re.match(r"^regex\s*\(\s*(.*)\s*\)$", cond, re.IGNORECASE | re.DOTALL)
    if regex_match:
        pattern = regex_match.group(1).strip()
        if pattern.startswith("r'") and pattern.endswith("'"):
            pattern = pattern[2:-1]
        elif pattern.startswith('r"') and pattern.endswith('"'):
            pattern = pattern[2:-1]
        elif (pattern.startswith("'") and pattern.endswith("'")) or (
            pattern.startswith('"') and pattern.endswith('"')
        ):
            pattern = pattern[1:-1]

        try:
            compiled = re.compile(pattern)
        except re.error as e:
            raise YAMLRuleParsingError(f"Invalid regex pattern '{pattern}': {e}") from e

        str_series = series.astype(str)
        valid_mask = series.notna() & str_series.str.contains(
            compiled, regex=True, na=False
        )
        return ~valid_mask, None

    # 5. Date and numeric comparisons: <=, >=, !=, ==, <, >
    # Handles: date <= today, <= today, not_future, <= now
    if cond_lower in {"date_not_future", "not_future", "date <= today", "<= today"}:
        cond = "<= today"

    op_match = re.match(r"^(?:date\s*)?(<=|>=|!=|==|<|>)\s*(.+)$", cond, re.IGNORECASE)
    if op_match:
        op = op_match.group(1)
        target_str = op_match.group(2).strip()
        target_lower = target_str.lower()

        # Date comparison with today / now
        if target_lower in {
            "today", "now", "now()", "current_date", "current_timestamp"
        }:
            dt_series = pd.to_datetime(series, errors="coerce")
            now = pd.Timestamp.now(tz=timezone.utc).tz_localize(None)

            if op == "<=":
                valid_mask = dt_series.notna() & (dt_series <= now)
            elif op == "<":
                valid_mask = dt_series.notna() & (dt_series < now)
            elif op == ">=":
                valid_mask = dt_series.notna() & (dt_series >= now)
            elif op == ">":
                valid_mask = dt_series.notna() & (dt_series > now)
            elif op == "==":
                valid_mask = dt_series.notna() & (dt_series == now)
            elif op == "!=":
                valid_mask = dt_series.notna() & (dt_series != now)
            else:
                valid_mask = pd.Series(False, index=series.index)

            return ~valid_mask, None

        # Numeric comparison
        try:
            target_num = float(target_str)
            num_series = pd.to_numeric(series, errors="coerce")
            if op == ">":
                valid_mask = num_series.notna() & (num_series > target_num)
            elif op == ">=":
                valid_mask = num_series.notna() & (num_series >= target_num)
            elif op == "<":
                valid_mask = num_series.notna() & (num_series < target_num)
            elif op == "<=":
                valid_mask = num_series.notna() & (num_series <= target_num)
            elif op == "==":
                valid_mask = num_series.notna() & (num_series == target_num)
            elif op == "!=":
                valid_mask = num_series.notna() & (num_series != target_num)
            else:
                valid_mask = pd.Series(False, index=series.index)
            return ~valid_mask, None
        except ValueError:
            # Fallback string comparison
            str_series = series.astype(str)
            clean_target = target_str.strip("'\"")
            if op == "==":
                valid_mask = str_series == clean_target
            elif op == "!=":
                valid_mask = str_series != clean_target
            else:
                valid_mask = pd.Series(False, index=series.index)
            return ~valid_mask, None

    raise YAMLRuleParsingError(
        f"Unsupported condition syntax: '{cond}'. "
        "Supported formats: 'not_null', 'email', 'between(min, max)', 'regex(...)', "
        "'> X', '>= X', '< X', '<= X', '<= today', '== X', '!= X'."
    )


def validate_dataframe(
    df: pd.DataFrame,
    yaml_path: Union[str, Path, dict, list],
    include_duplicates_check: bool = True,
) -> Dict[str, Any]:
    """Validates a Pandas DataFrame against rules defined in a YAML file.

    Key Logic:
        - Score = 100 * (N - N_пр) / N
        - N_пр includes rows with 'reject', 'flag' violations and duplicate rows.
        - Action 'block' DOES NOT decrease Quality Score, but sets 'can_publish = False'
          and 'has_blocking_violations = True'.
        - Duplicates: df.duplicated(keep='first') marks 2nd+ occurrences as violations.

    Args:
        df: The pandas DataFrame to validate.
        yaml_path: Path to the YAML rules file (or loaded rules list/dict).
        include_duplicates_check: Whether to include duplicate rows in Quality Score.

    Returns:
        Dict containing Score, total_rows, unique_violating_rows,
        can_publish, has_blocking_violations, violations, etc.
        Each violation includes ``violation_count`` and at most
        ``MAX_VIOLATING_INDICES`` row indices.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"Expected df to be a pandas DataFrame, got {type(df).__name__}."
        )

    rules = parse_yaml_rules(yaml_path)
    n_total = len(df)

    if n_total == 0:
        return {
            "Score": 100.0,
            "total_rows": 0,
            "unique_violating_rows": 0,
            "violation_count": 0,
            "can_publish": True,
            "has_blocking_violations": False,
            "violations": [],
            "duplicated_rows_count": 0,
        }

    # Mask for rows affecting Quality Score (reject, flag, duplicates)
    score_violating_rows_mask = pd.Series(False, index=df.index)
    has_blocking_violations = False
    violations_summary: List[Dict[str, Any]] = []
    total_rule_violations = 0

    # 1. Evaluate YAML rules
    for rule in rules:
        col = rule["column"]
        cond = rule["condition"]
        action = rule["action"]

        if col not in df.columns:
            available = ", ".join(str(column) for column in df.columns)
            raise YAMLRuleParsingError(
                f"Column '{col}' required by rule '{cond}' was not found "
                f"in DataFrame. Available columns: {available}."
            )

        violation_mask, _ = _evaluate_condition(df[col], cond)
        v_count = int(violation_mask.sum())
        message = (
            f"Rule '{cond}' on column '{col}' violated in {v_count} row(s)"
            if v_count > 0
            else "OK"
        )

        if v_count > 0:
            total_rule_violations += v_count
            if action == "block":
                # Action 'block' halts publication, but does NOT penalize Quality Score
                has_blocking_violations = True
            else:
                # Actions 'reject' and 'flag' affect Quality Score
                score_violating_rows_mask |= violation_mask

        violations_summary.append(
            {
                "column": col,
                "condition": cond,
                "action": action,
                "violation_count": v_count,
                "is_blocking": action == "block" and v_count > 0,
                "violating_indices": df.index[violation_mask].tolist()[
                    :MAX_VIOLATING_INDICES
                ],
                "violating_indices_truncated": (
                    v_count > MAX_VIOLATING_INDICES
                ),
                "message": message,
            }
        )

    # 2. Duplicate rows check (df.duplicated(keep='first'))
    dup_mask = df.duplicated(keep="first")
    dup_count = int(dup_mask.sum())
    if include_duplicates_check and dup_count > 0:
        score_violating_rows_mask |= dup_mask
        total_rule_violations += dup_count
        violations_summary.append(
            {
                "column": "*",
                "condition": "not_duplicated",
                "action": "flag",
                "violation_count": dup_count,
                "is_blocking": False,
                "violating_indices": df.index[dup_mask].tolist()[
                    :MAX_VIOLATING_INDICES
                ],
                "violating_indices_truncated": (
                    dup_count > MAX_VIOLATING_INDICES
                ),
                "message": f"Found {dup_count} duplicate row(s) in DataFrame",
            }
        )

    # 3. Calculate Quality Score: Score = 100 * (N - N_пр) / N
    n_pr = int(score_violating_rows_mask.sum())
    score = round(100.0 * (n_total - n_pr) / n_total, 1)

    return {
        "Score": score,
        "total_rows": n_total,
        "unique_violating_rows": n_pr,
        "violation_count": total_rule_violations,
        "can_publish": not has_blocking_violations,
        "has_blocking_violations": has_blocking_violations,
        "violations": violations_summary,
        "duplicated_rows_count": dup_count,
    }


evaluate_quality = validate_dataframe
