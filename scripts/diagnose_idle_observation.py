"""Authorized index-2-only recovery and Idle detection; never run a reward task.

One execution produces a new report directory. Existing claims are not replayed.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from top_heroes_auto.adb.client import Target  # noqa: E402
from top_heroes_auto.app.diagnostic import _manager, _state  # noqa: E402
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery  # noqa: E402
from top_heroes_auto.app.task_cli import DiagnosticIdleRewardPort  # noqa: E402
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError  # noqa: E402
from top_heroes_auto.vision.debug import write_overlay  # noqa: E402
from top_heroes_auto.vision.idle_detector import IdleRewardDetector  # noqa: E402
from top_heroes_auto.vision.matcher import match_anchor  # noqa: E402
from top_heroes_auto.vision.screenshot import ScreenshotService  # noqa: E402

PROTECTED = {0: 'Queen', 1: 'anh Ry', 6: 'Chicken', 7: 'Happy'}


def analyze(path: Path, folder: Path, label: str) -> dict:
    metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    identity = metadata['instance']
    target = Target(identity['index'], identity['name'], metadata['adb_target'], metadata['boot_id'])
    screen = ScreenshotService(lambda _: path.read_bytes()).take(target)
    screen = replace(screen, source_image=path, device_size=tuple(metadata['device_resolution']),
                     rotated_from_portrait=metadata['rotated_from_portrait'])
    detector = IdleRewardDetector()
    detection = detector.detect(screen)
    matches = tuple(match_anchor(screen, anchor) for anchor in detector.anchors)
    overlay = folder / f'{label}-overlay.png'
    write_overlay(screen, replace(detection, evidence=matches), overlay)
    return {'source': str(path), 'overlay': str(overlay), 'detection': detection.as_dict(),
            'device_resolution': screen.device_size, 'normalized_resolution': screen.normalized_size,
            'anchors': [{'roi': vars(anchor.expected_region), **match.as_dict()}
                        for anchor, match in zip(detector.anchors, matches, strict=True)]}


def main():
    if sys.argv[1:] != ['--execute-index-2-observation-only']:
        raise SystemExit('Explicit observation-only flag required; no fleet or claim mode exists.')
    data = Path(os.environ['LOCALAPPDATA']) / 'TopHeroesAutoManager'
    folder = ROOT / 'diagnostics' / ('idle-repair-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'))
    folder.mkdir(parents=True, exist_ok=False)
    manager = _manager(data)
    snapshot = RunSnapshot(manager.namespace, ((2, '5-Emmmmm'),), True)
    report = {'mode': 'OBSERVATION_ONLY', 'claims_dispatched': 0, 'folder': str(folder)}
    owned = False
    original_selection = None

    def guard():
        live = manager.list_readonly()
        for index, name in PROTECTED.items():
            if len([x for x in live if x.index == index and x.name == name]) != 1:
                raise SafetyError('Protected identity changed.')
            meta = manager.store.metadata(manager.namespace, index)
            if not meta.protected or meta.selected:
                raise SafetyError('Protected metadata changed.')
        current = manager.query(2)
        if current.name != '5-Emmmmm' or manager.store.metadata(manager.namespace, 2).protected:
            raise SafetyError('Authorized index-2 identity/protection mismatch.')
        return _state(live)

    try:
        report['before_instances'] = guard()
        config = json.loads(Path('D:/LDPlayer/LDPlayer9/vms/config/leidian2.config').read_text(encoding='utf-8-sig'))
        if config.get('statusSettings.playerName') != '5-Emmmmm' or config.get('basicSettings.adbDebug') != 1:
            raise SafetyError('ADB configuration unavailable; no setting will be changed.')
        original_selection = manager.store.metadata(manager.namespace, 2).selected
        manager.select(2, True)
        recovery, recovery_path, owned = run_home_recovery(manager, data, 2, '5-Emmmmm', cleanup_owned=False)
        report['recovery_report'] = str(recovery_path)
        report['recovery'] = recovery.as_dict()
        if recovery.status.value not in {'SUCCESS', 'ALREADY_HOME', 'UNKNOWN_SCREEN', 'LOADING_TIMEOUT'}:
            raise SafetyError('Recovery identity/runtime could not be established.')
        if recovery.adb_target != 'emulator-5558' or not recovery.boot_id:
            raise SafetyError('Explicit expected runtime identity unavailable.')
        guard()
        port = DiagnosticIdleRewardPort(manager, snapshot, 2, '5-Emmmmm', folder,
                                        require_known_promo=recovery.status.value == 'LOADING_TIMEOUT')
        port.verified_identity = (recovery.adb_target, recovery.boot_id)
        # This is only observation plus the existing qualified promo Back. Never
        # invoke IdleRewardTask.run, tap, or enter a reward screen.
        observation = port.observe('001-game-home')
        report['detection'] = observation.detection.as_dict()
        report['promo_recovery'] = port.promo_result.as_dict() if port.promo_result else None
        report['frames'] = [analyze(path, folder, path.stem) for path in folder.glob('*.png')
                            if not path.name.endswith('-overlay.png') and path.with_suffix('.json').exists()]
        report['result'] = 'DETECTED' if observation.detection.state.value == 'GAME_HOME' else 'UNKNOWN_NO_INPUT'
    except RecoveryFailure as exc:
        owned = exc.started_by_run and not exc.cleanup_attempted
        report['error'] = str(exc)
        report['result'] = 'BLOCKED'
    except Exception as exc:  # noqa: BLE001 - preserve diagnostic result and execute owned cleanup
        report['error'] = str(exc)
        report['result'] = 'BLOCKED'
    finally:
        report['cleanup'] = 'NOT_OWNED'
        if owned:
            try:
                guard()
                manager.execute(2, 'quit', snapshot=snapshot)
                report['cleanup'] = 'STOPPED_OWNED'
            except Exception as exc:  # noqa: BLE001 - report uncertain cleanup, never retry
                report['cleanup'] = 'FAILED: ' + str(exc)
        if original_selection is not None:
            try:
                guard()
                manager.select(2, original_selection)
            except Exception as exc:  # noqa: BLE001 - retain report even when selection cannot be restored
                report['selection_restore_error'] = str(exc)
        report['after_instances'] = _state(manager.list_readonly())
        before = report.get('before_instances', {})
        report['unrelated_changes'] = [idx for idx in set(before) | set(report['after_instances'])
                                       if idx != 2 and before.get(idx) != report['after_instances'].get(idx)]
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(folder / 'report.json'), 'result': report.get('result'),
                          'cleanup': report['cleanup'], 'error': report.get('error')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
