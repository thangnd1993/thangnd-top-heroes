"""Display metadata never repairs identity; existing disk/runtime/protection do."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity
from top_heroes_auto.automation.guard import SafetyError, create_snapshot, require_selected
from top_heroes_auto.ldplayer.client import Instance
from top_heroes_auto.storage.store import Store


def fixture(tmp_path, name='Current 名字'):
    root = tmp_path/'vms'
    (root/'config').mkdir(parents=True)
    (root/'leidian23').mkdir()
    (root/'leidian23/data.vmdk').write_bytes(b'offline disk identity only')
    config = root/'config/leidian23.config'
    config.write_text('{}')
    current = Instance(23, name, False, 0, 0, 1280, 720, 240)
    manager = SimpleNamespace(ld=SimpleNamespace(installation=SimpleNamespace(console=tmp_path/'ldconsole.exe')),
                              query=lambda _:current)
    return manager, current, config


@pytest.mark.parametrize('metadata', [{}, {'statusSettings.playerName':None},
                                     {'statusSettings.playerName':'stale stored name'}])
def test_optional_missing_or_stale_metadata_keeps_stable_identity(tmp_path, metadata):
    m, current, config = fixture(tmp_path)
    original = persistent_identity(m, 23)
    config.write_text(json.dumps(metadata))
    before = config.read_bytes()
    assert persistent_identity(m, 23) == original
    assert config.read_bytes() == before
    m.query = lambda _:replace(current, name='Renamed é 中文')
    assert persistent_identity(m, 23) == original


def test_missing_config_file_is_optional_not_disk_identity(tmp_path):
    m, _, config = fixture(tmp_path)
    original = persistent_identity(m, 23)
    config.unlink()
    assert persistent_identity(m, 23) == original
    assert not config.exists()


def test_ambiguous_or_changed_runtime_fails_closed(tmp_path):
    m, current, _ = fixture(tmp_path)
    samples = iter([current,replace(current,pid=123)])
    m.query = lambda _:next(samples)
    with pytest.raises(SafetyError, match='IDENTITY_UNVERIFIED'):
        persistent_identity(m, 23)


def test_missing_backing_disk_fails_closed(tmp_path):
    m, _, _ = fixture(tmp_path)
    (tmp_path/'vms/leidian23/data.vmdk').unlink()
    with pytest.raises(OSError):
        persistent_identity(m, 23)


def test_protection_survives_rename_and_missing_display_metadata(tmp_path):
    m, current, config = fixture(tmp_path)
    store = Store(tmp_path/'fixture.sqlite3')
    store.merge('fixture',(current,))
    store.protect('fixture',23,True)
    renamed = replace(current,name='Manual rename')
    store.merge('fixture',(renamed,))
    m.query = lambda _:renamed
    assert persistent_identity(m,23)
    assert store.metadata('fixture',23).protected
    snapshot = create_snapshot(store,'fixture',(renamed,))
    with pytest.raises(SafetyError):
        require_selected(store,snapshot,(renamed,),23)
    assert config.read_bytes() == b'{}'
