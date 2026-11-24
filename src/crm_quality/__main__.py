"""Command line: python -m crm_quality {generate,run}"""
from __future__ import annotations

import argparse
from pathlib import Path

from .generate import generate
from .pipeline import run


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crm_quality", description="Audit et fiabilisation d'une base CRM multi-filiales")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Générer un extrait CRM fictif avec anomalies")
    g.add_argument("--rows", type=int, default=400)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", type=Path, default=Path("data/raw/crm_extract.csv"))

    r = sub.add_parser("run", help="Lancer le pipeline qualité")
    r.add_argument("--input", type=Path, default=Path("data/raw/crm_extract.csv"))
    r.add_argument("--output", type=Path, default=Path("reports"))
    r.add_argument("--charts", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        generate(args.rows, args.seed).to_csv(args.out, index=False)
        print(f"Extrait CRM généré : {args.out}")
    else:
        kpis = run(args.input, args.output, charts_dir=args.charts)
        print(f"{kpis['raw_records']} fiches -> {kpis['golden_records']} golden records "
              f"({kpis['duplicates_merged']} doublons fusionnés, {kpis['issues']} anomalies)")
        print(f"Rapport : {args.output / 'quality_report.html'}")


if __name__ == "__main__":
    main()
