"""Build an audit-only monthly gold candidate and comparison report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths
from macro_compass.data_sources.gold_monthly import audit_gold_monthly, derive_gold_monthly


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=paths.PROJECT_ROOT / "outputs")
    args = parser.parse_args()
    daily = pd.read_parquet(paths.MARKET_PARQUET)
    production = daily  # production GOLD is in the same market canonical file
    candidate = derive_gold_monthly(daily)
    audit = audit_gold_monthly(daily, production)
    production_units = sorted(production.loc[production["series_id"].eq("GOLD"), "unit"].dropna().unique().tolist())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    parquet = args.output_dir / "gold_monthly_candidate.parquet"
    report = args.output_dir / "gold_monthly_candidate_audit.md"
    candidate.to_parquet(parquet, index=False)
    lines = [
        "# GOLD monthly derived candidate audit",
        "",
        "Status: **DISABLED / audit-only**; no canonical, Asset, Signal, algorithm, or weight changes.",
        "",
        f"- source: `{audit.source_rows}` rows of `{candidate['source_series_id'].iloc[0] if len(candidate) else 'GOLD_LONDON_SPOT_USD_OZ_DAILY'}`",
        f"- candidate: `{audit.candidate_rows}` rows; `{audit.candidate_start}` to `{audit.candidate_end}`",
        f"- rule: `{candidate['aggregation_rule'].iloc[0] if len(candidate) else 'last available daily observation per calendar month'}`",
        f"- missing calendar months: `{', '.join(audit.missing_months) if audit.missing_months else 'none'}`",
        f"- production GOLD overlap: `{audit.overlap_rows}` rows; mean/max absolute difference `{audit.overlap_mean_abs_diff}` / `{audit.overlap_max_abs_diff}` USD/troy oz",
        f"- units: candidate `usd_per_troy_oz`; production GOLD declared unit(s) `{', '.join(production_units) or 'none'}`. Monthly date is calendar month-end while `source_date` is the selected trading date.",
        "",
        "Promotion: **not recommended automatically**. A future promotion would require explicit unit/definition review and consumer-specific acceptance.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"candidate={parquet} rows={len(candidate)}")
    print(audit.to_dict())


if __name__ == "__main__":
    main()
