"""The retired ADB writer must never rewrite a user-owned instance name."""
import json

import pytest

from top_heroes_auto.ldplayer.config_remediation import ConfigRemediationError, enable_authorized_adb_debug


@pytest.mark.parametrize('protected', [False, True])
@pytest.mark.parametrize('name', ['Queen con', 'Tên mới 🌿, e\u0301', '旧名称'])
def test_retired_writer_preserves_entire_config_and_backup(tmp_path, protected, name):
    config=tmp_path/'leidian3.config'
    backup=tmp_path/'leidian3.config.backup'
    original=json.dumps({'statusSettings.playerName':name,'basicSettings.adbDebug':0},ensure_ascii=False).encode('utf-8')
    config.write_bytes(original)
    backup.write_bytes(b'old backup must never be restored')
    with pytest.raises(ConfigRemediationError,match='disabled'):
        enable_authorized_adb_debug(3,'old stored name',config,backup,live_name=name,protected=protected)
    assert config.read_bytes()==original
    assert backup.read_bytes()==b'old backup must never be restored'


def test_retired_writer_does_not_even_create_files(tmp_path):
    with pytest.raises(ConfigRemediationError):
        enable_authorized_adb_debug(3,'old',tmp_path/'missing',tmp_path/'backup',live_name='new',protected=False)
    assert list(tmp_path.iterdir())==[]
