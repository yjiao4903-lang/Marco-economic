"""V4.7 P0 consolidation regression tests.

Covers two invariants introduced after the repository audit:
1. every S3 proxy is normalized onto an explicit 0=lower / 1=higher fragility
   scale; ambiguous positive/negative per-proxy labels are rejected;
2. a Wind import that fails after canonical Parquet is written is resumable and
   must not append canonical data a second time.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from macro_compass import pipeline
from macro_compass.storage import raw_archive
from macro_compass.structural.config import StructuralConfigError, load_structural_config
from macro_compass.structural.engine import _align_s3_percentile_to_fragility


# ---------------------------------------------------------------------------
# S3 explicit fragility semantics
# ---------------------------------------------------------------------------


def test_s3_fragility_alignment_has_unambiguous_scale() -> None:
    pct = pd.Series([0.1, 0.5, 0.9])

    higher_fragile = _align_s3_percentile_to_fragility(pct, "higher_is_more_fragile")
    lower_fragile = _align_s3_percentile_to_fragility(pct, "lower_is_more_fragile")

    pd.testing.assert_series_equal(higher_fragile, pct)
    pd.testing.assert_series_equal(lower_fragile, 1.0 - pct)

    with pytest.raises(ValueError, match="higher_is_more_fragile"):
        _align_s3_percentile_to_fragility(pct, "positive")


def test_structural_config_rejects_ambiguous_s3_input_direction(tmp_path) -> None:
    cfg = tmp_path / "structural.yaml"
    cfg.write_text(
        """
signals:
  S3:
    direction: negative
    percentile_window: 20
    trend_quarters: 4
    thresholds:
      elevated_percentile: 0.8
      moderate_percentile: 0.5
    required_inputs: [PRICE]
    input_directions:
      PRICE: positive
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(StructuralConfigError, match="ambiguous positive/negative"):
        load_structural_config(cfg)


# ---------------------------------------------------------------------------
# Wind import recovery journal
# ---------------------------------------------------------------------------


def test_manifest_state_ignores_skip_but_not_post_canonical_failure(monkeypatch) -> None:
    file_hash = "abc123"

    manifest = pd.DataFrame(
        [
            {
                "file_name": "x.csv",
                "sha256": file_hash,
                "import_time": pd.Timestamp("2026-09-01 10:00:00"),
                "rows": 1,
                "status": raw_archive.STATUS_IMPORTED,
                "archive_path": "a.csv",
            },
            {
                "file_name": "x.csv",
                "sha256": file_hash,
                "import_time": pd.Timestamp("2026-09-01 10:01:00"),
                "rows": 0,
                "status": raw_archive.STATUS_SKIPPED,
                "archive_path": "",
            },
        ]
    )
    monkeypatch.setattr(raw_archive, "load_manifest", lambda: manifest)
    assert raw_archive.is_hash_imported(file_hash) is True

    failed = pd.concat(
        [
            manifest,
            pd.DataFrame(
                [
                    {
                        "file_name": "x.csv",
                        "sha256": file_hash,
                        "import_time": pd.Timestamp("2026-09-01 10:02:00"),
                        "rows": 1,
                        "status": raw_archive.STATUS_FAILED_POST_CANONICAL,
                        "archive_path": "a.csv",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    monkeypatch.setattr(raw_archive, "load_manifest", lambda: failed)
    assert raw_archive.is_hash_imported(file_hash) is False
    assert raw_archive.latest_hash_state(file_hash)["status"] == raw_archive.STATUS_FAILED_POST_CANONICAL


def test_wind_import_resumes_after_post_canonical_failure_without_reappend(
    monkeypatch, tmp_path
) -> None:
    source_file = tmp_path / "wind.csv"
    source_file.write_text("dummy", encoding="utf-8")
    file_hash = "recoverable-hash"
    canonical = pd.DataFrame(
        {
            "series_id": ["CN_PMI"],
            "date": [pd.Timestamp("2026-08-31").date()],
            "value": [49.9],
        }
    )

    events: list[dict] = []
    calls = {"append": 0, "archive": 0}
    fail_refresh = {"value": True}

    monkeypatch.setattr(raw_archive, "sha256_of_file", lambda path: file_hash)

    def latest_state(_file_hash):
        meaningful = [e for e in events if e["status"] != raw_archive.STATUS_SKIPPED]
        return pd.Series(meaningful[-1]) if meaningful else None

    def is_imported(_file_hash):
        state = latest_state(_file_hash)
        return state is not None and state["status"] == raw_archive.STATUS_IMPORTED

    def record_manifest(*, file_name, file_hash, import_time, rows, status, archive_path):
        events.append(
            {
                "file_name": file_name,
                "sha256": file_hash,
                "import_time": pd.Timestamp(import_time),
                "rows": rows,
                "status": status,
                "archive_path": archive_path or "",
            }
        )

    monkeypatch.setattr(raw_archive, "latest_hash_state", latest_state)
    monkeypatch.setattr(raw_archive, "is_hash_imported", is_imported)
    monkeypatch.setattr(raw_archive, "record_manifest", record_manifest)

    def archive_file(path, import_time):
        calls["archive"] += 1
        return tmp_path / "archive" / path.name

    monkeypatch.setattr(raw_archive, "archive_file", archive_file)
    monkeypatch.setattr(
        pipeline,
        "parse_wind_file",
        lambda path, mapping, source, file_hash=None: (canonical.copy(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        pipeline,
        "validate_canonical",
        lambda frame, registry: SimpleNamespace(passed=True, errors=[], warnings=[]),
    )

    def append_canonical(frame):
        calls["append"] += 1
        return len(frame)

    monkeypatch.setattr(pipeline, "append_canonical", append_canonical)

    class FakeDuckDBStore:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def refresh_series_data(self, frame):
            pass

        def refresh_series_metadata(self, registry):
            if fail_refresh["value"]:
                raise RuntimeError("simulated DuckDB refresh failure")

        def refresh_import_manifest(self):
            pass

    monkeypatch.setattr(pipeline, "DuckDBStore", FakeDuckDBStore)

    first = pipeline.import_wind_file(source_file, mapping=object(), registry={})
    assert first.status == pipeline.STATUS_FAILED_POST_CANONICAL
    assert first.ok is False
    assert calls == {"append": 1, "archive": 1}
    assert [e["status"] for e in events] == [
        raw_archive.STATUS_CANONICAL_WRITTEN,
        raw_archive.STATUS_FAILED_POST_CANONICAL,
    ]
    assert is_imported(file_hash) is False

    fail_refresh["value"] = False
    second = pipeline.import_wind_file(source_file, mapping=object(), registry={})

    assert second.status == pipeline.STATUS_IMPORTED
    assert second.ok is True
    assert "Recovered prior partial import" in second.message
    # Recovery must not archive or merge the same source into canonical again.
    assert calls == {"append": 1, "archive": 1}
    assert events[-1]["status"] == raw_archive.STATUS_IMPORTED
    assert is_imported(file_hash) is True


def test_failure_after_imported_event_is_still_resumable(monkeypatch, tmp_path) -> None:
    """If the DuckDB manifest mirror fails after an IMPORTED event was appended,
    FAILED_POST_CANONICAL must become the latest meaningful state so the next
    run does not incorrectly deduplicate the file as complete."""
    source_file = tmp_path / "wind.csv"
    source_file.write_text("dummy", encoding="utf-8")
    file_hash = "mirror-failure-hash"
    canonical = pd.DataFrame(
        {
            "series_id": ["CN_PMI"],
            "date": [pd.Timestamp("2026-08-31").date()],
            "value": [49.9],
        }
    )
    events: list[dict] = []
    calls = {"append": 0}
    fail_mirror = {"value": True}

    monkeypatch.setattr(raw_archive, "sha256_of_file", lambda path: file_hash)

    def latest_state(_file_hash):
        meaningful = [e for e in events if e["status"] != raw_archive.STATUS_SKIPPED]
        return pd.Series(meaningful[-1]) if meaningful else None

    monkeypatch.setattr(raw_archive, "latest_hash_state", latest_state)
    monkeypatch.setattr(
        raw_archive,
        "is_hash_imported",
        lambda _file_hash: (
            latest_state(_file_hash) is not None
            and latest_state(_file_hash)["status"] == raw_archive.STATUS_IMPORTED
        ),
    )

    def record_manifest(*, file_name, file_hash, import_time, rows, status, archive_path):
        events.append(
            {
                "file_name": file_name,
                "sha256": file_hash,
                "import_time": pd.Timestamp(import_time),
                "rows": rows,
                "status": status,
                "archive_path": archive_path or "",
            }
        )

    monkeypatch.setattr(raw_archive, "record_manifest", record_manifest)
    monkeypatch.setattr(raw_archive, "archive_file", lambda path, import_time: tmp_path / "a.csv")
    monkeypatch.setattr(
        pipeline,
        "parse_wind_file",
        lambda path, mapping, source, file_hash=None: (canonical.copy(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        pipeline,
        "validate_canonical",
        lambda frame, registry: SimpleNamespace(passed=True, errors=[], warnings=[]),
    )

    def append_canonical(frame):
        calls["append"] += 1
        return len(frame)

    monkeypatch.setattr(pipeline, "append_canonical", append_canonical)

    class FakeDuckDBStore:
        def __init__(self, db_path=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def refresh_series_data(self, frame):
            pass

        def refresh_series_metadata(self, registry):
            pass

        def refresh_import_manifest(self):
            if fail_mirror["value"]:
                raise RuntimeError("simulated manifest mirror failure")

    monkeypatch.setattr(pipeline, "DuckDBStore", FakeDuckDBStore)

    first = pipeline.import_wind_file(source_file, mapping=object(), registry={})
    assert first.status == pipeline.STATUS_FAILED_POST_CANONICAL
    assert [e["status"] for e in events][-3:] == [
        raw_archive.STATUS_CANONICAL_WRITTEN,
        raw_archive.STATUS_IMPORTED,
        raw_archive.STATUS_FAILED_POST_CANONICAL,
    ]
    assert raw_archive.is_hash_imported(file_hash) is False

    fail_mirror["value"] = False
    second = pipeline.import_wind_file(source_file, mapping=object(), registry={})
    assert second.status == pipeline.STATUS_IMPORTED
    assert calls["append"] == 1
