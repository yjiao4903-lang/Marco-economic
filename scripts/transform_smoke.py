"""V1.5A smoke command: run a declared transform chain on a real series.

Reads one series from canonical parquet, applies the transform chain declared
for a signal in config/signals.yaml, and prints a preview of raw vs level
basis vs momentum basis. Read-only: canonical is never modified.

Usage:
    python scripts/transform_smoke.py                 # G1 on CHN_CLI
    python scripts/transform_smoke.py --signal I1     # I1 on its available input
    python scripts/transform_smoke.py --series CN_PMI --signal G2
    python scripts/transform_smoke.py --series USD_CNY --rows 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.signals import load_signal_registry  # noqa: E402
from macro_compass.storage import canonical_store  # noqa: E402
from macro_compass.transforms import apply_chain  # noqa: E402


def _load_series(series_id: str) -> pd.Series:
    frames = [
        canonical_store.read_canonical(category)
        for category in ("macro", "market")
    ]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    rows = combined[combined["series_id"] == series_id] if not combined.empty else combined
    if rows.empty:
        available = sorted(combined["series_id"].unique()) if not combined.empty else []
        raise SystemExit(
            f"series '{series_id}' has no canonical data. Available: {available}"
        )
    values = (
        rows.assign(date=pd.to_datetime(rows["date"]))
        .drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .set_index("date")["value"]
        .astype(float)
        .rename(series_id)
    )
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", default=None, help="series_id to transform")
    parser.add_argument("--signal", default="G1", help="signal_id whose declared chain to run")
    parser.add_argument("--rows", type=int, default=8, help="preview rows from the end")
    args = parser.parse_args()

    indicators = load_indicator_config(paths.INDICATORS_YAML)
    registry = load_signal_registry(paths.SIGNALS_YAML, indicators_registry=indicators)
    spec = registry.signals.get(args.signal)
    if spec is None:
        raise SystemExit(f"signal '{args.signal}' not in signals.yaml: {sorted(registry.signals)}")
    if not spec.transforms and spec.momentum_transform is None:
        raise SystemExit(
            f"signal '{args.signal}' ({spec.name}) declares no transform chain "
            "(market/structural placeholders have none)"
        )

    series_id = args.series
    if series_id is None:
        available = [
            i.series_id
            for i in spec.inputs
            if _canonical_has(i.series_id)
        ]
        if not available:
            raise SystemExit(
                f"signal '{args.signal}' has no input with canonical data "
                f"({spec.inputs}); pass --series explicitly"
            )
        series_id = available[0]

    values = _load_series(series_id)
    level_basis = apply_chain(values, [step.model_dump() for step in spec.transforms])
    momentum_basis = (
        apply_chain(values, [spec.momentum_transform.model_dump()])
        if spec.momentum_transform is not None
        else pd.Series(dtype=float)
    )

    preview = pd.concat(
        {"raw": values, "level_basis": level_basis, "momentum_basis": momentum_basis},
        axis=1,
    ).tail(args.rows)

    print(f"signal: {spec.signal_id} ({spec.name}), layer={spec.layer}, factor={spec.factor}")
    print(f"series: {series_id}, {len(values)} observations "
          f"({values.index.min().date()} .. {values.index.max().date()})")
    if spec.transforms:
        print(f"level chain: {[s.model_dump(exclude_none=True) for s in spec.transforms]}")
    if spec.momentum_transform is not None:
        print(f"momentum:    {spec.momentum_transform.model_dump(exclude_none=True)}")
    print()
    print(preview.to_string(float_format=lambda v: f"{v:.4f}"))
    print("\nRead-only smoke run - canonical data was not modified.")


def _canonical_has(series_id: str) -> bool:
    for category in ("macro", "market"):
        frame = canonical_store.read_canonical(category)
        if not frame.empty and series_id in set(frame["series_id"]):
            return True
    return False


if __name__ == "__main__":
    main()
