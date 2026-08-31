"""Read-only preflight audit for an offline USD_BROAD history file.

This command deliberately stops before ``import_wind.py``/canonical storage.
It accepts a FRED-style file (DATE + DTWEXBGS) or a Wind export whose date and
value columns have a recognizable name, and emits an auditable JSON report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from macro_compass.ingestion.csv_reader import read_csv_table
from macro_compass.ingestion.excel_reader import read_excel_table

SERIES_ID = "USD_BROAD"
DATE_ALIASES = {"date", "日期", "observation date", "time period"}
VALUE_ALIASES = {
    "dtwexbgs", "broad", "usd_broad", "usd broad", "美元广义指数", "美元广义指数(宽)",
    "value", "值", "obs_value", "observation value",
}


def _key(value: object) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def _read(path: Path) -> pd.DataFrame:
    # Discover the header from a bounded preview, then reuse the project's
    # readers so BOM/GBK and title rows follow the established conventions.
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        last_error = None
        preview = None
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                preview = pd.read_csv(path, header=None, nrows=10, encoding=encoding, sep="\t" if suffix == ".tsv" else ",")
                break
            except (UnicodeDecodeError, pd.errors.ParserError) as exc:
                last_error = exc
        if preview is None:
            raise ValueError(f"cannot read delimited file: {last_error}")
        candidates = [str(c).strip() for c in preview.iloc[0].tolist()] if len(preview) else []
        date_col = next((c for c in candidates if _key(c) in DATE_ALIASES), None)
        if date_col is None:
            for row in preview.itertuples(index=False):
                date_col = next((str(c).strip() for c in row if _key(c) in DATE_ALIASES), None)
                if date_col:
                    break
        if date_col is None:
            raise ValueError("no recognizable date column (expected Date/DATE/日期/observation_date)")
        return read_csv_table(path, date_col)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        raw = pd.read_excel(path, sheet_name=0, header=None, nrows=10, engine="openpyxl")
        date_col = None
        for row in raw.itertuples(index=False):
            date_col = next((str(c).strip() for c in row if _key(c) in DATE_ALIASES), None)
            if date_col:
                break
        if date_col is None:
            raise ValueError("no recognizable date column (expected Date/DATE/日期/observation_date)")
        return read_excel_table(path, date_col)
    raise ValueError(f"unsupported file type '{path.suffix}'")


def _choose_column(columns, requested: str | None, aliases: set[str], kind: str) -> str:
    if requested:
        if requested not in columns:
            raise ValueError(f"{kind} column '{requested}' not found; columns={list(columns)}")
        return requested
    matches = [str(c) for c in columns if _key(c) in aliases]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one recognizable {kind} column; matches={matches}, columns={list(columns)}")
    return matches[0]


def audit_usd_broad_file(
    path: Path,
    *,
    date_column: str | None = None,
    value_column: str | None = None,
    series_id: str = SERIES_ID,
    unit: str = "index",
    base_definition: str = "Jan-2006=100",
) -> dict:
    """Audit one file in memory; never writes canonical or production data."""
    if series_id != SERIES_ID:
        raise ValueError(f"series_id must be {SERIES_ID}")
    frame = _read(Path(path))
    date_col = _choose_column(frame.columns, date_column, DATE_ALIASES, "date")
    value_col = _choose_column(frame.columns, value_column, VALUE_ALIASES, "value")
    dates = pd.to_datetime(frame[date_col], errors="coerce")
    values = pd.to_numeric(frame[value_col].replace({".": None, "": None}), errors="coerce")
    usable = pd.DataFrame({"date": dates, "value": values}).dropna()
    usable = usable.sort_values("date")
    duplicate_dates = int(usable["date"].duplicated().sum())
    gaps = usable["date"].diff().dt.days.dropna()
    max_gap = int(gaps.max()) if len(gaps) else 0
    missing_weekdays = int(sum(
        1 for d in pd.date_range(usable["date"].min(), usable["date"].max(), freq="D")
        if d.weekday() < 5 and d not in set(usable["date"])
    )) if len(usable) else 0
    min_date = usable["date"].min() if len(usable) else None
    max_date = usable["date"].max() if len(usable) else None
    span_months = ((max_date.year - min_date.year) * 12 + max_date.month - min_date.month + 1) if min_date is not None else 0
    definition_ok = unit.strip().lower() == "index" and base_definition.replace(" ", "").lower() in {"jan-2006=100", "2006-01=100", "jan2006=100"}
    structural_pass = bool(len(usable) and not duplicate_dates and max_gap <= 7 and definition_ok)
    ready_250 = len(usable) >= 250
    history_120 = bool(span_months >= 120 and min_date is not None and min_date <= pd.Timestamp("2006-01-31"))
    report = {
        "status": "PASS" if structural_pass else "FAIL",
        "readiness_status": "READY" if structural_pass and ready_250 and history_120 else ("WARMUP" if structural_pass else "BLOCKED"),
        "scope": "candidate_preflight_only",
        "writes_canonical": False,
        "series_id": series_id,
        "date_column": date_col,
        "value_column": value_col,
        "unit": unit,
        "base_definition": base_definition,
        "definition_check": "PASS" if definition_ok else "FAIL",
        "rows_usable": int(len(usable)),
        "invalid_date_or_value_rows": int(len(frame) - len(usable)),
        "duplicate_dates": duplicate_dates,
        "date_start": min_date.date().isoformat() if min_date is not None else None,
        "date_end": max_date.date().isoformat() if max_date is not None else None,
        "max_gap_days": max_gap,
        "missing_weekdays": missing_weekdays,
        "continuity_check": "PASS" if len(usable) and not duplicate_dates and max_gap <= 7 else "FAIL",
        "ready_250_observations": ready_250,
        "history_120_months": history_120,
        "span_months": span_months,
        "next_step": "review report, then use the explicit approved import path; this command did not import anything",
    }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path)
    ap.add_argument("--date-column")
    ap.add_argument("--value-column")
    ap.add_argument("--unit", default="index")
    ap.add_argument("--base-definition", default="Jan-2006=100")
    ap.add_argument("--output", type=Path, help="optional JSON report path (candidate artifact only)")
    args = ap.parse_args(argv)
    try:
        report = audit_usd_broad_file(args.file, date_column=args.date_column, value_column=args.value_column, unit=args.unit, base_definition=args.base_definition)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc), "writes_canonical": False}, ensure_ascii=False, indent=2))
        return 1
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
