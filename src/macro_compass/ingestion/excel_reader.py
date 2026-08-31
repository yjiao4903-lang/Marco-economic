"""Excel table reader.

Handles Wind-style exports that may contain title rows above the header:
the header row is located by scanning for the configured date column.
"""

from __future__ import annotations

import pandas as pd

MAX_HEADER_SCAN_ROWS = 10


class ReadError(Exception):
    """Raised when a file cannot be parsed into a table."""


def read_excel_table(path, date_column: str) -> pd.DataFrame:
    """Read the first sheet of an Excel file as a DataFrame.

    Raises ``ReadError`` with a readable message when the file is unreadable
    or the expected ``date_column`` header cannot be found.
    """
    try:
        raw = pd.read_excel(path, sheet_name=0, header=None, engine="openpyxl")
    except Exception as exc:
        raise ReadError(f"Cannot read Excel file '{path}': {exc}") from exc

    if raw.empty:
        raise ReadError(f"Excel file '{path}' has no data rows")

    header_row = _find_header_row(raw, date_column)
    # Wind's localized metadata export labels the date column as
    # ``指标名称`` in the first row; observation dates begin below the
    # metadata rows.  Keep the configured canonical name (usually ``Date``)
    # while accepting this well-defined Wind layout.
    wind_metadata_date = False
    if header_row is None:
        header_row = _find_header_row(raw, "指标名称")
        wind_metadata_date = header_row is not None
    if header_row is None:
        raise ReadError(
            f"Excel file '{path}': date column '{date_column}' not found in the first "
            f"{min(MAX_HEADER_SCAN_ROWS, len(raw))} rows. Found header candidates: "
            f"{_first_row_preview(raw)}"
        )

    df = pd.read_excel(path, sheet_name=0, header=header_row, engine="openpyxl")
    if wind_metadata_date and date_column not in df.columns and "指标名称" in df.columns:
        df = df.rename(columns={"指标名称": date_column})
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def _find_header_row(raw: pd.DataFrame, date_column: str) -> int | None:
    limit = min(MAX_HEADER_SCAN_ROWS, len(raw))
    for i in range(limit):
        cells = {str(c).strip() for c in raw.iloc[i].tolist()}
        if date_column in cells:
            return i
    return None


def _first_row_preview(raw: pd.DataFrame) -> list[str]:
    return [str(c) for c in raw.iloc[0].tolist()[:8]]
