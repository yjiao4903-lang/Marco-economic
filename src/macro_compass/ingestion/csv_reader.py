"""CSV table reader with encoding fallback (utf-8 / utf-8-sig / gbk)."""

from __future__ import annotations

import pandas as pd

MAX_HEADER_SCAN_ROWS = 10

_ENCODINGS = ("utf-8-sig", "utf-8", "gbk")


class ReadError(Exception):
    """Raised when a file cannot be parsed into a table."""


def read_csv_table(path, date_column: str) -> pd.DataFrame:
    """Read a CSV file as a DataFrame, locating the header row containing
    ``date_column`` (title rows above the header are tolerated)."""
    last_error: Exception | None = None
    for encoding in _ENCODINGS:
        try:
            raw = pd.read_csv(path, header=None, encoding=encoding, nrows=MAX_HEADER_SCAN_ROWS)
            full = pd.read_csv(path, header=None, encoding=encoding)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
            continue

        if full.empty:
            raise ReadError(f"CSV file '{path}' has no data rows")

        header_row = _find_header_row(raw, date_column)
        if header_row is None:
            raise ReadError(
                f"CSV file '{path}': date column '{date_column}' not found in the first "
                f"{min(MAX_HEADER_SCAN_ROWS, len(full))} rows. First row preview: "
                f"{[str(c) for c in full.iloc[0].tolist()[:8]]}"
            )

        df = pd.read_csv(path, header=header_row, encoding=encoding)
        return df.dropna(how="all").reset_index(drop=True)

    raise ReadError(f"Cannot read CSV file '{path}' with encodings {_ENCODINGS}: {last_error}")


def _find_header_row(raw: pd.DataFrame, date_column: str) -> int | None:
    for i in range(len(raw)):
        cells = {str(c).strip() for c in raw.iloc[i].tolist()}
        if date_column in cells:
            return i
    return None
