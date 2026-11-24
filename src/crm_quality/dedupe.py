"""Duplicate detection across subsidiaries and golden-record consolidation.

Strategy
1. Blocking: only compare records sharing the same contact last name (cheap, avoids n^2).
2. Scoring: exact e-mail or phone match, or fuzzy company name + same contact.
3. Clustering: union-find over matched pairs.
4. Survivorship: one golden record per cluster, field by field.
"""
from __future__ import annotations

import pandas as pd
from rapidfuzz import fuzz

from .rules import EMAIL_RE

COMPANY_THRESHOLD = 88


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def canonical_company_names(df: pd.DataFrame, threshold: int = COMPANY_THRESHOLD) -> pd.Series:
    """Harmonise company spellings across the whole base.

    Company keys that are fuzzy-similar are grouped; each group takes its most
    frequent spelling, so 'Parfums d'Orsay Lue' (typo) becomes 'Parfums d'Orsay Lune'.
    """
    counts = df.groupby(["company_key", "company_name"]).size().reset_index(name="n")
    keys = counts.groupby("company_key")["n"].sum().sort_values(ascending=False).index.tolist()
    uf = UnionFind(keys)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if fuzz.ratio(a, b) >= threshold:
                uf.union(a, b)
    counts["group"] = counts["company_key"].map(uf.find)
    best = counts.sort_values("n", ascending=False).drop_duplicates("group").set_index("group")["company_name"]
    key_to_name = counts.set_index("company_key")["group"].map(best).to_dict()
    return df["company_key"].map(key_to_name).fillna(df["company_name"])


def match_reason(a: pd.Series, b: pd.Series) -> str | None:
    """Return why two records are the same contact, or None."""
    same_person = (a["contact_first_name"] or "").lower() == (b["contact_first_name"] or "").lower()
    if a["email"] and a["email"] == b["email"]:
        return "email identique"
    company_score = fuzz.token_sort_ratio(a["company_key"] or "", b["company_key"] or "")
    if same_person and a["phone"] and a["phone"] == b["phone"]:
        return "téléphone identique"
    if same_person and company_score >= COMPANY_THRESHOLD:
        return f"même contact + société proche ({company_score:.0f}%)"
    return None


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Return pairs of matching records with the matching reason."""
    pairs = []
    blocks = df.assign(_block=df["contact_last_name"].str.lower()).groupby("_block")
    for _, block in blocks:
        rows = list(block.iterrows())
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                reason = match_reason(rows[i][1], rows[j][1])
                if reason:
                    pairs.append({"record_a": rows[i][1]["record_id"], "record_b": rows[j][1]["record_id"],
                                  "reason": reason})
    return pd.DataFrame(pairs, columns=["record_a", "record_b", "reason"])


def assign_clusters(df: pd.DataFrame, pairs: pd.DataFrame) -> pd.Series:
    uf = UnionFind(df["record_id"])
    for a, b in zip(pairs["record_a"], pairs["record_b"]):
        uf.union(a, b)
    return df["record_id"].map(uf.find).rename("cluster_id")


def _completeness(row: pd.Series, cols) -> int:
    return sum(row[c] is not None and not pd.isna(row[c]) for c in cols)


def build_golden_records(df: pd.DataFrame, cluster_ids: pd.Series, valid_mask: pd.Series) -> pd.DataFrame:
    """One record per cluster. Survivorship rules:
    - the most complete, most recently contacted record is the base;
    - each empty field is filled from other records of the cluster (valid values first);
    - every subsidiary that knows the contact is kept in `subsidiaries`.
    """
    work = df.assign(cluster_id=cluster_ids.values, _valid=valid_mask.values,
                     company_name=canonical_company_names(df).values)
    fields = [c for c in df.columns if c not in ("record_id", "subsidiary", "country_raw", "phone_raw")]
    golden = []
    for cid, group in work.groupby("cluster_id", sort=True):
        group = group.assign(
            _complete=group.apply(lambda r: _completeness(r, fields), axis=1),
            _recency=pd.to_datetime(group["last_contact_date"], errors="coerce"),
        ).sort_values(["_valid", "_complete", "_recency"], ascending=False)
        base = group.iloc[0].copy()
        for col in fields:
            if base[col] is None or pd.isna(base[col]):
                candidates = group[col].dropna()
                if not candidates.empty:
                    base[col] = candidates.iloc[0]
        base["needs_review"] = not (isinstance(base["email"], str) and EMAIL_RE.match(base["email"])) \
            or base["phone"] is None or pd.isna(base["phone"])
        if isinstance(base["email"], str) and not EMAIL_RE.match(base["email"]):
            base["email"] = None  # never push an unusable e-mail to the CRM
        base["golden_id"] = f"G{len(golden) + 1:05d}"
        base["source_records"] = ", ".join(sorted(group["record_id"]))
        base["subsidiaries"] = ", ".join(sorted(group["subsidiary"].dropna().unique()))
        base["n_sources"] = len(group)
        golden.append(base)
    out = pd.DataFrame(golden).drop(columns=["_complete", "_recency", "_valid", "subsidiary", "record_id",
                                             "country_raw", "phone_raw", "cluster_id"])
    lead = ["golden_id", "company_name", "contact_first_name", "contact_last_name", "email", "phone",
            "country", "city", "segment", "account_type", "siret", "annual_revenue_eur", "last_contact_date",
            "subsidiaries", "n_sources", "source_records", "needs_review"]
    return out[lead].reset_index(drop=True)
