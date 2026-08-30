"""V3 Local Dashboard.

The dashboard is a READ-ONLY consumer. ``loader`` reads the snapshot CSVs
produced by the four report scripts plus static config YAML, and ``app`` is the
Streamlit entry point. Neither imports any engine module nor triggers an
update / recomputation - every displayed value is an already-produced snapshot.
"""