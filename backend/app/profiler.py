"""Data profiling module for Data Clean Room.

Analyses a pandas DataFrame and returns a structured profile JSON
that includes column statistics, PII detection, data classification,
and a quality score.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# PII detection helpers
# ---------------------------------------------------------------------------

def _luhn_check(number: str) -> bool:
    """Return True if *number* passes the Luhn algorithm."""
    digits = [int(d) for d in number]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        d *= 2
        if d > 9:
            d -= 9
        total += d
    return total % 10 == 0


def _ua_ipn_checksum(s: str) -> bool:
    """Validate Ukrainian IPN (РНОКПП) 10-digit control checksum."""
    if len(s) != 10 or not s.isdigit():
        return False
    d = [int(c) for c in s]
    control = ((-1)*d[0] + 5*d[1] + 7*d[2] + 9*d[3] + 4*d[4] +
               6*d[5] + 10*d[6] + 5*d[7] + 7*d[8]) % 11 % 10
    return control == d[9]


_RE_UA_IPN   = re.compile(r'^\d{10}$')
_RE_UA_IBAN  = re.compile(r'^UA\d{27}$')
_RE_EMAIL    = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_RE_PHONE    = re.compile(r'^(\+380|0)\d{9}$')
_RE_PASSPORT = re.compile(r'^[А-ЯІЇЄ]{2}\d{6}$')
_RE_CARD     = re.compile(r'^\d{16}$')

_NAME_KEYWORDS = [
    'name', 'ім', 'піб', 'прізвище', 'fname', 'lname',
    'surname', 'first_name', 'last_name',
]


def detect_pii(series: pd.Series, col_name: str) -> dict:
    """Return PII detection result for a column sample.

    Returns::

        {"is_pii": bool, "pii_type": str|None, "pii_confidence": float|None}
    """
    # Work on a sample of up to 100 non-null string values
    non_null = series.dropna().astype(str)
    sample = non_null.head(100)
    n = len(sample)

    candidates: list[tuple[str, float]] = []  # (pii_type, confidence)

    if n > 0:
        # 1. UA_IPN
        ipn_matches = sample.apply(
            lambda v: bool(_RE_UA_IPN.match(v)) and _ua_ipn_checksum(v)
        )
        ipn_ratio = ipn_matches.sum() / n
        if ipn_ratio >= 0.70:
            candidates.append(("UA_IPN", 0.95))
        elif ipn_ratio >= 0.30:
            candidates.append(("UA_IPN", 0.70))

        # 2. UA_IBAN
        iban_matches = sample.apply(lambda v: bool(_RE_UA_IBAN.match(v)))
        iban_ratio = iban_matches.sum() / n
        if iban_ratio >= 0.50:
            candidates.append(("UA_IBAN", 0.99))
        elif iban_ratio >= 0.10:
            candidates.append(("UA_IBAN", 0.80))

        # 3. EMAIL
        email_matches = sample.apply(lambda v: bool(_RE_EMAIL.match(v)))
        email_ratio = email_matches.sum() / n
        if email_ratio >= 0.50:
            candidates.append(("EMAIL", 0.95))
        elif email_ratio >= 0.20:
            candidates.append(("EMAIL", 0.75))

        # 4. PHONE
        phone_matches = sample.apply(lambda v: bool(_RE_PHONE.match(v)))
        phone_ratio = phone_matches.sum() / n
        if phone_ratio >= 0.50:
            candidates.append(("PHONE", 0.90))
        elif phone_ratio >= 0.20:
            candidates.append(("PHONE", 0.70))

        # 5. PASSPORT
        passport_matches = sample.apply(lambda v: bool(_RE_PASSPORT.match(v)))
        passport_ratio = passport_matches.sum() / n
        if passport_ratio >= 0.30:
            candidates.append(("PASSPORT", 0.85))

        # 6. CARD (16 digits + Luhn)
        card_matches = sample.apply(
            lambda v: bool(_RE_CARD.match(v)) and _luhn_check(v)
        )
        card_ratio = card_matches.sum() / n
        if card_ratio >= 0.30:
            candidates.append(("CARD", 0.90))

        # 7. NAME — heuristic via column name first
        col_lower = col_name.lower()
        name_by_col = any(kw in col_lower for kw in _NAME_KEYWORDS)
        if name_by_col:
            candidates.append(("NAME", 0.60))

        # Strengthen NAME confidence if values look like real names
        name_value_ratio = sample.apply(
            lambda v: not any(ch.isdigit() for ch in v) and 2 <= len(v) <= 50
        ).sum() / n
        if name_value_ratio >= 0.50:
            # Replace or improve NAME confidence
            existing_name = next((i for i, (t, _) in enumerate(candidates) if t == "NAME"), None)
            if existing_name is not None:
                candidates[existing_name] = ("NAME", 0.75)
            else:
                candidates.append(("NAME", 0.75))

    if not candidates:
        return {"is_pii": False, "pii_type": None, "pii_confidence": None}

    # Pick the candidate with the highest confidence
    best_type, best_conf = max(candidates, key=lambda x: x[1])
    return {"is_pii": True, "pii_type": best_type, "pii_confidence": best_conf}


# ---------------------------------------------------------------------------
# Column type classification
# ---------------------------------------------------------------------------

def _classify_col_type(series: pd.Series) -> str:
    """Return one of: 'numeric', 'datetime', 'boolean', 'string'."""
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    # Try to parse as datetime
    non_null = series.dropna()
    if len(non_null) > 0:
        try:
            parsed = pd.to_datetime(non_null.head(50), infer_datetime_format=True, errors="coerce")
            if parsed.notna().sum() / len(parsed) >= 0.8:
                return "datetime"
        except Exception:
            pass
    return "string"


# ---------------------------------------------------------------------------
# Outlier detection (IQR method for numeric)
# ---------------------------------------------------------------------------

def _count_outliers_numeric(series: pd.Series) -> int:
    clean = series.dropna()
    if len(clean) < 4:
        return 0
    q1 = clean.quantile(0.25)
    q3 = clean.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return int(((clean < lower) | (clean > upper)).sum())


def _count_outliers_datetime(series: pd.Series) -> int:
    """Count future dates as outliers."""
    now = datetime.now(timezone.utc)
    clean = series.dropna()
    try:
        if not pd.api.types.is_datetime64_any_dtype(clean):
            clean = pd.to_datetime(clean, errors="coerce").dropna()
        # Make all tz-aware for comparison
        if hasattr(clean, 'dt') and clean.dt.tz is None:
            clean = clean.dt.tz_localize('UTC')
        return int((clean > pd.Timestamp(now)).sum())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Histogram for numeric columns
# ---------------------------------------------------------------------------

def _build_histogram(series: pd.Series) -> dict | None:
    clean = series.dropna()
    n_unique = clean.nunique()
    if len(clean) == 0:
        return None
    bins = min(5, max(1, n_unique))
    try:
        cut = pd.cut(clean, bins=bins, duplicates="drop")
        counts = cut.value_counts(sort=False)
        bin_labels = [str(interval) for interval in counts.index]
        return {"bins": bin_labels, "counts": [int(c) for c in counts.values]}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Safe scalar serialisation
# ---------------------------------------------------------------------------

def _safe_scalar(val: Any) -> Any:
    """Convert numpy/pandas scalars to native Python types."""
    if val is None:
        return None
    try:
        import numpy as np  # noqa: F401
        if isinstance(val, (float,)) and (val != val):  # NaN
            return None
        if hasattr(val, 'item'):  # numpy scalar
            return val.item()
    except ImportError:
        pass
    if isinstance(val, pd.Timestamp):
        return str(val)
    return val


# ---------------------------------------------------------------------------
# Main profiling entry point
# ---------------------------------------------------------------------------

def profile_dataframe(df: pd.DataFrame, dataset_id: int, dataset_name: str) -> dict:
    """Analyse *df* and return the canonical profile dict."""
    total_rows = len(df)
    total_columns = len(df.columns)

    duplicate_rows_count = int(df.duplicated().sum())

    columns_profile: list[dict] = []

    for col in df.columns:
        series = df[col]
        col_type = _classify_col_type(series)

        null_count = int(series.isna().sum())
        null_pct = round(null_count / total_rows * 100, 2) if total_rows > 0 else 0.0
        unique_count = int(series.nunique())

        pii_info = detect_pii(series, col)

        # min / max / mean / outliers / histogram
        col_min = col_max = col_mean = None
        outliers_count = 0
        histogram = None

        if col_type == "numeric":
            clean = series.dropna()
            col_min = _safe_scalar(clean.min()) if len(clean) else None
            col_max = _safe_scalar(clean.max()) if len(clean) else None
            col_mean = round(float(clean.mean()), 4) if len(clean) else None
            outliers_count = _count_outliers_numeric(series)
            histogram = _build_histogram(series)

        elif col_type == "datetime":
            # Try to parse if not already datetime
            parsed = series
            if not pd.api.types.is_datetime64_any_dtype(series):
                parsed = pd.to_datetime(series, errors="coerce")
            clean = parsed.dropna()
            col_min = str(clean.min()) if len(clean) else None
            col_max = str(clean.max()) if len(clean) else None
            outliers_count = _count_outliers_datetime(parsed)

        columns_profile.append({
            "name": str(col),
            "type": col_type,
            "null_count": null_count,
            "null_percentage": null_pct,
            "unique_count": unique_count,
            "is_pii": pii_info["is_pii"],
            "pii_type": pii_info["pii_type"],
            "pii_confidence": pii_info["pii_confidence"],
            "min": col_min,
            "max": col_max,
            "mean": col_mean,
            "outliers_count": outliers_count,
            "histogram": histogram,
        })

    # -----------------------------------------------------------------------
    # data_class
    # -----------------------------------------------------------------------
    pii_types_found = {
        cp["pii_type"] for cp in columns_profile if cp["is_pii"] and cp["pii_type"]
    }

    personal_markers = {"UA_IPN", "PASSPORT", "CARD"}
    confidential_markers = {"UA_IBAN", "EMAIL", "PHONE", "NAME"}

    if pii_types_found & personal_markers:
        data_class = "Personal"
    elif pii_types_found & confidential_markers:
        data_class = "Confidential"
    elif duplicate_rows_count > total_rows * 0.1:
        data_class = "Internal"
    else:
        data_class = "Internal"

    # -----------------------------------------------------------------------
    # Quality score
    # -----------------------------------------------------------------------
    if total_rows == 0:
        quality_score = 0.0
    else:
        # Rows that have at least one null in any column
        rows_with_null = int(df.isnull().any(axis=1).sum())
        violated_rows = rows_with_null + duplicate_rows_count
        quality_score = max(0.0, round(100 * (total_rows - violated_rows) / total_rows, 1))

    # rules_violated_count = columns with any null
    rules_violated_count = sum(1 for cp in columns_profile if cp["null_count"] > 0)

    return {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "data_class": data_class,
        "quality_score": quality_score,
        "summary": {
            "total_rows": total_rows,
            "total_columns": total_columns,
            "duplicate_rows_count": duplicate_rows_count,
            "rules_violated_count": rules_violated_count,
        },
        "columns": columns_profile,
    }

