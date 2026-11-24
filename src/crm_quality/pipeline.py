"""End-to-end pipeline: raw CSV -> standardized data, issue log, duplicates, golden records, report."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import dedupe, report, rules, scoring
from .standardize import standardize


def run(input_csv: Path, output_dir: Path, today: date = date(2026, 11, 24), charts_dir: Path | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = charts_dir or output_dir
    charts_dir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    raw = raw.replace({"": None})
    df = standardize(raw)

    issues = rules.run_rules(df, today)
    pairs = dedupe.find_duplicates(df)
    clusters = dedupe.assign_clusters(df, pairs)

    blocking = set(issues.loc[issues["severity"] == "bloquant", "record_id"])
    valid_mask = ~df["record_id"].isin(blocking)
    golden = dedupe.build_golden_records(df, clusters, valid_mask)

    scores = scoring.record_scores(df, issues, clusters)
    summary = scoring.subsidiary_summary(scores, issues)

    golden_email_ok = golden["email"].fillna("").str.match(rules.EMAIL_RE)
    kpis = {
        "raw_records": len(raw),
        "golden_records": len(golden),
        "duplicates_merged": len(raw) - len(golden),
        "issues": len(issues),
        "score_raw": scores["quality_score"].mean(),
        "n_subsidiaries": df["subsidiary"].nunique(),
        "valid_emails_raw": int(raw["email"].fillna("").str.strip().str.match(rules.EMAIL_RE).sum()),
        "valid_emails_golden": int(golden_email_ok.sum()),
        "e164_phones_raw": int(raw["phone"].fillna("").str.match(r"^\+\d{10,15}$").sum()),
        "e164_phones_golden": int(golden["phone"].notna().sum()),
        "unique_raw": int((clusters.map(clusters.value_counts()) == 1).sum()),
    }
    n_raw, n_gold = kpis["raw_records"], kpis["golden_records"]
    kpis["pct"] = {
        "Fiches uniques": (100 * kpis["unique_raw"] / n_raw, 100.0),
        "Emails exploitables": (100 * kpis["valid_emails_raw"] / n_raw, 100 * kpis["valid_emails_golden"] / n_gold),
        "Téléphones au format\ninternational": (100 * kpis["e164_phones_raw"] / n_raw,
                                               100 * kpis["e164_phones_golden"] / n_gold),
    }

    df.drop(columns=["company_key"]).assign(cluster_id=clusters.values).to_csv(
        output_dir / "crm_standardized.csv", index=False)
    issues.to_csv(output_dir / "issues_log.csv", index=False)
    pairs.to_csv(output_dir / "duplicate_pairs.csv", index=False)
    golden.to_csv(output_dir / "golden_records.csv", index=False)
    scores.to_csv(output_dir / "record_scores.csv", index=False)
    summary.to_csv(output_dir / "subsidiary_summary.csv", index=False)

    charts = [charts_dir / "before_after.png", charts_dir / "score_by_subsidiary.png", charts_dir / "issues_by_rule.png"]
    report.chart_before_after(kpis, charts[0])
    report.chart_score_by_subsidiary(summary, charts[1])
    report.chart_issues_by_rule(issues, charts[2])
    report.html_report(kpis, summary, issues, pairs, charts, output_dir / "quality_report.html")
    return kpis
