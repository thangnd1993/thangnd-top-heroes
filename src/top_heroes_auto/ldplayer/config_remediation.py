"""Narrow, backup-first repair for explicitly authorized LDPlayer ADB settings."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

AUTHORIZED_ADB_DEBUG_TARGETS = {
    3: "Queen con",
    8: "Soup",
    9: "Pooh5",
    10: "Nấm hương",
    11: "Nấm đùi gà",
}


class ConfigRemediationError(ValueError):
    """The requested instance/config does not match the narrow authorization."""


@dataclass(frozen=True)
class ConfigRemediationResult:
    index: int
    name: str
    config_path: Path
    backup_path: Path
    previous_value: int
    current_value: int


def enable_authorized_adb_debug(
    index: int,
    name: str,
    config_path: Path,
    backup_path: Path,
    *,
    live_name: str,
    protected: bool,
) -> ConfigRemediationResult:
    """Change only adbDebug for an exact authorized, live, non-Protected target.

    A unique byte-for-byte backup is created before the atomic config replacement.
    The authorization is intentionally limited to the five Phase 6 instance IDs.
    """
    expected_name = AUTHORIZED_ADB_DEBUG_TARGETS.get(index)
    if expected_name is None or name != expected_name or live_name != expected_name:
        raise ConfigRemediationError("Instance is outside the exact authorized index/name allowlist.")
    if protected:
        raise ConfigRemediationError("Protected instances cannot be changed.")
    config_path = Path(config_path)
    backup_path = Path(backup_path)
    if config_path.name.casefold() != f"leidian{index}.config".casefold():
        raise ConfigRemediationError("Config filename does not match the authorized instance index.")
    if config_path.parent.resolve() != backup_path.parent.resolve():
        raise ConfigRemediationError("Backup must be stored beside the exact instance config.")
    if backup_path.exists():
        raise ConfigRemediationError("Refusing to overwrite an existing config backup.")

    original = config_path.read_bytes()
    has_bom = original.startswith(b"\xef\xbb\xbf")
    text = original.decode("utf-8-sig")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigRemediationError("Instance config is not valid JSON.") from exc
    if parsed.get("statusSettings.playerName") != expected_name:
        raise ConfigRemediationError("Config player name does not match the exact authorized target.")
    if parsed.get("basicSettings.adbDebug") != 0:
        raise ConfigRemediationError("Expected adbDebug=0; refusing an unexpected or already changed value.")

    field_line = re.compile(r'(?m)^(\s*"basicSettings\.adbDebug"\s*:\s*)0(\s*,?\s*)$')
    updated, count = field_line.subn(r'\g<1>1\g<2>', text)
    if count != 1:
        raise ConfigRemediationError("Expected exactly one basicSettings.adbDebug field.")

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, backup_path)
    if backup_path.read_bytes() != original:
        raise ConfigRemediationError("Config backup did not preserve the original bytes.")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=config_path.parent,
            prefix=f"{config_path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            encoded = updated.encode("utf-8")
            temporary.write((b"\xef\xbb\xbf" if has_bom else b"") + encoded)
            temp_path = Path(temporary.name)
        os.replace(temp_path, config_path)
        temp_path = None

        try:
            verified = json.loads(config_path.read_text(encoding="utf-8-sig"))
            before_other_fields = dict(parsed)
            after_other_fields = dict(verified)
            before_other_fields.pop("basicSettings.adbDebug", None)
            after_other_fields.pop("basicSettings.adbDebug", None)
            if (
                verified.get("basicSettings.adbDebug") != 1
                or before_other_fields != after_other_fields
            ):
                raise ConfigRemediationError("Post-write verification found an unintended config change.")
        except Exception:
            shutil.copy2(backup_path, config_path)
            raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return ConfigRemediationResult(
        index, expected_name, config_path, backup_path, 0, 1
    )
