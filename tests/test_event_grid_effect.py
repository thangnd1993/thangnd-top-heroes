"""Saved explicit claimed state cannot use stale, popup or wrong-target evidence."""

import json
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.app.event_grid_effect import claimed_grid_effect
from top_heroes_auto.vision.event_task_grid import task_grid_rows, task_grid_shell
from top_heroes_auto.vision.local_ocr import read_words


@pytest.fixture
def proof_files(tmp_path):
    if __import__("sys").platform != "win32":
        pytest.skip("Windows local OCR evidence")
    before = cv2.imread("tests/fixtures/phase8/task-grid-complete-exceeded.png")
    after = cv2.imread("tests/fixtures/phase8/task-grid-claimed.png")
    row = next(
        r
        for r in task_grid_rows(before, task_grid_shell(before), reader=read_words)
        if r["state"] == "AVAILABLE"
    )
    identity = [13, "user-owned", "explicit", "boot"]
    page = "event:functional-race-task-grid:race-task-grid"
    files = []
    for n, image in enumerate((before, after, after)):
        path = tmp_path / f"{n}.png"
        path.write_bytes(cv2.imencode(".png", image)[1].tobytes())
        frame = dict(
            identity=identity,
            page=page,
            popup=False,
            controls=(
                [
                    dict(
                        kind="reward",
                        identity=row["identity"],
                        cost="FREE",
                        available=True,
                        box=vars(row["box"]),
                    )
                ]
                if n == 0
                else []
            ),
        )
        path.with_suffix(".event.json").write_text(
            json.dumps(dict(frame=frame, entered_event="current-root"))
        )
        path.with_suffix(".json").write_text(
            json.dumps(
                dict(
                    instance=dict(index=13, name="user-owned"),
                    adb_target="explicit",
                    boot_id="boot",
                    timestamp=f"2026-10-05T10:0{n}:00+00:00",
                )
            )
        )
        files.append(path)
    proof = dict(
        capture=str(files[0]),
        identity=identity,
        page=page,
        event="functional-race-task-grid",
        reward=row["identity"],
        tap=list(row["box"].center),
    )
    return proof, files


def test_two_explicit_claimed_states_verify_without_receipt_or_input(proof_files):
    proof, files = proof_files
    result = claimed_grid_effect(proof, files[1:])
    assert len(result) == 2 and all(not r["receipt_required"] for r in result)
    assert all(
        {"explicit-claimed-label", "original-green-control-absent"}.issubset(r["independent_evidence"])
        for r in result
    )
    assert not claimed_grid_effect(proof, [files[1], files[1]])
    assert not claimed_grid_effect(proof, [files[0], files[1]])


@pytest.mark.parametrize("change", ["popup", "root", "serial", "timestamp", "still-free", "missing-label"])
def test_unqualified_or_unrelated_post_state_never_verifies(proof_files, change):
    proof, files = proof_files
    path = files[2]
    meta = json.loads(path.with_suffix(".event.json").read_text())
    shot = json.loads(path.with_suffix(".json").read_text())
    if change == "popup":
        meta["frame"]["popup"] = True
    if change == "root":
        meta["entered_event"] = "other-root"
    if change == "serial":
        meta["frame"]["identity"][2] = "other-serial"
        shot["adb_target"] = "other-serial"
    if change == "timestamp":
        shot["timestamp"] = "2026-10-05T09:00:00+00:00"
    if change == "still-free":
        path.write_bytes(Path("tests/fixtures/phase8/task-grid-complete-exceeded.png").read_bytes())
    if change == "missing-label":
        im = cv2.imread(str(path))
        im[680:720, 505:607] = 40
        path.write_bytes(cv2.imencode(".png", im)[1].tobytes())
    path.with_suffix(".event.json").write_text(json.dumps(meta))
    path.with_suffix(".json").write_text(json.dumps(shot))
    assert not claimed_grid_effect(proof, files[1:])


def test_original_dispatch_requires_exact_free_control_and_category(proof_files):
    proof,files=proof_files
    for key,value in [('tap',[0,0]),('event','other-context')]:
        wrong={**proof,key:value}
        assert not claimed_grid_effect(wrong,files[1:])
    path=files[0].with_suffix('.event.json')
    meta=json.loads(path.read_text())
    meta['frame']['controls'][0]['cost']='VND'
    path.write_text(json.dumps(meta))
    assert not claimed_grid_effect(proof,files[1:])
