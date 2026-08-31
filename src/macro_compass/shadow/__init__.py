"""Shadow Operation package (V4.6 handoff -> Shadow Operation infra).

Read-only observation monitors for the 3-6 month shadow phase (MASTER SPEC
section 15 / task 86): record the declared Asset Views each month-end and
count directional consistency against realized forward-return proxies.

Never imported by production Asset/Macro/Market code and never writes to
canonical - same isolation contract as the validation package.
"""

from macro_compass.shadow.metrics import (
    VIEW_HEADWIND,
    VIEW_NEUTRAL,
    VIEW_TAILWIND,
    asset_views,
    hit_summary,
    realized_frame,
    upsert_snapshot,
    view_of,
    DECISION_SNAPSHOT_COLUMNS,
    OUTCOME_OBSERVATION_COLUMNS,
    append_unique,
    content_hash,
    decision_snapshot_frame,
    git_hash,
    maturity_counts,
    outcome_observation_frame,
    runtime_metadata,
    validate_decision_snapshots,
    replay_gate,
)

__all__ = [
    "VIEW_HEADWIND",
    "VIEW_NEUTRAL",
    "VIEW_TAILWIND",
    "asset_views",
    "hit_summary",
    "realized_frame",
    "upsert_snapshot",
    "view_of",
    "DECISION_SNAPSHOT_COLUMNS",
    "OUTCOME_OBSERVATION_COLUMNS",
    "append_unique",
    "content_hash",
    "decision_snapshot_frame",
    "git_hash",
    "maturity_counts",
    "outcome_observation_frame",
    "runtime_metadata",
    "validate_decision_snapshots",
    "replay_gate",
]
