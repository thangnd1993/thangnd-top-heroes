import json
import os
from contextlib import nullcontext
from types import SimpleNamespace as NS

import pytest

from top_heroes_auto.app import authorized_adb_config as config
from top_heroes_auto.app.authorized_adb_config import FIELD, patch_field, writer_lock


@pytest.mark.parametrize('source', [b'{}', b'{\r\n "name":"user\\u540d", "unknown":[2,{"z":true}]\r\n}',
    b'{"basicSettings.adbDebug":0,"name":"USER"}',
    b'{"nested":{"basicSettings.adbDebug":9},"basicSettings.adbDebug":false}',
    b'\xef\xbb\xbf {"name":"USER"} '])
def test_only_requested_field_changes(source):
    result, original = patch_field(source)
    before = json.loads(source)
    expected = dict(before)
    expected[FIELD] = 1
    assert json.loads(result) == expected
    assert original == dict(present=FIELD in before, value=before.get(FIELD))
    if FIELD not in before:
        assert result.replace(b'"basicSettings.adbDebug":1' + (b',' if before else b''), b'', 1) == source
    else:
        assert b'"name":"USER"' not in source or b'"name":"USER"' in result


@pytest.mark.parametrize('source', [b'[]', b'{', b'{"name":1,"name":2}', b'{"x":{"a":1,"a":2}}', b'{} extra'])
def test_ambiguous_or_malformed_config_never_fabricated(source):
    with pytest.raises(ValueError):
        patch_field(source)


@pytest.mark.skipif(os.name != 'nt', reason='Windows file sharing')
def test_kernel_lock_refuses_concurrent_writer(tmp_path):
    path = tmp_path/'config'
    path.write_bytes(b'{}')
    with writer_lock(path) as stream:
        assert stream.read() == b'{}'
        with pytest.raises(OSError):
            path.write_bytes(b'changed')
    assert path.read_bytes() == b'{}'


@pytest.mark.parametrize('protected,running,identity,authorized', [
    (True, False, 'disk', {2}), (False, True, 'disk', {2}),
    (False, False, 'replaced', {2}), (False, False, 'disk', {3}),
])
def test_guard_rejection_leaves_config_and_backup_untouched(tmp_path, monkeypatch, protected, running, identity, authorized):
    path = tmp_path/'vms/config/leidian2.config'
    path.parent.mkdir(parents=True)
    original = b'{"name":"USER","unknown":42}'
    path.write_bytes(original)
    manager = NS(ld=NS(installation=NS(console=tmp_path/'ldconsole.exe')),
        namespace='test', store=NS(metadata=lambda *a: NS(protected=protected)),
        query=lambda i: NS(running=running, stable_id=identity))
    monkeypatch.setattr(config, 'mutation_ownership', lambda m: nullcontext())
    monkeypatch.setattr(config, 'persistent_identity', lambda m, i: identity)
    backup = tmp_path/'backup/config'
    with pytest.raises(ValueError):
        config.enable(manager, 2, 'disk', backup, authorized_indexes=authorized)
    assert path.read_bytes() == original
    assert not backup.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows file sharing')
def test_authorized_change_keeps_exact_backup_and_unknown_fields(tmp_path, monkeypatch):
    path = tmp_path/'vms/config/leidian2.config'
    path.parent.mkdir(parents=True)
    original = b'{\r\n "name":"USER", "unknown":[42,false]\r\n}'
    path.write_bytes(original)
    manager = NS(ld=NS(installation=NS(console=tmp_path/'ldconsole.exe')),
        namespace='test', store=NS(metadata=lambda *a: NS(protected=False)),
        query=lambda i: NS(running=False, stable_id='disk'))
    monkeypatch.setattr(config, 'mutation_ownership', lambda m: nullcontext())
    monkeypatch.setattr(config, 'persistent_identity', lambda m, i: 'disk')
    backup = tmp_path/'backup/config'
    proof = config.enable(manager, 2, 'disk', backup, authorized_indexes={2})
    assert backup.read_bytes() == original
    assert path.read_bytes() == patch_field(original)[0]
    assert proof['other_values_unchanged']
    assert proof['original'] == dict(present=False, value=None)
