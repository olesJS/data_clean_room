"""Data profiling and PII detection module for Data Clean Room.

Analyses a pandas DataFrame and returns a structured profile JSON
that includes column statistics, PII detection, data classification,
and a quality score.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Dictionary loaders for high-precision PII detection
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DICT_DIR = _BASE_DIR / "data" / "pii" / "dictionaries"

_FIRST_NAMES: set[str] = set()
_SURNAMES: set[str] = set()
_OBLASTS: set[str] = set()
_ADDRESS_WORDS: set[str] = set()


def _load_dictionaries():
    global _FIRST_NAMES, _SURNAMES, _OBLASTS, _ADDRESS_WORDS
    if _FIRST_NAMES:
        return
    try:

        def read_words(path: Path) -> set[str]:
            if not path.exists():
                return set()
            words = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        words.add(line.lower())
            return words

        _FIRST_NAMES.update(read_words(_DICT_DIR / "first_names_male_uk.txt"))
        _FIRST_NAMES.update(read_words(_DICT_DIR / "first_names_female_uk.txt"))
        _SURNAMES.update(read_words(_DICT_DIR / "surnames_uk.txt"))
        _OBLASTS.update(read_words(_DICT_DIR / "oblasts_uk.txt"))
        _ADDRESS_WORDS.update(read_words(_DICT_DIR / "address_words_uk.txt"))
    except Exception:
        pass


_load_dictionaries()


# ---------------------------------------------------------------------------
# Validation helpers (Luhn, Checksum, Mod97, UA Phone)
# ---------------------------------------------------------------------------


def _luhn_check(number: str) -> bool:
    """Return True if *number* is 16 digits and passes Luhn algorithm."""
    clean = re.sub(r"[\s\-]", "", str(number))
    if len(clean) != 16 or not clean.isdigit():
        return False
    digits = [int(d) for d in clean]
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
    """Validate Ukrainian IPN 10-digit control checksum."""
    s = str(s).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if len(s) != 10 or not s.isdigit():
        return False
    d = [int(c) for c in s]
    control = (
        (
            (-1) * d[0]
            + 5 * d[1]
            + 7 * d[2]
            + 9 * d[3]
            + 4 * d[4]
            + 6 * d[5]
            + 10 * d[6]
            + 5 * d[7]
            + 7 * d[8]
        )
        % 11
        % 10
    )
    return control == d[9]


def _iban_mod97(s: str) -> bool:
    """Validate UA IBAN with standard ISO 7064 mod 97 check."""
    s = re.sub(r"\s+", "", str(s)).upper()
    if not (s.startswith("UA") and len(s) == 29 and s[2:].isdigit()):
        return False
    # Move 'UA' to end -> U=30, A=10 => '3010'
    rearranged = s[4:] + "3010" + s[2:4]
    try:
        return int(rearranged) % 97 == 1
    except Exception:
        return False


_UA_OPERATORS = (
    "050",
    "063",
    "066",
    "067",
    "068",
    "073",
    "089",
    "091",
    "092",
    "093",
    "094",
    "095",
    "096",
    "097",
    "098",
    "099",
)


def _is_ua_phone(s: str) -> bool:
    """Strict Ukrainian mobile phone validation."""
    digits = re.sub(r"\D", "", str(s))
    if len(digits) == 12 and digits.startswith("380"):
        digits = digits[2:]
    return len(digits) == 10 and digits.startswith(_UA_OPERATORS)


# Regex patterns using Unicode escapes to prevent Windows cp1252 corruption
_RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
# Ukrainian Cyrillic uppercase: [\u0410-\u042f\u0490\u0404\u0406\u0407]
_RE_PASSPORT_BOOK = re.compile(r"^[\u0410-\u042f\u0490\u0404\u0406\u0407]{2}\s?\d{6}$")
_RE_PASSPORT_ID = re.compile(r"^\d{9}$")
_RE_NAME_INITIALS = re.compile(
    r"^[\u0410-\u042f\u0490\u0404\u0406\u0407][\u0430-\u044f\u0491\u0454\u0456\u0457\']+\s+[\u0410-\u042f\u0490\u0404\u0406\u0407]\.\s?[\u0410-\u042f\u0490\u0404\u0406\u0407]\.$"
)

_NAME_KEYWORDS = [
    "name",
    "fname",
    "lname",
    "surname",
    "first_name",
    "last_name",
    "patronymic",
    "full_name",
    "\u0456\u043c'\u044f",
    "\u0456\u043c\u044f",
    "\u043f\u0440\u0456\u0437\u0432\u0438\u0449\u0435",
]

_NON_NAME_COLUMNS = {
    "brand_name",
    "product_line",
    "city_name",
    "company_name",
    "position",
    "department",
    "order_number",
    "invoice_no",
    "transaction_id",
    "contract_ref",
    "part_number",
    "order_id",
}


# ---------------------------------------------------------------------------
# Masking sample helper for UI (PiiPage)
# ---------------------------------------------------------------------------


def mask_sample(val: Any, pii_type: str | None) -> str:
    """Create a masked preview string for UI."""
    if val is None or pd.isna(val):
        return "\u2014"
    s = str(val).strip()
    if not s:
        return "\u2014"

    if pii_type in ("ipn", "UA_IPN"):
        return s[:5] + "*****" if len(s) >= 5 else s + "***"
    elif pii_type in ("iban", "UA_IBAN"):
        return s[:7] + " **** " + s[-4:] if len(s) >= 12 else s[:4] + "****"
    elif pii_type in ("email", "EMAIL"):
        if "@" in s:
            name, domain = s.split("@", 1)
            return (name[:2] + "***@" + domain) if len(name) >= 2 else "***@" + domain
        return s[:3] + "***"
    elif pii_type in ("phone", "UA_PHONE"):
        return s[:7] + " ***-**-" + s[-2:] if len(s) >= 10 else s[:4] + "***"
    elif pii_type in ("card", "CREDIT_CARD"):
        clean = re.sub(r"[\s\-]", "", s)
        return clean[:4] + " **** **** " + clean[-4:] if len(clean) >= 12 else "****"
    elif pii_type in ("passport", "UA_PASSPORT"):
        return s[:2] + " ****" + s[-2:] if len(s) >= 6 else s[:2] + "****"
    elif pii_type in ("person_name", "UA_FULL_NAME"):
        parts = s.split()
        if len(parts) >= 2:
            return parts[0] + " " + parts[1][0] + "***"
        return s[:2] + "***" if len(s) >= 2 else s + "***"
    elif pii_type in ("address", "UA_ADDRESS"):
        return s[:12] + "..." if len(s) > 12 else s
    return s[:4] + "***"


# ---------------------------------------------------------------------------
# PII Detection Core
# ---------------------------------------------------------------------------


def detect_pii(series: pd.Series, col_name: str) -> dict:
    """Detect PII type and confidence in a Series.

    Returns canonical PII types:
        "person_name", "ipn", "iban", "email", "phone", "passport", "card", "address"
    """
    _load_dictionaries()
    col_lower = col_name.lower().strip()

    # Guard against false positives in known non-PII columns
    if col_lower in _NON_NAME_COLUMNS:
        return {
            "is_pii": False,
            "pii_type": None,
            "pii_confidence": None,
            "detection_method": "regex",
            "sample_masked": None,
        }

    non_null = series.dropna()
    if len(non_null) == 0:
        return {
            "is_pii": False,
            "pii_type": None,
            "pii_confidence": None,
            "detection_method": "regex",
            "sample_masked": None,
        }

    def to_clean_str(v):
        if isinstance(v, (int, float)) and not pd.isna(v):
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
        return str(v).strip()

    str_sample = non_null.head(100).apply(to_clean_str)
    n = len(str_sample)
    first_val = str_sample.iloc[0] if n > 0 else None

    # 1. IPN
    ipn_matches = str_sample.apply(_ua_ipn_checksum)
    if ipn_matches.sum() / n >= 0.70:
        return {
            "is_pii": True,
            "pii_type": "ipn",
            "pii_confidence": 0.98,
            "detection_method": "regex+checksum",
            "sample_masked": mask_sample(first_val, "ipn"),
        }

    # 2. IBAN
    iban_matches = str_sample.apply(_iban_mod97)
    if iban_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "iban",
            "pii_confidence": 0.99,
            "detection_method": "regex+checksum",
            "sample_masked": mask_sample(first_val, "iban"),
        }

    # 3. CARD (16 digits + Luhn)
    card_matches = str_sample.apply(_luhn_check)
    if card_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "card",
            "pii_confidence": 0.99,
            "detection_method": "regex+luhn",
            "sample_masked": mask_sample(first_val, "card"),
        }

    # 4. EMAIL
    email_matches = str_sample.apply(lambda v: bool(_RE_EMAIL.match(v)))
    if email_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "email",
            "pii_confidence": 0.99,
            "detection_method": "regex",
            "sample_masked": mask_sample(first_val, "email"),
        }

    # 5. PASSPORT (book: AA 123456 or ID: 9 digits with passport column name)
    passport_book_matches = str_sample.apply(lambda v: bool(_RE_PASSPORT_BOOK.match(v)))
    if passport_book_matches.sum() / n >= 0.30:
        return {
            "is_pii": True,
            "pii_type": "passport",
            "pii_confidence": 0.95,
            "detection_method": "regex",
            "sample_masked": mask_sample(first_val, "passport"),
        }

    if "passport" in col_lower:
        passport_id_matches = str_sample.apply(lambda v: bool(_RE_PASSPORT_ID.match(v)))
        if passport_id_matches.sum() / n >= 0.30:
            return {
                "is_pii": True,
                "pii_type": "passport",
                "pii_confidence": 0.90,
                "detection_method": "column_name+regex",
                "sample_masked": mask_sample(first_val, "passport"),
            }

    # 6. PHONE (Strict Ukrainian mobile phone with operator code check)
    phone_matches = str_sample.apply(_is_ua_phone)
    if phone_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "phone",
            "pii_confidence": 0.95,
            "detection_method": "regex",
            "sample_masked": mask_sample(first_val, "phone"),
        }

    # 7. ADDRESS
    addr_kw = [
        "\u043c.",
        "\u0432\u0443\u043b\u0438\u0446\u044f",
        "\u0432\u0443\u043b.",
        "\u043f\u0440\u043e\u0432.",
        "\u0431\u0443\u043b\u044c\u0432.",
        "\u043a\u0432.",
        "\u043e\u0431\u043b\u0430\u0441\u0442\u044c",
        "\u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442",
        "\u043f\u0440\u043e\u0441\u043f.",
    ]
    addr_matches = str_sample.apply(
        lambda v: sum(kw in v.lower() for kw in addr_kw) >= 2
    )
    if addr_matches.sum() / n >= 0.50 or (
        "address" in col_lower and addr_matches.sum() / n >= 0.20
    ):
        return {
            "is_pii": True,
            "pii_type": "address",
            "pii_confidence": 0.92,
            "detection_method": "dictionary",
            "sample_masked": mask_sample(first_val, "address"),
        }

    # 8. PERSON NAME (Initials, Full Name, Dictionary)
    name_kw_found = any(kw in col_lower for kw in _NAME_KEYWORDS)

    initials_matches = str_sample.apply(lambda v: bool(_RE_NAME_INITIALS.match(v)))
    if initials_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "person_name",
            "pii_confidence": 0.95,
            "detection_method": "regex",
            "sample_masked": mask_sample(first_val, "person_name"),
        }

    def is_name_words(val: str) -> bool:
        words = [
            w.lower()
            for w in re.findall(
                r"[\u0410-\u044f\u0490\u0491\u0404\u0454\u0406\u0456\u0407\u0457\']+",
                val,
            )
        ]
        if not words:
            return False
        has_patronymic = any(
            w.endswith(
                (
                    "\u043e\u0432\u0438\u0447",
                    "\u0435\u0432\u0438\u0447",
                    "\u0456\u0432\u043d\u0430",
                    "\u0457\u0432\u043d\u0430",
                )
            )
            for w in words
        )
        in_dict = any(w in _FIRST_NAMES or w in _SURNAMES for w in words)
        return has_patronymic or in_dict

    dict_name_matches = str_sample.apply(is_name_words)
    dict_name_ratio = dict_name_matches.sum() / n

    if name_kw_found and dict_name_ratio >= 0.40:
        return {
            "is_pii": True,
            "pii_type": "person_name",
            "pii_confidence": 0.96,
            "detection_method": "dictionary",
            "sample_masked": mask_sample(first_val, "person_name"),
        }

    if dict_name_ratio >= 0.70 and not any(ch.isdigit() for ch in first_val or ""):
        return {
            "is_pii": True,
            "pii_type": "person_name",
            "pii_confidence": 0.85,
            "detection_method": "dictionary",
            "sample_masked": mask_sample(first_val, "person_name"),
        }

    return {
        "is_pii": False,
        "pii_type": None,
        "pii_confidence": None,
        "detection_method": "regex",
        "sample_masked": None,
    }


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
    # Try datetime heuristic safely
    non_null = series.dropna().astype(str)
    if len(non_null) > 0:
        try:
            # Only test on ISO format or date format strings (YYYY-MM-DD or DD.MM.YYYY)
            sample_val = non_null.iloc[0]
            if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", sample_val) or re.match(
                r"^\d{2}\.\d{2}\.\d{4}", sample_val
            ):
                parsed = pd.to_datetime(non_null.head(50), errors="coerce")
                if parsed.notna().sum() / len(parsed) >= 0.8:
                    return "datetime"
        except Exception:
            pass
    return "string"


# ---------------------------------------------------------------------------
# Outlier detection
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
    now = datetime.now(timezone.utc)
    clean = series.dropna()
    try:
        if not pd.api.types.is_datetime64_any_dtype(clean):
            clean = pd.to_datetime(clean, errors="coerce").dropna()
        if hasattr(clean, "dt") and clean.dt.tz is None:
            clean = clean.dt.tz_localize("UTC")
        return int((clean > pd.Timestamp(now)).sum())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Histograms
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


def _safe_scalar(val: Any) -> Any:
    if val is None:
        return None
    try:
        import numpy as np  # noqa: F401

        if isinstance(val, (float,)) and (val != val):
            return None
        if hasattr(val, "item"):
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
    pii_findings: list[dict] = []

    for col in df.columns:
        series = df[col]
        col_type = _classify_col_type(series)

        null_count = int(series.isna().sum())
        null_pct = round(null_count / total_rows * 100, 2) if total_rows > 0 else 0.0
        unique_count = int(series.nunique())

        pii_info = detect_pii(series, str(col))

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
            parsed = series
            if not pd.api.types.is_datetime64_any_dtype(series):
                parsed = pd.to_datetime(series, errors="coerce")
            clean = parsed.dropna()
            col_min = str(clean.min()) if len(clean) else None
            col_max = str(clean.max()) if len(clean) else None
            outliers_count = _count_outliers_datetime(parsed)

        columns_profile.append(
            {
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
            }
        )

        if pii_info["is_pii"]:
            pii_findings.append(
                {
                    "column_name": str(col),
                    "pii_type": pii_info["pii_type"],
                    "confidence": pii_info["pii_confidence"],
                    "sample_masked": pii_info["sample_masked"],
                    "detection_method": pii_info["detection_method"],
                    "user_confirmed": None,
                    "corrected_pii_type": None,
                }
            )

    # Data class assignment
    pii_types_found = {
        cp["pii_type"] for cp in columns_profile if cp["is_pii"] and cp["pii_type"]
    }

    personal_markers = {"ipn", "passport", "card"}
    confidential_markers = {"iban", "email", "phone", "person_name", "address"}

    if pii_types_found & personal_markers:
        data_class = "Personal"
    elif pii_types_found & confidential_markers:
        data_class = "Confidential"
    else:
        data_class = "Internal"

    # Quality score
    if total_rows == 0:
        quality_score = 0.0
    else:
        rows_with_null = int(df.isnull().any(axis=1).sum())
        violated_rows = rows_with_null + duplicate_rows_count
        quality_score = max(
            0.0, round(100 * (total_rows - violated_rows) / total_rows, 1)
        )

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
        "pii_findings": pii_findings,
    }
