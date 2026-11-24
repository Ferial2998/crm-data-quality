"""Normalisation helpers: one function per field type, all pure and testable."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

import pandas as pd

LEGAL_FORM_RE = re.compile(r"\b(s\.?a\.?s\.?|s\.?a\.?r\.?l\.?|s\.?a\.?|ltd|limited|gmbh|spa|srl|inc)\b\.?", re.I)

COUNTRY_MAP = {
    "fr": "FR", "fra": "FR", "france": "FR",
    "it": "IT", "ita": "IT", "italie": "IT", "italy": "IT",
    "gb": "GB", "uk": "GB", "royaume-uni": "GB", "united kingdom": "GB",
    "ae": "AE", "uae": "AE", "emirats arabes unis": "AE", "united arab emirates": "AE",
    "ch": "CH", "suisse": "CH", "switzerland": "CH",
}
DIAL_CODES = {"FR": "33", "IT": "39", "GB": "44", "AE": "971", "CH": "41"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or (isinstance(value, str) and not value.strip())


def clean_text(value) -> str | None:
    """Trim and collapse whitespace; empty strings become None."""
    if _is_missing(value):
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def title_name(value) -> str | None:
    """'  camille ' -> 'Camille', 'MARTIN' -> 'Martin', keeps compound names."""
    v = clean_text(value)
    if v is None:
        return None
    return "-".join(part.capitalize() for part in v.lower().split("-"))


def company_key(value) -> str | None:
    """Matching key: lowercase, no accents, no legal form, no punctuation."""
    v = clean_text(value)
    if v is None:
        return None
    v = strip_accents(v.lower())
    v = LEGAL_FORM_RE.sub(" ", v)
    v = re.sub(r"[^a-z0-9 ]", " ", v)
    return re.sub(r"\s+", " ", v).strip() or None


def display_company(value) -> str | None:
    """Readable company name without legal form, e.g. 'MAISON AURÈLE SAS' -> 'Maison Aurèle'."""
    v = clean_text(value)
    if v is None:
        return None
    v = LEGAL_FORM_RE.sub(" ", v)
    v = re.sub(r"\s+", " ", v).strip(" .")
    if v.isupper():
        v = " ".join(w.capitalize() for w in v.lower().split())
    return v


def normalize_email(value) -> str | None:
    v = clean_text(value)
    return v.lower().replace(" ", "") if v else None


def normalize_country(value) -> str | None:
    v = clean_text(value)
    if v is None:
        return None
    return COUNTRY_MAP.get(strip_accents(v.lower()))


def normalize_phone(value, country: str | None) -> str | None:
    """Return E.164 (+33612345678) when possible, else None."""
    v = clean_text(value)
    if v is None:
        return None
    digits = re.sub(r"\D", "", v)
    if v.startswith("+"):
        e164 = digits
    elif digits.startswith("00"):
        e164 = digits[2:]
    elif digits.startswith("0") and country in DIAL_CODES:
        e164 = DIAL_CODES[country] + digits[1:]
    else:
        return None
    return "+" + e164 if 10 <= len(e164) <= 15 else None


def parse_date(value) -> date | None:
    v = clean_text(value)
    if v is None:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Return a standardized copy; raw columns are kept with a `_raw` suffix where values change."""
    out = df.copy()
    out["country_raw"] = out["country"]
    out["country"] = out["country"].map(normalize_country)
    out["company_name"] = out["company_name"].map(display_company)
    out["company_key"] = out["company_name"].map(company_key)
    out["contact_first_name"] = out["contact_first_name"].map(title_name)
    out["contact_last_name"] = out["contact_last_name"].map(title_name)
    out["email"] = out["email"].map(normalize_email)
    out["phone_raw"] = out["phone"]
    out["phone"] = [normalize_phone(p, c) for p, c in zip(out["phone"], out["country"])]
    out["siret"] = out["siret"].map(lambda s: re.sub(r"\D", "", str(s)) if clean_text(s) else None)
    out["last_contact_date"] = out["last_contact_date"].map(parse_date)
    for col in ("segment", "city", "subsidiary", "account_type"):
        out[col] = out[col].map(clean_text)
    out = out.astype(object)
    return out.where(out.notna(), None)
