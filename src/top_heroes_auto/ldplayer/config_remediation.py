"""Retired config writer: LDPlayer instance names are user-owned/read-only.

The old adbDebug helper replaced the whole JSON file and could restore an old
name through rollback after a concurrent user edit. No automation caller may
rewrite/restore that file. Keep the entry point fail-closed for older callers.
"""
from pathlib import Path


class ConfigRemediationError(ValueError):
    """Persistent LDPlayer config remediation is unavailable."""


def enable_authorized_adb_debug(
    index: int,
    name: str,
    config_path: Path,
    backup_path: Path,
    *,
    live_name: str,
    protected: bool,
):
    """Never write config or a backup, including on identity/protection errors."""
    raise ConfigRemediationError(
        "Automatic LDPlayer config replacement is disabled: instance names are user-owned and read-only."
    )
