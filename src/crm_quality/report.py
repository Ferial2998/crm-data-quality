"""Charts (PNG) and a self-contained HTML quality report."""
from __future__ import annotations

import base64
import html
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def _style(ax, title: str):
    ax.set_title(title, loc="left", fontsize=12, color=INK, fontweight="bold", pad=12)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_score_by_subsidiary(summary: pd.DataFrame, path: Path):
    data = summary.sort_values("quality_score")
    fig, ax = plt.subplots(figsize=(7, 3.4), dpi=150)
    bars = ax.barh(data["subsidiary"], data["quality_score"], color=BLUE, height=0.55)
    for bar, v in zip(bars, data["quality_score"]):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2, f"{v:.0f}", va="center", color=INK, fontsize=9)
    ax.set_xlim(0, 105)
    _style(ax, "Score qualité moyen par filiale (/100)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chart_issues_by_rule(issues: pd.DataFrame, path: Path):
    counts = issues["rule"].value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=150)
    bars = ax.barh(counts.index, counts.values, color=BLUE, height=0.55)
    for bar, v in zip(bars, counts.values):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2, str(v), va="center", color=INK, fontsize=9)
    _style(ax, "Anomalies détectées par règle")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def chart_before_after(kpis: dict, path: Path):
    labels = list(kpis["pct"])
    before = [kpis["pct"][k][0] for k in labels]
    after = [kpis["pct"][k][1] for k in labels]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    w = 0.36
    b1 = ax.bar([i - w / 2 - 0.01 for i in x], before, w, color=BLUE, label="Avant (extrait brut)")
    b2 = ax.bar([i + w / 2 + 0.01 for i in x], after, w, color=ORANGE, label="Après (golden records)")
    for bars in (b1, b2):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"{bar.get_height():.0f} %",
                    ha="center", color=INK, fontsize=9)
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, 128)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    _style(ax, "Base CRM avant / après traitement (% des fiches)")
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper left", ncol=2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _img(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(path.stem)}">'


def _table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, border=0, classes="t", na_rep="")


def html_report(kpis: dict, summary: pd.DataFrame, issues: pd.DataFrame, pairs: pd.DataFrame,
                charts: list[Path], path: Path):
    top_rules = (issues.groupby(["rule", "severity", "description"]).size().rename("occurrences")
                 .reset_index().sort_values("occurrences", ascending=False))
    tiles = "".join(f'<div class="tile"><div class="v">{v}</div><div class="l">{html.escape(k)}</div></div>' for k, v in [
        ("fiches brutes", kpis["raw_records"]),
        ("golden records", kpis["golden_records"]),
        ("doublons fusionnés", kpis["duplicates_merged"]),
        ("anomalies détectées", kpis["issues"]),
        ("score qualité brut", f'{kpis["score_raw"]:.0f}/100'),
    ])
    doc = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport qualité CRM</title><style>
body{{font-family:system-ui,Arial,sans-serif;max-width:980px;margin:32px auto;padding:0 20px;color:#0b0b0b;background:#fcfcfb}}
h1{{margin-bottom:4px}} .sub{{color:#52514e;margin-top:0}} h2{{margin-top:36px;border-bottom:1px solid #e4e3df;padding-bottom:4px}}
.tiles{{display:flex;gap:12px;flex-wrap:wrap}} .tile{{flex:1;min-width:150px;border:1px solid #e4e3df;border-radius:8px;padding:12px;background:#fff}}
.v{{font-size:26px;font-weight:700}} .l{{color:#52514e;font-size:13px}}
img{{max-width:100%;margin:10px 0}} table.t{{border-collapse:collapse;width:100%;font-size:13px}}
.t th{{text-align:left;background:#f1f0ec;padding:6px}} .t td{{padding:6px;border-bottom:1px solid #eeede9}}
</style></head><body>
<h1>Rapport qualité de la base CRM Groupe</h1>
<p class="sub">Consolidation multi-filiales · {kpis["n_subsidiaries"]} filiales · données fictives</p>
<div class="tiles">{tiles}</div>
<h2>Synthèse</h2>{"".join(_img(c) for c in charts)}
<h2>Qualité par filiale</h2>{_table(summary)}
<h2>Anomalies par règle</h2>{_table(top_rules)}
<h2>Exemples de doublons détectés</h2>{_table(pairs.head(15))}
</body></html>"""
    path.write_text(doc, encoding="utf-8")
