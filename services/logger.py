"""Deprecated logger shim.

This module was moved to the top-level `logs` package. Import from
`logs.logger` instead. This shim raises an ImportError to prevent
accidental imports of an old module.
"""

raise ImportError(
    "logger moved to top-level `logs` package. Use `from logs.logger import send_log, send_log_groupable`."
)
