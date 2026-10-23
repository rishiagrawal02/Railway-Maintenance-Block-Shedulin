"""Public API facade for the Railway Maintenance Block Planning system.

This is the only module that the UI (app/streamlit_app.py) may import from rbp.
"""


def get_version() -> str:
    """Return the package version string."""
    return "0.1.0"
