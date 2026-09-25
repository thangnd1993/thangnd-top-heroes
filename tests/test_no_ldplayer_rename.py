"""Offline-only identity fixtures; no real LDPlayer rename or emulator launch."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity
from top_heroes_auto.app.process import CommandError, Process
from top_heroes_auto.automation.guard import SafetyError, create_snapshot
from top_heroes_auto.ldplayer.client import parse_list2


@pytest.mark.parametrize('command', ['rename','modify','restore','copy','add','remove','quitall','Rename'])
def test_cli_boundary_rejects_name_and_config_mutation(monkeypatch,command):
    calls=[]
    monkeypatch.setattr('subprocess.run',lambda *a,**k:calls.append(a))
    with pytest.raises(CommandError,match='read-only'):
        Process().run(['D:/LDPlayer/ldconsole.exe',command,'--index','7','--title','new'])
    assert calls==[]


@pytest.mark.parametrize('command',['rename','modify','restore'])
def test_indexed_wrapper_cannot_bypass_boundary(rig,command):
    manager,process,_=rig
    with pytest.raises(ValueError,match='allowlist'):
        manager.ld._indexed(command,7,'--title','new')
    assert process.calls==[]


@pytest.mark.parametrize('name',['  Tên mới 🌿, e\u0301  ','中文 • 𝒜 • Queen','Nấm đùi gà'])
def test_manual_unicode_rename_is_preserved_and_runtime_reverified(rig,name):
    manager,process,store=rig
    original,_=manager.capture_verified(7)
    process.calls.clear()
    process.listing=process.listing.replace('Farm-007',name)
    current=manager.refresh()
    assert next(i.name for i in current if i.index==7)==name
    with store.connect() as db:
        assert db.execute('SELECT name FROM instances WHERE namespace=? AND idx=7',(manager.namespace,)).fetchone()[0]==name
    # Fresh explicit authorization, never resurrect stale opt-in after a rename.
    manager.select(7,True)
    target,_=manager.capture_verified(7)
    assert target.name==name
    assert (target.index,target.serial,target.boot_id)==(original.index,original.serial,original.boot_id)
    assert all(c[1] not in {'rename','modify','restore'} for c in process.calls)
    assert any(c[1:3]==['-s',target.serial] for c in process.calls)


def test_protection_survives_manual_rename_without_any_input(rig):
    manager,process,store=rig
    manager.protect(7,True)
    process.calls.clear()
    process.listing=process.listing.replace('Farm-007','Tên được bảo vệ 🌿')
    manager.refresh()
    assert store.metadata(manager.namespace,7).protected
    assert not store.metadata(manager.namespace,7).selected
    with pytest.raises(SafetyError):
        manager.capture_verified(7)
    assert all(c[1]=='list2' for c in process.calls)


def test_stale_snapshot_and_ambiguous_adb_fail_closed_without_rename(rig):
    manager,process,store=rig
    snapshot=create_snapshot(store,manager.namespace,manager.refresh())
    process.listing=process.listing.replace('Farm-007','User chosen')
    manager.refresh()
    manager.select(7,True)
    process.calls.clear()
    with pytest.raises(SafetyError):
        manager.capture_verified(7,snapshot)
    assert all(c[1]=='list2' for c in process.calls)
    process.device_boot='different-runtime'
    with pytest.raises(SafetyError):
        manager.capture_verified(7)
    assert not any('screencap' in c or c[1] in {'rename','modify'} for c in process.calls)


def test_stable_disk_identity_does_not_depend_on_display_name(tmp_path):
    root=tmp_path/'vms'
    (root/'config').mkdir(parents=True)
    (root/'leidian7').mkdir()
    (root/'leidian7/data.vmdk').write_bytes(b'fixture only')
    config=root/'config/leidian7.config'
    current=SimpleNamespace(name='Old')
    manager=SimpleNamespace(ld=SimpleNamespace(installation=SimpleNamespace(console=tmp_path/'ldconsole.exe')),
                            query=lambda _:current)
    config.write_text(json.dumps({'statusSettings.playerName':current.name}),encoding='utf-8')
    before=persistent_identity(manager,7)
    # Simulated USER edit in a temporary fixture, never an application write.
    current.name='Tên MỚI, e\u0301'
    config.write_text(json.dumps({'statusSettings.playerName':current.name},ensure_ascii=False),encoding='utf-8')
    preserved=config.read_bytes()
    assert persistent_identity(manager,7)==before
    assert config.read_bytes()==preserved


def test_all_production_indexed_call_sites_use_only_allowed_verbs():
    root=Path(__file__).parents[1]/'src'
    found=[]
    for source in root.rglob('*.py'):
        tree=ast.parse(source.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='_indexed':
                assert node.args and isinstance(node.args[0],ast.Constant),str(source)
                assert node.args[0].value in {'launch','quit','adb'},str(source)
                found.append(node.args[0].value)
    assert set(found)=={'launch','quit','adb'}


@pytest.mark.parametrize('module',['app/recovery_cli.py','app/bxh_shop_acceptance.py','app/vip_fleet.py',
                                   'app/diagnostic.py','storage/fleet_repair.py'])
def test_recovery_fleet_diagnostics_and_migration_have_no_name_writer(module):
    source=Path(__file__).parents[1]/'src/top_heroes_auto'/module
    tree=ast.parse(source.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            assert node.func.attr not in {'rename','renames','copy2'}
            # Diagnostic screenshot Path.replace is not an LDPlayer config write.
            if node.func.attr == 'replace':
                assert module == 'app/diagnostic.py'
                assert isinstance(node.func.value,ast.Name) and node.func.value.id in {'first','second'}
    # Read-only Unicode discovery must remain exact.
    assert parse_list2('7,Tên mới,0,0,0,-1,-1')[0].name=='Tên mới'
