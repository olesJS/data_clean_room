import hashlib
import hmac
import os
import re
from typing import Optional

import pandas as pd

# Load HMAC key from environment. In production/test environments, this must be set.
HMAC_KEY = os.getenv("HMAC_KEY")
ENV = os.getenv("ENV", "development").lower()

if not HMAC_KEY:
    if ENV in ("development", "test", "dev"):
        HMAC_KEY = "dev_anonymization_secret_key_hmac_32_bytes_long!"
    else:
        err = "CRITICAL CONFIG ERROR: HMAC_KEY environment variable must be set!"
        raise RuntimeError(err)


def mask_val(val: Optional[str]) -> Optional[str]:
    """Masks value depending on detected PII pattern:

    - email -> i***@d***.com
    - phone -> +380*****67
    - ipn/iban/card/digits -> ******1234
    - general string -> first char + *** + last char
    """
    if val is None or pd.isna(val):
        return val

    s = str(val).strip()
    if not s:
        return s

    # Email
    if "@" in s:
        parts = s.split("@", 1)
        name, domain = parts[0], parts[1]
        m_name = (name[0] + "***") if name else "***"
        if "." in domain:
            d_parts = domain.rsplit(".", 1)
            d0, d1 = d_parts[0], d_parts[1]
            m_domain = (d0[0] + "***." + d1) if d0 else "***." + d1
        else:
            m_domain = domain[0] + "***" if domain else "***"
        return f"{m_name}@{m_domain}"

    # Phone e.g. +380501234567 or 0501234567 (with prefix e.g. +380 or starts with 0)
    cleaned_digits = re.sub(r"\D", "", s)
    if s.startswith("+") or (s.startswith("0") and len(cleaned_digits) == 10):
        prefix = s[:4] if s.startswith("+") else s[:3]
        suffix = s[-2:]
        return f"{prefix}*****{suffix}"

    # IPN (10 digits) / Card / IBAN (show last 4 digits)
    if len(s) >= 8 and any(c.isdigit() for c in s):
        return f"******{s[-4:]}"

    # Fallback short string
    if len(s) <= 2:
        return "**"
    return f"{s[0]}***{s[-1]}"


def generalize_val(val: Optional[str], kind: str = "auto") -> Optional[str]:
    """Generalizes value:

    - date -> year (YYYY)
    - age -> decade range (e.g. 34 -> "30-39")
    - city/address -> only city or general area
    """
    if val is None or pd.isna(val):
        return val

    s = str(val).strip()
    if not s:
        return s

    # Age check (numeric between 0 and 120)
    if kind == "age" or (kind == "auto" and s.isdigit() and 0 <= int(s) <= 120):
        age_num = int(s)
        decade_start = (age_num // 10) * 10
        decade_end = decade_start + 9
        return f"{decade_start}-{decade_end}"

    # Date check (YYYY-MM-DD or DD.MM.YYYY)
    date_match = re.search(r"(\d{4})[-/.]\d{2}[-/.]\d{2}", s)
    if date_match:
        return date_match.group(1)

    date_match_reverse = re.search(r"\d{2}[-/.]\d{2}[-/.](\d{4})", s)
    if date_match_reverse:
        return date_match_reverse.group(1)

    # Address generalization: strip street, house, apartment
    # E.g. "м. Київ, вул. Хрещатик, 1" -> "м. Київ"
    if "," in s:
        return s.split(",")[0].strip()

    return s


def hmac_sha256_val(val: Optional[str]) -> Optional[str]:
    """Computes deterministic HMAC-SHA256 hex digest for non-empty string."""
    if val is None or pd.isna(val):
        return val

    s = str(val).strip()
    if not s:
        return s

    key_bytes = HMAC_KEY.encode("utf-8")
    val_bytes = s.encode("utf-8")
    return hmac.new(key_bytes, val_bytes, hashlib.sha256).hexdigest()


def mask_series(series: pd.Series) -> pd.Series:
    return series.apply(mask_val)


def generalize_series(series: pd.Series, kind: str = "auto") -> pd.Series:
    return series.apply(lambda v: generalize_val(v, kind=kind))


def hmac_sha256_series(series: pd.Series) -> pd.Series:
    return series.apply(hmac_sha256_val)


def apply_anonymization(df: pd.DataFrame, methods: dict) -> pd.DataFrame:
    """Applies anonymization methods to DataFrame.

    methods: dict of {column_name: method_str}
    supported methods: "mask", "generalize", "hmac_sha256" (or "hmac")
    """
    df_copy = df.copy()
    for col, method in methods.items():
        if col not in df_copy.columns:
            continue
        m = method.lower()
        if m == "mask":
            df_copy[col] = mask_series(df_copy[col])
        elif m in ("generalize", "generalization"):
            df_copy[col] = generalize_series(df_copy[col])
        elif m in ("hmac", "hmac_sha256"):
            df_copy[col] = hmac_sha256_series(df_copy[col])
        else:
            raise ValueError(f"Unsupported anonymization method: {method}")
    return df_copy
