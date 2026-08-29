"""Ingestion: Wind Excel/CSV -> canonical long format."""

from macro_compass.ingestion.excel_reader import read_excel_table
from macro_compass.ingestion.csv_reader import read_csv_table
from macro_compass.ingestion.normalizer import normalize_to_canonical
from macro_compass.ingestion.validator import validate_canonical

__all__ = [
    "read_excel_table",
    "read_csv_table",
    "normalize_to_canonical",
    "validate_canonical",
]
