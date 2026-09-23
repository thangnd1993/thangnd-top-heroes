"""Explicit index-2-only acceptance of both annotated free VIP targets."""

from datetime import datetime, timezone

from top_heroes_auto.app.diagnostic import _manager, _view
from top_heroes_auto.app.main import data_directory
from top_heroes_auto.app.vip_fleet import _protected, _write, run_vip_account


def run(manager, data):
    _protected(manager)
    before = _view(manager, manager.list_readonly())
    folder = data / "diagnostics/tasks/vip-popup-acceptance" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    result = run_vip_account(manager, data, 2, "5-Emmmmm", folder, include_upper_gift=True)
    after = _view(manager, manager.list_readonly())
    report = dict(before_instances=before, account=result, after_instances=after,
                  unrelated_unchanged=all(r in after for r in before if r["index"] != 2),
                  selections_restored={r["index"]: r["selected"] for r in before} ==
                  {r["index"]: r["selected"] for r in after})
    _write(folder / "acceptance-report.json", report)
    print(folder / "acceptance-report.json", flush=True)
    return report


if __name__ == "__main__":
    run(_manager(data_directory()), data_directory())
