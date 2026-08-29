"""V0-02 config loader tests live in test_ingestion.py; this file covers
project-level sanity (V0-01)."""

from __future__ import annotations

from macro_compass import paths


def test_project_layout_exists():
    assert paths.PROJECT_ROOT.exists()
    assert (paths.PROJECT_ROOT / "pyproject.toml").exists()
    assert paths.CONFIG_DIR.exists()


def test_no_hardcoded_absolute_paths_in_source():
    # Spec rule: Windows paths must not be hardcoded. Scan source for drive letters.
    forbidden = ("C:\\", "D:\\")
    offenders = []
    for py in (paths.PROJECT_ROOT / "src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(str(py))
    assert not offenders, f"hardcoded drive paths found in: {offenders}"
