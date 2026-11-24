"""Data-quality rules. Each rule is declared once and produces an issue log."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
REQUIRED = ["company_name", "contact_last_name", "email", "phone", "country", "segment"]


def present(value) -> bool:
    """True when a cell holds a real value (not None / NaN / empty)."""
    return value is not None and not (isinstance(value, float) and pd.isna(value)) and value != ""


def luhn_ok(number: str) -> bool:
    if not number.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


@dataclass(frozen=True)
class Rule:
    code: str
    column: str
    severity: str  # "bloquant" | "majeur" | "mineur"
    description: str
    failed: Callable[[pd.Series], bool]


def build_rules(today: date) -> list[Rule]:
    rules = [
        Rule(f"MISSING_{col.upper()}", col, "majeur" if col in ("email", "phone") else "mineur",
             f"Champ obligatoire manquant : {col}", lambda r, c=col: not present(r[c]))
        for col in REQUIRED
    ]
    rules += [
        Rule("INVALID_EMAIL", "email", "bloquant", "Format d'email invalide",
             lambda r: present(r["email"]) and not EMAIL_RE.match(r["email"])),
        Rule("INVALID_PHONE", "phone_raw", "majeur", "Téléphone non convertible au format international",
             lambda r: not present(r["phone"]) and present(r["phone_raw"])),
        Rule("UNKNOWN_COUNTRY", "country_raw", "mineur", "Pays non reconnu",
             lambda r: not present(r["country"]) and present(r["country_raw"])),
        Rule("INVALID_SIRET", "siret", "majeur", "SIRET invalide (14 chiffres + clé de Luhn)",
             lambda r: r["country"] == "FR" and present(r["siret"])
             and not (len(r["siret"]) == 14 and luhn_ok(r["siret"]))),
        Rule("FUTURE_CONTACT_DATE", "last_contact_date", "majeur", "Date de dernier contact dans le futur",
             lambda r: present(r["last_contact_date"]) and r["last_contact_date"] > today),
        Rule("STALE_ACCOUNT", "last_contact_date", "mineur", "Aucun contact depuis plus de 18 mois",
             lambda r: present(r["last_contact_date"])
             and (today - r["last_contact_date"]).days > 548),
    ]
    return rules


def run_rules(df: pd.DataFrame, today: date) -> pd.DataFrame:
    issues = []
    rules = build_rules(today)
    for _, row in df.iterrows():
        for rule in rules:
            if rule.failed(row):
                issues.append({
                    "record_id": row["record_id"], "subsidiary": row["subsidiary"], "rule": rule.code,
                    "column": rule.column, "severity": rule.severity, "description": rule.description,
                    "value": row.get(rule.column),
                })
    return pd.DataFrame(issues, columns=["record_id", "subsidiary", "rule", "column", "severity", "description", "value"])
