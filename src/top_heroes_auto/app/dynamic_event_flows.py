"""Phase 8 registers with the shared instance-first pipeline."""
import json
from dataclasses import asdict

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.app.flow_registry import REGISTRY, Flow
from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer


def run(session, folder, rewards, *, port_factory=DynamicEventPort):
    folder.mkdir(parents=True,exist_ok=True)
    report = dict(index=session.index,name=session.name,rewards={},return_home='NOT_STARTED')
    path = folder/'feature-report.json'

    def persist(exploration=None):
        if exploration is not None:
            report['exploration'] = exploration
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

    recovery, recovery_path, _ = session.recover()
    report.update(recovery=recovery.status.value,recovery_report=str(recovery_path),adb=recovery.adb_target)
    if recovery.status.value not in {'SUCCESS','ALREADY_HOME'}:
        report['rewards']['dynamic-event-exploration'] = dict(result='BLOCKED',claim_dispatched=False)
        persist()
        return report
    result = DynamicEventExplorer().run(port_factory(session,folder),persist=persist)
    report['exploration'] = asdict(result)
    report['return_home'] = result.return_home
    report['rewards']['dynamic-event-exploration'] = dict(result=result.result,
        claim_dispatched=any(r.get('claim_dispatched') for r in result.rewards),
        claim_count=sum(bool(r.get('claim_dispatched')) for r in result.rewards),
        verified=sum(r.get('journal') == 'VERIFIED' and r.get('claim_dispatched',False) for r in result.rewards))
    persist()
    return report


# This is a coverage summary only. Real reward journals use event/page/reward keys.
REGISTRY.register(Flow('events',('dynamic-event-exploration',),run,refresh_current_batches=True))
