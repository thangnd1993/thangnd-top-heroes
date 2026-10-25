"""One-file diagnostic export for a finished run.

Strictly read-only toward existing data: reports are copied, the journal is read
through a read-only SQLite connection, and nothing is deleted, reset or rewritten.
The bundle contains what is needed to find missed rewards, wrong navigation,
excessive waits and unverified claims. Missing evidence is listed, never invented."""
import hashlib
import json
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from top_heroes_auto.app.version_info import load_version_info

MAX_FILE_BYTES = 25_000_000
MAX_SCREENSHOT_BYTES = 120_000_000
JOURNAL_TABLES = (
    ('runs', 'SELECT * FROM runs WHERE id=?', lambda r: (r,)),
    ('run_accounts', 'SELECT * FROM run_accounts WHERE run_id=?', lambda r: (r,)),
    ('task_runs', 'SELECT * FROM task_runs ORDER BY id DESC LIMIT 400', lambda r: ()),
    ('reward_claims', 'SELECT * FROM reward_claims ORDER BY id DESC LIMIT 2000', lambda r: ()),
    ('instances', 'SELECT namespace,idx,selected,protected,present FROM instances', lambda r: ()),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def latest_run_id(db_path: Path) -> int | None:
    try:
        with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True) as db:
            row = db.execute('SELECT MAX(id) FROM runs').fetchone()
        return row[0]
    except sqlite3.Error:
        return None


def _journal(db_path: Path, run_id: int) -> tuple[dict, list]:
    notes = []
    result = {}
    try:
        db = sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True)
    except sqlite3.Error as exc:
        return result, [f'journal unreadable: {exc}']
    try:
        db.row_factory = sqlite3.Row
        for name, query, args in JOURNAL_TABLES:
            try:
                result[name] = [dict(r) for r in db.execute(query, args(run_id))]
            except sqlite3.Error as exc:
                notes.append(f'table {name} unreadable: {exc}')
    finally:
        db.close()
    return result, notes


def _run_log_lines(logs: Path, run_id: int) -> list[str]:
    marker = re.compile(rf'\brun={run_id}\b')
    lines = []
    for path in sorted(logs.glob('app.log*'), key=lambda p: p.name, reverse=True):
        try:
            with path.open(encoding='utf-8', errors='replace') as stream:
                lines.extend(line for line in stream if marker.search(line))
        except OSError:
            continue
    return lines


def _timing_table(accounts: list[dict]) -> list[dict]:
    table = []
    for account in accounts:
        timing = account.get('timing_seconds') or {}
        metrics = account.get('operation_metrics') or {}
        transport = account.get('transport_metrics') or {}
        wall = account.get('elapsed_seconds') or 0
        table.append(dict(
            index=account.get('index'), result=account.get('result'), worker=account.get('worker'),
            worker_started_at=account.get('worker_started_at'), worker_finished_at=account.get('worker_finished_at'),
            wall_seconds=wall, startup_seconds=timing.get('startup_and_initial_home'),
            flow_seconds=timing.get('flows'), cleanup_seconds=timing.get('cleanup'),
            exclusive_seconds_percent_of_wall={
                k: round(100 * v.get('exclusive_seconds', 0) / wall, 1) for k, v in metrics.items() if wall},
            operation_metrics=metrics, transport_commands=transport))
    return table


def _overlap(accounts: list[dict]) -> dict:
    """Actual two-worker overlap from recorded worker intervals, not from settings."""
    spans = []
    for a in accounts:
        try:
            spans.append((datetime.fromisoformat(a['worker_started_at']), datetime.fromisoformat(a['worker_finished_at']),
                          a.get('worker'), a.get('index')))
        except (KeyError, ValueError, TypeError):
            continue
    best = 0.0
    pairs = []
    for i, left in enumerate(spans):
        for right in spans[i + 1:]:
            seconds = (min(left[1], right[1]) - max(left[0], right[0])).total_seconds()
            if seconds > 0 and left[2] != right[2]:
                best = max(best, seconds)
                pairs.append((left[3], right[3], round(seconds, 1)))
    return dict(max_overlap_seconds=round(best, 1), overlapping_pairs=pairs, distinct_workers=len({s[2] for s in spans}))


def export_bundle(data_dir: Path, run_id: int | None = None, *, screenshots: bool = False,
                  output: Path | None = None, now=None) -> Path:
    data_dir = Path(data_dir)
    db_path = data_dir / 'config.sqlite3'
    missing = []
    if run_id is None:
        run_id = latest_run_id(db_path)
    if run_id is None:
        raise ValueError('Chưa có lượt chạy nào để xuất.')
    stamp = (now or datetime.now(UTC)).strftime('%Y%m%d-%H%M%S')
    output = output or data_dir / 'exports' / f'diagnostics-run{run_id}-{stamp}.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    version = load_version_info()
    report_path = None
    try:
        with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True) as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (f'automation-report:{run_id}',)).fetchone()
        report_path = Path(row[0]) if row else None
    except sqlite3.Error as exc:
        missing.append(f'settings unreadable: {exc}')
    entries: list[tuple[str, bytes]] = []
    accounts = []
    if report_path and report_path.is_file():
        root = report_path.parent
        for path in sorted(root.rglob('*.json')):
            if path.stat().st_size > MAX_FILE_BYTES:
                missing.append(f'{path.name} skipped: larger than {MAX_FILE_BYTES} bytes')
                continue
            entries.append((f'reports/{path.relative_to(root).as_posix()}', path.read_bytes()))
            if path.name == 'account-report.json':
                try:
                    accounts.append(json.loads(path.read_text(encoding='utf-8')))
                except ValueError:
                    missing.append(f'{path} is not valid JSON')
        if screenshots:
            used = 0
            for path in sorted(root.rglob('*.png')):
                size = path.stat().st_size
                if used + size > MAX_SCREENSHOT_BYTES:
                    missing.append('screenshots truncated at size limit; remaining PNGs stay on disk under ' + str(root))
                    break
                used += size
                entries.append((f'screenshots/{path.relative_to(root).as_posix()}', path.read_bytes()))
    else:
        missing.append(f'fleet report for run {run_id} not found (setting automation-report:{run_id}).')
    log_lines = _run_log_lines(data_dir / 'logs', run_id)
    if log_lines:
        entries.append((f'logs/app-run{run_id}.log', ''.join(log_lines).encode('utf-8')))
    else:
        missing.append(f'no app.log lines tagged run={run_id}.')
    pressure = data_dir / 'logs' / 'log-pressure-summary.txt'
    if pressure.is_file():
        entries.append(('logs/log-pressure-summary.txt', pressure.read_bytes()))
    journal, notes = _journal(db_path, run_id)
    missing.extend(notes)
    entries.append(('journal-snapshot.json', json.dumps(journal, indent=2, default=str).encode('utf-8')))
    entries.append(('timings.json', json.dumps(dict(accounts=_timing_table(accounts), worker_overlap=_overlap(accounts)),
                                               indent=2, default=str).encode('utf-8')))
    manifest = dict(created_at=(now or datetime.now(UTC)).isoformat(), run_id=run_id, version=version.as_report(),
                    read_only=True, screenshots_included=screenshots, missing_evidence=missing,
                    files=[dict(path=name, bytes=len(data), sha256=_sha(data)) for name, data in entries])
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('manifest.json', json.dumps(manifest, indent=2))
        for name, data in entries:
            bundle.writestr(name, data)
    return output
