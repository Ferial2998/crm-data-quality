"""Quality score (0-100) per record and per subsidiary.

score = 40% completeness + 40% validity + 20% uniqueness
"""
from __future__ import annotations

import pandas as pd

from .rules import REQUIRED

WEIGHTS = {"completeness": 0.4, "validity": 0.4, "uniqueness": 0.2}
SEVERITY_PENALTY = {"bloquant": 1.0, "majeur": 0.5, "mineur": 0.2}


def record_scores(df: pd.DataFrame, issues: pd.DataFrame, cluster_ids: pd.Series) -> pd.DataFrame:
    completeness = df[REQUIRED].notna().mean(axis=1)
    validity_issues = issues[~issues["rule"].str.startswith("MISSING_")]
    penalty = (validity_issues.assign(p=validity_issues["severity"].map(SEVERITY_PENALTY))
               .groupby("record_id")["p"].sum())
    validity = (1 - df["record_id"].map(penalty).fillna(0)).clip(lower=0)
    cluster_size = cluster_ids.map(cluster_ids.value_counts())
    uniqueness = (cluster_size == 1).astype(float)
    score = 100 * (WEIGHTS["completeness"] * completeness + WEIGHTS["validity"] * validity
                   + WEIGHTS["uniqueness"] * uniqueness)
    return pd.DataFrame({
        "record_id": df["record_id"], "subsidiary": df["subsidiary"],
        "completeness": completeness.round(3), "validity": validity.round(3),
        "is_duplicate": cluster_size.values > 1, "quality_score": score.round(1),
    })


def subsidiary_summary(scores: pd.DataFrame, issues: pd.DataFrame) -> pd.DataFrame:
    summary = scores.groupby("subsidiary").agg(
        records=("record_id", "count"),
        quality_score=("quality_score", "mean"),
        completeness=("completeness", "mean"),
        duplicate_rate=("is_duplicate", "mean"),
    )
    summary["issues"] = issues.groupby("subsidiary").size().reindex(summary.index).fillna(0).astype(int)
    summary["blocking_issues"] = (issues[issues["severity"] == "bloquant"].groupby("subsidiary").size()
                                  .reindex(summary.index).fillna(0).astype(int))
    return summary.round(3).sort_values("quality_score").reset_index()
