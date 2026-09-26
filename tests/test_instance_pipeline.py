"""Global orchestration regressions: fake features/devices, never a real emulator."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from top_heroes_auto.app import automation_fleet as fleet
from top_heroes_auto.app.flow_registry import Flow, FlowRegistry, production_registry
from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.automation.fixed_reward_period import current_attempts, period_start
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus


def setup(calls):
    registry = FlowRegistry()

    class Session:
        def __init__(self, manager, data, target, folder, **kw):
            self.target = target

        def start(self):
            calls.append((self.target["index"], "start"))

        def check(self):
            pass

        def recover(self):
            calls.append((self.target["index"], "recover"))
            return RecoveryResult(RecoveryStatus.SUCCESS), None, False

        def close(self):
            calls.append((self.target["index"], "cleanup"))
            return dict(cleanup="SUCCESS", selection_restored=True)

    def feature(session, folder, rewards):
        calls.append((session.target["index"], folder.name, tuple(rewards)))
        return dict(
            rewards={
                r: dict(result="NOT_AVAILABLE", journal="NONE", claim_dispatched=False) for r in rewards
            },
            return_home="SUCCESS",
        )

    registry.register(Flow("feature-one", ("one", "two"), feature))
    registry.register(Flow("feature-two", ("three",), feature))
    return registry, Session, feature


def run(rig, tmp_path, calls, **kw):
    registry, session, _ = setup(calls)
    return fleet.run(
        rig[0], tmp_path, identity_reader=lambda *a: "disk", registry=registry, session_factory=session, **kw
    )


def test_all_registered_features_finish_instance_before_next_and_cleanup(rig, tmp_path):
    manager, process, _ = rig
    process.listing += "13,another,0,0,0,-1,-1\n"
    calls = []
    registry, session, feature = setup(calls)
    registry.register(Flow("future-feature", ("future-a", "future-b"), feature))
    result = fleet.run(
        manager, tmp_path, registry=registry, session_factory=session, identity_reader=lambda *a: "disk"
    )
    assert result["result"] == "PASS"
    assert calls == [
        (i, event, *args)
        for i in (7, 13)
        for event, args in [
            ("start", ()),
            ("feature-one", (("one", "two"),)),
            ("feature-two", (("three",),)),
            ("future-feature", (("future-a", "future-b"),)),
            ("cleanup", ()),
        ]
    ]
    assert len(result["accounts"][0]["plan"]) == 3
    assert all(c[1:] == ["list2"] for c in process.calls)


def test_blocked_feature_records_all_rewards_and_continues_future_flow(rig, tmp_path):
    calls = []
    registry, session, feature = setup(calls)

    def fail(*a):
        raise SafetyError("known blocker")

    registry.register(Flow("blocked", ("four", "five"), fail))
    registry.register(Flow("later", ("six",), feature))
    result = fleet.run(
        rig[0], tmp_path, registry=registry, session_factory=session, identity_reader=lambda *a: "disk"
    )
    row = result["accounts"][0]
    assert row["result"] == "PARTIAL" and row["rewards"]["six"]["result"] == "NOT_AVAILABLE"
    assert row["rewards"]["four"]["result"] == row["rewards"]["five"]["result"] == "BLOCKED"
    assert calls[-2:] == [(7, "later", ("six",)), (7, "cleanup")]


def test_missing_reward_is_not_silently_complete(rig, tmp_path):
    calls = []
    registry, session, _ = setup(calls)
    registry.register(Flow("omits", ("four",), lambda *a: dict(return_home="SUCCESS")))
    result = fleet.run(
        rig[0], tmp_path, registry=registry, session_factory=session, identity_reader=lambda *a: "disk"
    )
    assert result["accounts"][0]["rewards"]["four"]["result"] == "BLOCKED"
    assert result["result"] == "PARTIAL"


def test_disabled_unsupported_not_applicable_explicit(rig, tmp_path):
    calls = []
    registry, session, feature = setup(calls)
    registry.register(Flow("disabled", ("four",), feature, enabled=False))
    registry.register(Flow("unsupported", ("five",), feature, supported=False))
    registry.register(Flow("not-applicable", ("six",), feature, applicable=lambda t: False))
    result = fleet.run(
        rig[0], tmp_path, registry=registry, session_factory=session, identity_reader=lambda *a: "disk"
    )
    row = result["accounts"][0]
    assert [row["rewards"][r]["result"] for r in ("four", "five", "six")] == [
        "DISABLED",
        "BLOCKED",
        "NOT_APPLICABLE",
    ]
    assert calls == [
        (7, "start"),
        (7, "feature-one", ("one", "two")),
        (7, "feature-two", ("three",)),
        (7, "cleanup"),
    ]


def test_snapshot_immutable_and_registry_duplicate_rejected():
    registry, _, feature = setup([])
    snapshot = registry.snapshot()
    registry.register(Flow("future", ("four",), feature))
    assert len(snapshot) == 2 and len(registry.snapshot()) == 3
    with pytest.raises(ValueError):
        registry.register(Flow("bad", ("one",), feature))
    with pytest.raises(SafetyError):
        registry.snapshot({"unknown": True})


def test_resume_skips_only_completed_rewards_and_retains_proof(rig, tmp_path):
    calls = []
    result = run(rig, tmp_path, calls)
    row = result["accounts"][0]
    row["rewards"]["one"].update(result="SUCCESS", journal="VERIFIED", claim_id=90)
    row["rewards"]["two"]["result"] = "UNKNOWN"
    path = tmp_path / "resume.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    calls.clear()
    resumed = run(rig, tmp_path, calls, resume_report=path)
    assert calls == [(7, "start"), (7, "feature-one", ("two",)), (7, "cleanup")]
    assert resumed["accounts"][0]["rewards"]["one"]["claim_id"] == 90
    assert resumed["result"] == "PASS"


def test_resume_identity_change_no_start(rig, tmp_path):
    calls = []
    result = run(rig, tmp_path, calls)
    path = tmp_path / "resume.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    registry, session, _ = setup(calls)
    calls.clear()
    resumed = fleet.run(
        rig[0],
        tmp_path,
        registry=registry,
        session_factory=session,
        identity_reader=lambda *a: "changed",
        resume_report=path,
    )
    assert not calls and resumed["result"] == "PARTIAL"


def test_recovery_only_resume_never_enters_rewards(rig, tmp_path):
    calls = []
    result = run(rig, tmp_path, calls)
    result["accounts"][0]["recovery_ok"] = False
    path = tmp_path / "resume.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    calls.clear()
    resumed = run(rig, tmp_path, calls, resume_report=path)
    assert calls == [(7, "start"), (7, "recover"), (7, "cleanup")]
    assert resumed["result"] == "PASS" and resumed["accounts"][0]["new_claims"] == 0


@pytest.mark.parametrize("external", [True, False])
def test_shared_session_one_start_then_navigation_only_one_cleanup(rig, tmp_path, external):
    manager, process, _ = rig
    manager.select(7, False)
    calls = []

    def recovery(*a, **kw):
        calls.append(kw)
        assert manager.store.metadata(manager.namespace, 7).selected
        return (
            RecoveryResult(RecoveryStatus.SUCCESS),
            tmp_path / "recovery.json",
            not external if len(calls) == 1 else False,
        )

    session = InstanceSession(
        manager,
        tmp_path,
        dict(index=7, name="Farm-007", persistent_identity="disk"),
        tmp_path,
        identity_reader=lambda *a: "disk",
        recovery_runner=recovery,
    )
    session.start()
    session.recover()
    session.recover()
    session.recover()
    assert not any(c[1] == "quit" for c in process.calls)
    session.close()
    session.close()
    assert sum(c[1] == "quit" for c in process.calls) == (0 if external else 1)
    assert session.report["selection_restored"] and not manager.store.metadata(manager.namespace, 7).selected
    assert len(calls) == 3 and all(c["allow_start"] is False for c in calls[1:])


def test_session_protection_revocation_blocks_cleanup_and_selection(rig, tmp_path):
    manager, process, _ = rig
    session = InstanceSession(
        manager,
        tmp_path,
        dict(index=7, name="Farm-007", persistent_identity="disk"),
        tmp_path,
        identity_reader=lambda *a: "disk",
        recovery_runner=lambda *a, **kw: (RecoveryResult(RecoveryStatus.SUCCESS), tmp_path / "r", True),
    )
    session.start()
    manager.protect(7, True)
    with pytest.raises(SafetyError):
        session.recover()
    session.close()
    assert not any(c[1] == "quit" for c in process.calls)
    assert session.report["cleanup"].startswith("FAILED")


def test_no_phase_specific_scheduler_and_current_registration():
    import inspect

    source = inspect.getsource(fleet)
    assert "run_vip" not in source and "run_bxh" not in source and "phase6" not in source.lower()
    plan = production_registry().snapshot()
    assert [f.id for f in plan] == ["vip", "ranking", "shop"]
    assert len([r for f in plan for r in f.rewards]) == 7


@pytest.mark.parametrize(
    "reward",
    ["ranking-chest", "shop-weekly-card-gift", "shop-permanent-privilege-gift", "shop-monthly-quick-collect"],
)
def test_user_confirmed_vietnam_0900_period_boundary_preserves_journals(reward):
    reset = datetime(2026, 9, 26, 2, tzinfo=timezone.utc)
    assert period_start(reward, reset - timedelta(microseconds=1)) == reset - timedelta(days=1)
    assert period_start(reward, reset) == reset
    row = dict(reward_id=reward, status="VERIFIED", reserved_at=(reset - timedelta(seconds=1)).isoformat())
    assert current_attempts([row], reward, reset - timedelta(microseconds=1)) == [row]
    assert current_attempts([row], reward, reset) == [] and row["status"] == "VERIFIED"
    row.update(status="RESERVED", dispatch_state="POSSIBLE")
    assert current_attempts([row], reward, reset) == [row]
    row["reserved_at"] = "unproven"
    assert current_attempts([row], reward, reset) == [row]


def test_selected_adapter_keeps_exact_target_and_cleanup_failure_visible(monkeypatch,tmp_path):
    from top_heroes_auto.app import registered_tasks
    calls=[]
    def run(manager,data,**kw):
        calls.append(kw)
        return dict(accounts=[dict(result='PARTIAL',cleanup='FAILED',flows={'one':dict(result='COMPLETE',rewards={})})])
    monkeypatch.setattr(registered_tasks,'run',run)
    result=registered_tasks.run_registered_selected(None,tmp_path,71,'exact')
    assert calls[0]['targets']==[dict(index=71,name='exact')]
    assert calls[0]['temporary_selection'] is False
    assert result[-1].status=='PARTIAL' and not result[-1].cleanup_succeeded


def test_no_lifecycle_for_an_inapplicable_plan(rig,tmp_path):
    calls=[]
    _,session,feature=setup(calls)
    registry=FlowRegistry()
    registry.register(Flow('future',('future',),feature,applicable=lambda t:False))
    result=fleet.run(rig[0],tmp_path,registry=registry,session_factory=session,identity_reader=lambda *a:'disk')
    assert not calls and result['result']=='PASS'


def test_uncertain_lifecycle_ownership_never_reports_cleanup_success(rig,tmp_path):
    manager,process,_=rig
    session=InstanceSession(manager,tmp_path,dict(index=7,name='Farm-007',persistent_identity='disk'),tmp_path,
        identity_reader=lambda *a:'disk',recovery_runner=lambda *a,**kw:(
            RecoveryResult(RecoveryStatus.SUCCESS,ownership_uncertain=True),tmp_path/'r',False))
    session.start()
    session.close()
    assert session.report['cleanup']=='OWNERSHIP_UNKNOWN'
    assert not any(c[1]=='quit' for c in process.calls)


@pytest.mark.parametrize('reward',['ranking-chest','shop-daily-gift','shop-weekly-card-gift',
                                  'shop-permanent-privilege-gift','shop-monthly-quick-collect'])
def test_canonical_past_possible_period_expires_eligibility_only(reward):
    from top_heroes_auto.automation.fixed_reward_period import cycle_key
    reset=datetime(2026,9,26,2,tzinfo=timezone.utc)
    earlier=reset-timedelta(seconds=1)
    row=dict(reward_id=reward,status='RESERVED',dispatch_state='POSSIBLE',
             reserved_at=earlier.isoformat(),cycle_key=cycle_key(reward,earlier))
    original=dict(row)
    assert current_attempts([row],reward,earlier)==[row]
    assert current_attempts([row],reward,reset)==[]
    assert row==original  # Never verify/delete/downgrade historical POSSIBLE.
    row['cycle_key']=cycle_key(reward,reset)
    assert current_attempts([row],reward,reset)==[row]  # Inconsistent period evidence.


def test_new_period_reservation_preserves_old_possible_and_blocks_same_period(rig):
    from top_heroes_auto.automation.fixed_reward_period import cycle_key
    _,_,store=rig
    reward='shop-daily-gift'
    task=store.create_task_run('n','bxh-shop-fixed',23,'exact')
    cid=store.reserve_reward_claim(task,reward,cycle_key(reward),'{}',not_dispatched=True,fixed_reward_period=True)
    store.mark_reward_dispatch(cid,task)
    old=datetime.now(timezone.utc)-timedelta(days=2)
    with store.connect() as db:
        db.execute('UPDATE reward_claims SET reserved_at=?,cycle_key=? WHERE id=?',
                   (old.isoformat(),cycle_key(reward,old),cid))
    original=dict(store.reward_claims('n',23)[0])
    new=store.reserve_reward_claim(task,reward,cycle_key(reward),'{}',not_dispatched=True,fixed_reward_period=True)
    assert new!=cid and dict(store.reward_claims('n',23)[0])==original
    with pytest.raises(ValueError,match='already attempted'):
        store.reserve_reward_claim(task,reward,cycle_key(reward),'{}',fixed_reward_period=True)
