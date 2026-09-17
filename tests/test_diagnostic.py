from dataclasses import replace
from pathlib import Path

import pytest

from top_heroes_auto.app.diagnostic import list_command, protect_command, test_command as run_test_command
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.client import Instance
from top_heroes_auto.storage.store import Store


class DiagnosticManager:
    namespace = "diagnostic-install"

    def __init__(self, path: Path):
        self.store = Store(path / "config.sqlite3")
        self.data_dir = path
        self.instances = [
            Instance(0, "Queen", False, -1, -1, 1280, 720, 240),
            Instance(4, "3-Chíp", False, -1, -1, 1280, 720, 240),
            Instance(7, "Other", False, -1, -1, 1280, 720, 240),
        ]
        self.store.merge(self.namespace, tuple(self.instances))
        self.calls = []

    def refresh(self):
        self.store.merge(self.namespace, tuple(self.instances))
        return tuple(self.instances)

    def list_readonly(self):
        return tuple(self.instances)

    def query(self, index):
        matches = [item for item in self.refresh() if item.index == index]
        if len(matches) != 1:
            raise SafetyError("missing")
        return matches[0]

    def protect(self, index, value):
        self.store.protect(self.namespace, index, value)

    def select(self, index, value):
        self.store.select(self.namespace, index, value)

    def execute(self, index, action, package="", values=()):
        self.calls.append((index, action, package, values))
        if index != 4:
            raise AssertionError("diagnostic dispatched an unexpected instance")
        if action in {"launch", "reboot"}:
            self.instances[1] = replace(self.instances[1], android_started=True, pid=400)
            return "verified emulator-5568"
        if action == "quit":
            self.instances[1] = replace(self.instances[1], android_started=False, pid=-1)
            return "stopped"
        if action == "screenshot":
            folder = self.data_dir / "screenshots"
            folder.mkdir(exist_ok=True)
            image = folder / f"{len(self.calls)}.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n")
            return image
        if action == "packages":
            return "package:com.example.topheroes.game\n"
        return "ok"


def test_list_is_read_only(tmp_path):
    manager = DiagnosticManager(tmp_path)
    before = manager.store.metadata(manager.namespace, 4)
    result = list_command(manager, tmp_path)
    assert result["instances"][0]["name"] == "Queen"
    assert manager.calls == []
    assert manager.store.metadata(manager.namespace, 4) == before


def test_protect_requires_exact_identity_and_clears_selection(tmp_path):
    manager = DiagnosticManager(tmp_path)
    manager.select(0, True)
    with pytest.raises(SafetyError):
        protect_command(manager, tmp_path, 0, "Not Queen")
    assert manager.store.metadata(manager.namespace, 0).selected
    protect_command(manager, tmp_path, 0, "Queen")
    assert manager.store.metadata(manager.namespace, 0).protected
    assert not manager.store.metadata(manager.namespace, 0).selected


def test_diagnostic_rejects_protected_target_and_identity_mismatch(tmp_path):
    manager = DiagnosticManager(tmp_path)
    manager.protect(0, True)
    manager.protect(4, True)
    with pytest.raises(SafetyError):
        run_test_command(manager, tmp_path, 4, "3-Chíp")
    with pytest.raises(SafetyError):
        run_test_command(manager, tmp_path, 4, "Wrong")
    assert manager.calls == []


def test_diagnostic_uses_only_explicit_target_and_reresolves_adb(tmp_path):
    manager = DiagnosticManager(tmp_path)
    manager.protect(0, True)
    report = run_test_command(manager, tmp_path, 4, "3-Chíp")
    assert report["isolation"] == "passed"
    assert report["top_heroes_package"] == "com.example.topheroes.game"
    assert all(call[0] == 4 for call in manager.calls)
    assert sum(call[1] == "verify" for call in manager.calls) == 2
    assert (tmp_path / "diagnostics" / "3-Chíp").is_dir()
