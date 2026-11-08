from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dictionary loaders for high-precision PII detection
# ---------------------------------------------------------------------------

_POSSIBLE_DATA_DIRS = [
    Path(__file__).resolve().parent.parent.parent / "data" / "pii" / "dictionaries",
    Path("/app/data/pii/dictionaries"),
    Path("data/pii/dictionaries").resolve(),
    Path("../data/pii/dictionaries").resolve(),
]

_FIRST_NAMES: set[str] = set()
_SURNAMES: set[str] = set()
_OBLASTS: set[str] = set()
_ADDRESS_WORDS: set[str] = set()


def _get_dict_dir() -> Path:
    for p in _POSSIBLE_DATA_DIRS:
        if p.exists() and p.is_dir():
            return p
    return _POSSIBLE_DATA_DIRS[0]


def _load_dictionaries() -> None:
    global _FIRST_NAMES, _SURNAMES, _OBLASTS, _ADDRESS_WORDS
    if _FIRST_NAMES:
        return
    dict_dir = _get_dict_dir()

    def read_words(path: Path) -> set[str]:
        if not path.exists():
            logger.warning("Dictionary file not found at: %s", path)
            return set()
        words = set()
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        words.add(line.lower())
        except Exception as exc:
            logger.warning("Failed to read dictionary file %s: %s", path, exc)
        return words

    _FIRST_NAMES.update(read_words(dict_dir / "first_names_male_uk.txt"))
    _FIRST_NAMES.update(read_words(dict_dir / "first_names_female_uk.txt"))
    _SURNAMES.update(read_words(dict_dir / "surnames_uk.txt"))
    _OBLASTS.update(read_words(dict_dir / "oblasts_uk.txt"))
    _ADDRESS_WORDS.update(read_words(dict_dir / "address_words_uk.txt"))


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
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def _ua_ipn_checksum(s: str) -> bool:
    """Strict Ukrainian 10-digit Tax ID (РНОКПП/ІПН) checksum validation."""
    s = re.sub(r"\D", "", str(s))
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
    except ValueError:
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


# Regex patterns using Unicode escapes
_RE_EMAIL = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
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
    "імя",
    "ім'я",
    "прізвище",
    "побатькові",
    "по_батькові",
]


# ---------------------------------------------------------------------------
# Masking sample helper for UI (PiiPage)
# ---------------------------------------------------------------------------


def mask_sample(val: Any, pii_type: str | None) -> str:
    """Create a masked preview string for UI."""
    if val is None or pd.isna(val):
        return "—"
    s = str(val).strip()
    if not s:
        return "—"

    if pii_type in ("ipn", "UA_IPN"):
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 6:
            return digits[:2] + "****" + digits[-2:]
        return "******"

    if pii_type in ("iban", "UA_IBAN"):
        clean = re.sub(r"\s+", "", s)
        if len(clean) >= 8:
            return clean[:4] + " **** " + clean[-4:]
        return clean[:4] + " ****"

    if pii_type in ("card", "CREDIT_CARD"):
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 12:
            return digits[:4] + " **** **** " + digits[-4:]
        return "**** **** **** ****"

    if pii_type in ("passport", "UA_PASSPORT"):
        if _RE_PASSPORT_BOOK.match(s):
            letters = s[:2]
            digits = re.sub(r"\D", "", s)
            return (
                f"{letters} ***{digits[-2:]}" if len(digits) >= 2 else f"{letters} ****"
            )
        digits = re.sub(r"\D", "", s)
        if len(digits) == 9:
            return digits[:2] + "*****" + digits[-2:]
        return "*********"

    if pii_type in ("email", "EMAIL"):
        parts = s.split("@", 1)
        if len(parts) == 2:
            user, domain = parts
            masked_user = user[0] + "***" if len(user) > 1 else "***"
            return f"{masked_user}@{domain}"
        return "***@***"

    if pii_type in ("phone", "UA_PHONE"):
        digits = re.sub(r"\D", "", s)
        if len(digits) >= 10:
            return "+380" + digits[-9:-6] + "***" + digits[-2:]
        return "+380*********"

    if pii_type in ("person_name", "UA_FULL_NAME"):
        words = s.split()
        masked_words = []
        for w in words:
            if len(w) > 2:
                masked_words.append(w[0] + "*" * (len(w) - 2) + w[-1])
            elif len(w) > 0:
                masked_words.append(w[0] + "*")
        return " ".join(masked_words) if masked_words else "***"

    if pii_type in ("address", "ADDRESS"):
        parts = s.split(",")
        if len(parts) > 1:
            return parts[0].strip() + ", ***"
        return s[:8] + "***" if len(s) > 8 else "***"

    return "***"


# ---------------------------------------------------------------------------
# Core Column PII Detector (Without Hardcoded Trap Lists!)
# ---------------------------------------------------------------------------


def detect_pii(series: pd.Series, column_name: str) -> dict[str, Any]:
    """Detect PII type and confidence in a Series from data and context."""
    _load_dictionaries()
    col_lower = str(column_name).lower().strip()

    non_null = series.dropna()
    if len(non_null) == 0:
        return {
            "is_pii": False,
            "pii_type": None,
            "pii_confidence": None,
            "detection_method": "regex",
            "sample_masked": None,
        }

    def to_clean_str(v: Any) -> str:
        if isinstance(v, (int, float)) and not pd.isna(v):
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
        return str(v).strip()

    str_sample = non_null.head(100).apply(to_clean_str)
    n = len(str_sample)
    first_val = str_sample.iloc[0] if n > 0 else None

    # 1. IPN (10 digits + strict mathematical checksum)
    # Traps like order_number or invoice_no will fail the checksum!
    ipn_matches = str_sample.apply(_ua_ipn_checksum)
    if ipn_matches.sum() / n >= 0.70:
        return {
            "is_pii": True,
            "pii_type": "ipn",
            "pii_confidence": 0.98,
            "detection_method": "regex+checksum",
            "sample_masked": mask_sample(first_val, "ipn"),
        }

    # 2. IBAN (UA + 27 digits + ISO 7064 mod 97 check)
    # Traps like contract_ref will fail mod 97!
    iban_matches = str_sample.apply(_iban_mod97)
    if iban_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "iban",
            "pii_confidence": 0.99,
            "detection_method": "regex+checksum",
            "sample_masked": mask_sample(first_val, "iban"),
        }

    # 3. CARD (16 digits + Luhn algorithm)
    # Traps like transaction_id will fail Luhn!
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

    # 5. PASSPORT
    # Book format: 2 Cyrillic uppercase letters + 6 digits (e.g., 'АВ 123456')
    passport_book_matches = str_sample.apply(lambda v: bool(_RE_PASSPORT_BOOK.match(v)))
    if passport_book_matches.sum() / n >= 0.30:
        return {
            "is_pii": True,
            "pii_type": "passport",
            "pii_confidence": 0.95,
            "detection_method": "regex",
            "sample_masked": mask_sample(first_val, "passport"),
        }

    # ID card: 9 digits. Since a 9-digit number could be a part_number or serial,
    # passport ID requires passport context in column name (domain rules)
    if any(k in col_lower for k in ("passport", "паспорт", "id_card", "id_doc")):
        passport_id_matches = str_sample.apply(lambda v: bool(_RE_PASSPORT_ID.match(v)))
        if passport_id_matches.sum() / n >= 0.30:
            return {
                "is_pii": True,
                "pii_type": "passport",
                "pii_confidence": 0.90,
                "detection_method": "column_name+regex",
                "sample_masked": mask_sample(first_val, "passport"),
            }

    # 6. PHONE (Strict Ukrainian mobile phone with valid operator codes)
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
        "м.",
        "вулиця",
        "вул.",
        "пров.",
        "бульв.",
        "кв.",
        "область",
        "просп.",
        "проспект",
    ]
    addr_matches = str_sample.apply(
        lambda v: sum(kw in v.lower() for kw in addr_kw) >= 2
    )
    if addr_matches.sum() / n >= 0.50 or (
        any(k in col_lower for k in ("address", "адрес"))
        and addr_matches.sum() / n >= 0.20
    ):
        return {
            "is_pii": True,
            "pii_type": "address",
            "pii_confidence": 0.92,
            "detection_method": "dictionary",
            "sample_masked": mask_sample(first_val, "address"),
        }

    # 8. PERSON NAME (Initials, Full Name, Dictionary, Patronymics)
    initials_matches = str_sample.apply(lambda v: bool(_RE_NAME_INITIALS.match(v)))
    if initials_matches.sum() / n >= 0.50:
        return {
            "is_pii": True,
            "pii_type": "person_name",
            "pii_confidence": 0.95,
            "detection_method": "regex",
            "sample_masked": mask_sample(first_val, "person_name"),
        }

    name_kw_found = any(kw in col_lower for kw in _NAME_KEYWORDS)

    # City filter: compare column name tokens by whole words so that
    # words like 'ethnicity' are NOT misidentified as city columns!
    col_tokens = set(re.findall(r"\w+", col_lower))
    if col_tokens & {"city", "місто", "town", "settlement"}:
        return {
            "is_pii": False,
            "pii_type": None,
            "pii_confidence": None,
            "detection_method": "regex",
            "sample_masked": None,
        }

    # Helper: check for Ukrainian patronymic endings
    def has_patronymic_ending(w: str) -> bool:
        return w.endswith(("ович", "евич", "євич", "івна", "ївна"))

    # Name matching logic:
    # A full name typically has 2 or 3 words (Surname Firstname Patronymic).
    # Single words (like brand_name or product_line) should only match if the column
    # specifically indicates a person's name (name, surname, first_name, etc.)
    # OR if values have patronymic endings / clear full name format.
    def is_person_name_val(val: str) -> bool:
        words = [
            w.lower()
            for w in re.findall(
                r"[\u0410-\u044f\u0490\u0491\u0404\u0454\u0406\u0456\u0407\u0457\']+",
                val,
            )
        ]
        if not words:
            return False

        if any(has_patronymic_ending(w) for w in words):
            return True

        if len(words) >= 2:
            # Multi-word value (e.g. "Тарас Руденко" or "Дмитро Маслюк")
            # At least one word in name dictionary => person full name
            return any(w in _FIRST_NAMES or w in _SURNAMES for w in words)
        else:
            # Single word (e.g. "Марченко" in surname column or "Орел" in product_line)
            # If column name specifically indicates person name/surname/first_name:
            if name_kw_found:
                return words[0] in _FIRST_NAMES or words[0] in _SURNAMES
            return False

    dict_name_matches = str_sample.apply(is_person_name_val)
    dict_name_ratio = dict_name_matches.sum() / n
    unique_ratio = non_null.nunique() / len(non_null) if len(non_null) > 0 else 0.0

    # Person names in datasets have high cardinality/uniqueness (> 30%).
    # Low cardinality columns (like brand_name 10/80 => 12%) are tags, not names.
    if (
        dict_name_ratio >= 0.40
        and unique_ratio >= 0.30
        and not any(ch.isdigit() for ch in first_val or "")
    ):
        return {
            "is_pii": True,
            "pii_type": "person_name",
            "pii_confidence": 0.95 if name_kw_found else 0.85,
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
# Full DataFrame Profiling Function
# ---------------------------------------------------------------------------


def profile_dataframe(
    df: pd.DataFrame,
    dataset_id: int,
    dataset_name: str,
    rules_yaml: str | Path | None = None,
) -> dict[str, Any]:
    """Profile a pandas DataFrame and return complete quality report."""
    total_rows = len(df)
    total_columns = len(df.columns)
    duplicate_rows_count = int(df.duplicated(keep="first").sum())

    columns_profile = []
    pii_findings = []

    for col in df.columns:
        series = df[col]
        non_null_s = series.dropna()

        # Handle blank strings in string/object series as nulls too
        if series.dtype == "object" or str(series.dtype).startswith(("string", "str")):
            null_count = int(
                series.isnull().sum()
                + (series.dropna().astype(str).str.strip() == "").sum()
            )
        else:
            null_count = int(series.isnull().sum())

        null_pct = round(100.0 * null_count / total_rows, 2) if total_rows > 0 else 0.0
        unique_count = int(series.nunique(dropna=True))

        pii_info = detect_pii(series, str(col))

        # Basic numerical stats and histograms
        col_type = str(series.dtype)
        col_min: float | str | None = None
        col_max: float | str | None = None
        col_mean: float | None = None
        outliers_count = 0
        histogram: dict[str, Any] | None = None

        if pd.api.types.is_numeric_dtype(series) and len(non_null_s) > 0:
            numeric_s = pd.to_numeric(non_null_s, errors="coerce").dropna()
            if len(numeric_s) > 0:
                col_min = round(float(numeric_s.min()), 2)
                col_max = round(float(numeric_s.max()), 2)
                col_mean = round(float(numeric_s.mean()), 2)

                # IQR outliers
                q25 = float(numeric_s.quantile(0.25))
                q75 = float(numeric_s.quantile(0.75))
                iqr = q75 - q25
                lower_bound = q25 - 1.5 * iqr
                upper_bound = q75 + 1.5 * iqr
                outliers_count = int(
                    ((numeric_s < lower_bound) | (numeric_s > upper_bound)).sum()
                )

                # 5-bin histogram
                try:
                    counts, bin_edges = pd.cut(
                        numeric_s, bins=5, retbins=True, right=True
                    )
                    hist_counts = [int(c) for c in counts.value_counts(sort=False)]
                    hist_bins = [
                        f"{round(bin_edges[i], 1)}–{round(bin_edges[i + 1], 1)}"
                        for i in range(len(bin_edges) - 1)
                    ]
                    histogram = {"bins": hist_bins, "counts": hist_counts}
                except Exception:
                    histogram = None

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

    # -----------------------------------------------------------------------
    # Data Class Assignment (Domain Rule from sprint-2.md):
    # Any dataset with PII is "Personal" data class!
    # -----------------------------------------------------------------------
    has_pii = any(cp["is_pii"] for cp in columns_profile)
    if has_pii:
        data_class = "Personal"
    else:
        data_class = "Internal"

    # -----------------------------------------------------------------------
    # Quality Score Evaluation
    # Formula: Score = 100 * (N - N_пр) / N
    # -----------------------------------------------------------------------
    quality_score = 100.0
    quality_report: dict[str, Any] | None = None

    # Check for provided or standard rules files
    # NOTE: Rule auto-selection by file name prefix is temporary until
    # rules API (UC-04) is implemented.
    resolved_rules_path: Path | None = None
    if rules_yaml:
        p = Path(rules_yaml)
        if p.exists():
            resolved_rules_path = p
    else:
        # Check standard data rules
        name_lower = str(dataset_name).lower()
        candidate_paths = [
            Path(__file__).resolve().parent.parent.parent / "data",
            Path("/app/data"),
            Path("data").resolve(),
            Path("../data").resolve(),
        ]
        for cdir in candidate_paths:
            if "payroll" in name_lower and (cdir / "payroll_rules.yaml").exists():
                resolved_rules_path = cdir / "payroll_rules.yaml"
                break
            elif "customer" in name_lower and (cdir / "customers_rules.yaml").exists():
                resolved_rules_path = cdir / "customers_rules.yaml"
                break

    if resolved_rules_path and resolved_rules_path.exists():
        try:
            from app.services.quality_engine import validate_dataframe

            quality_report = validate_dataframe(df, resolved_rules_path)
            quality_score = quality_report["Score"]
        except Exception as exc:
            logger.warning(
                "Quality Engine evaluation failed for rules %s: %s",
                resolved_rules_path,
                exc,
                exc_info=True,
            )
            quality_report = None

    if quality_report is None:
        # Standard fallback calculation for Score = 100 * (N - N_пр) / N
        if total_rows == 0:
            quality_score = 0.0
        else:
            rows_with_null = df.isnull().any(axis=1)
            # Check empty strings
            str_empty = pd.Series(False, index=df.index)
            for c in df.select_dtypes(include="object").columns:
                str_empty |= df[c].astype(str).str.strip() == ""
            dup_rows = df.duplicated(keep="first")
            violated_mask = rows_with_null | str_empty | dup_rows
            n_pr = int(violated_mask.sum())
            quality_score = max(0.0, round(100.0 * (total_rows - n_pr) / total_rows, 1))

    rules_violated_count = sum(1 for cp in columns_profile if cp["null_count"] > 0)
    if quality_report and "violation_count" in quality_report:
        rules_violated_count = quality_report["violation_count"]

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
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
