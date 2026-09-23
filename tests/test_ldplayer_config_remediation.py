from __future__ import annotations

import json

import pytest

from top_heroes_auto.ldplayer import config_remediation
from top_heroes_auto.ldplayer.config_remediation import (
    ConfigRemediationError,
    enable_authorized_adb_debug,
)


def config_bytes(name="Queen con", adb_debug=0):
    return (
        "{\n"
        '  "statusSettings.playerName": "' + name + '",\n'
        '  "basicSettings.adbDebug": ' + str(adb_debug) + ",\n"
        '  "basicSettings.ram": 4096,\n'
        '  "networkSettings.networkEnable": true\n'
        "}\n"
    ).encode("utf-8")


def remediate(path, backup, *, protected=False, live_name="Queen con"):
    return enable_authorized_adb_debug(
        3,
        "Queen con",
        path,
        backup,
        live_name=live_name,
        protected=protected,
    )


def test_protected_account_config_cannot_be_changed(tmp_path):
    config = tmp_path / "leidian3.config"
    backup = tmp_path / "leidian3.config.backup"
    original = config_bytes()
    config.write_bytes(original)

    with pytest.raises(ConfigRemediationError, match="Protected"):
        remediate(config, backup, protected=True)

    assert config.read_bytes() == original
    assert not backup.exists()


def test_config_remediation_changes_only_adb_debug(tmp_path):
    config = tmp_path / "leidian3.config"
    backup = tmp_path / "leidian3.config.backup"
    original = config_bytes()
    config.write_bytes(original)

    result = remediate(config, backup)

    assert result.previous_value == 0
    assert result.current_value == 1
    assert backup.read_bytes() == original
    before = json.loads(backup.read_text(encoding="utf-8"))
    after = json.loads(config.read_text(encoding="utf-8"))
    before.pop("basicSettings.adbDebug")
    after.pop("basicSettings.adbDebug")
    assert before == after
    changed_lines = [
        (old, new)
        for old, new in zip(
            backup.read_text(encoding="utf-8").splitlines(),
            config.read_text(encoding="utf-8").splitlines(),
        )
        if old != new
    ]
    assert changed_lines == [
        ('  "basicSettings.adbDebug": 0,', '  "basicSettings.adbDebug": 1,')
    ]


def test_config_backup_exists_before_atomic_mutation(tmp_path, monkeypatch):
    config = tmp_path / "leidian3.config"
    backup = tmp_path / "leidian3.config.backup"
    original = config_bytes()
    config.write_bytes(original)
    replace = config_remediation.os.replace
    observed = []

    def verify_backup_then_replace(source, destination):
        assert backup.is_file()
        assert backup.read_bytes() == original
        assert destination == config
        observed.append(True)
        replace(source, destination)

    monkeypatch.setattr(config_remediation.os, "replace", verify_backup_then_replace)
    remediate(config, backup)

    assert observed == [True]
    assert json.loads(config.read_text(encoding="utf-8"))["basicSettings.adbDebug"] == 1


def test_config_remediation_rejects_wrong_identity_and_preexisting_backup(tmp_path):
    config = tmp_path / "leidian3.config"
    backup = tmp_path / "leidian3.config.backup"
    original = config_bytes()
    config.write_bytes(original)

    with pytest.raises(ConfigRemediationError, match="index/name allowlist"):
        remediate(config, backup, live_name="other clone")
    assert config.read_bytes() == original
    assert not backup.exists()

    backup.write_bytes(b"preserve existing backup")
    with pytest.raises(ConfigRemediationError, match="overwrite"):
        remediate(config, backup)
    assert config.read_bytes() == original
    assert backup.read_bytes() == b"preserve existing backup"
