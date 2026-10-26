"""One entry point for local development, shared by Claude hooks, skills and humans.

    python tools/dev.py setup            create/reuse .venv and install the project (+dev extras)
    python tools/dev.py test [paths...]  targeted tests (default: tests that match changed files)
    python tools/dev.py full             full suite, parallel when pytest-xdist is available
    python tools/dev.py lint             ruff check .
    python tools/dev.py check            pre-commit gate: lint + git diff --check + secret scan + guarded-file notice
    python tools/dev.py env              report what this environment can and cannot do (no secrets)
    python tools/dev.py hook post-edit|pre-bash   Claude Code hook adapters (JSON on stdin)

Nothing here touches LDPlayer, journals, logs or the Desktop. It only reads the repo and runs tools.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv'
GUARDED = (  # edits here need an explicit safety re-read (see CLAUDE.md)
    'src/top_heroes_auto/ldplayer/', 'src/top_heroes_auto/automation/guard.py', 'src/top_heroes_auto/storage/store.py',
    'src/top_heroes_auto/app/service.py', 'src/top_heroes_auto/app/automation_ownership.py',
    'TopHeroesAutoManager.spec', '.github/workflows/windows.yml', 'tools/write_build_info.py',
)
SENSITIVE_PATH = re.compile(r'(^|/)(logs|diagnostics|screenshots|exports)/|\.sqlite3|\.env$|id_rsa|\.pem$|\.pfx$', re.I)
SECRET = re.compile(
    r'(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|'
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[=:]\s*["\'][^"\'\s]{8,}["\']))')


def venv_python() -> str:
    exe = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return str(exe) if exe.is_file() else sys.executable


def run(args, **kw) -> int:
    return subprocess.run(args, cwd=ROOT, **kw).returncode


def have(module: str) -> bool:
    return subprocess.run([venv_python(), '-c', f'import {module}'], cwd=ROOT, capture_output=True).returncode == 0


def git(*args) -> str:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout


def setup() -> int:
    if not VENV.exists():
        print(f'creating {VENV}')
        if run([sys.executable, '-m', 'venv', str(VENV)]):
            return 1
    return run([venv_python(), '-m', 'pip', 'install', '-q', '-e', '.[dev]'])


def pytest_args(paths, parallel) -> list:
    env_args = [venv_python(), '-m', 'pytest', '-q', '-p', 'no:cacheprovider']
    if parallel and have('xdist'):
        env_args += ['-n', str(min(4, os.cpu_count() or 1))]
    return env_args + list(paths)


def test(paths) -> int:
    if not paths:
        changed = [p for p in git('status', '--porcelain').splitlines()]
        stems = {Path(line[3:]).stem for line in changed if line[3:].startswith('src/') and line.endswith('.py')}
        paths = sorted({str(t.relative_to(ROOT)) for t in (ROOT / 'tests').glob('test_*.py')
                        if any(stem in t.read_text(encoding='utf-8', errors='ignore') for stem in stems)}) if stems else []
        if not paths:
            print('No changed source with matching tests; pass test paths explicitly or run `full`.')
            return 0
        print('targeted:', ' '.join(paths))
    env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
    return run(pytest_args(paths, parallel=len(paths) > 3), env=env)


def full() -> int:
    return run(pytest_args([], parallel=True), env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})


def lint(files=()) -> int:
    return run([venv_python(), '-m', 'ruff', 'check', *files] if files else [venv_python(), '-m', 'ruff', 'check', '.'])


def staged_or_changed() -> list:
    names = git('diff', '--cached', '--name-only').split() or git('diff', '--name-only').split()
    return [n for n in names if n]


def scan() -> list:
    problems = []
    diff = git('diff', '--cached', '-U0') or git('diff', '-U0')
    for line in diff.splitlines():
        if line.startswith('+') and not line.startswith('+++') and SECRET.search(line):
            problems.append('possible credential in added line: ' + SECRET.sub('<redacted>', line)[:120])
    for name in staged_or_changed():
        if SENSITIVE_PATH.search(name.replace('\\', '/')):
            problems.append(f'private/runtime file staged: {name}')
    return problems


def check() -> int:
    status = 0
    if lint():
        status = 1
    if run(['git', 'diff', '--check']) or run(['git', 'diff', '--cached', '--check']):
        print('git diff --check: whitespace errors')
        status = 1
    problems = scan()
    for item in problems:
        print('BLOCKED:', item)
    status = 1 if problems else status
    touched = [n for n in staged_or_changed() if n.replace('\\', '/').startswith(GUARDED)]
    if touched:
        print('NOTICE: safety-critical files changed (Protected/identity/journal/lifecycle/release):', ', '.join(touched))
        print('        Re-read docs/SAFETY.md and confirm tests cover Protected isolation and journal locks.')
    return status


def env_report() -> int:
    def version(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[0]
        except (OSError, IndexError, subprocess.SubprocessError):
            return 'missing'
    windows = {p: Path(p).exists() for p in (r'D:\Projects\thangnd-top-heroes', r'C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\logs',
                                              r'C:\Users\ADMIN\Desktop\app', r'D:\LDPlayer\LDPlayer9')}
    gh_login = subprocess.run(['gh', 'api', 'user', '--jq', '.login'], capture_output=True, text=True).stdout.strip() if shutil.which('gh') else ''
    info = dict(os=sys.platform, python=version([venv_python(), '--version']), pytest=version([venv_python(), '-m', 'pytest', '--version']),
                ruff=version([venv_python(), '-m', 'ruff', '--version']), pyinstaller=version([venv_python(), '-m', 'PyInstaller', '--version']),
                gh='authenticated as ' + gh_login if gh_login else ('installed, not authenticated' if shutil.which('gh') else 'missing'),
                can_build_windows_exe=os.name == 'nt', windows_paths=windows, venv=str(VENV) if VENV.exists() else 'not created',
                branch=git('branch', '--show-current').strip(), head=git('rev-parse', '--short', 'HEAD').strip(),
                dirty=bool(git('status', '--porcelain').strip()))
    print(json.dumps(info, indent=2))
    return 0


def hook(kind) -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    tool_input = payload.get('tool_input') or {}
    if kind == 'post-edit':
        path = str(tool_input.get('file_path', '')).replace('\\', '/')
        if not path.endswith('.py'):
            return 0
        rel = path.split('/thangnd-top-heroes/')[-1] if '/thangnd-top-heroes/' in path else path
        out = subprocess.run([venv_python(), '-m', 'ruff', 'check', path], cwd=ROOT, capture_output=True, text=True)
        messages = []
        if out.returncode:
            messages.append('ruff found problems in the edited file:\n' + out.stdout[-1500:])
        if rel.startswith(GUARDED):
            messages.append(f'{rel} is safety-critical (Protected isolation / identity / journal / lifecycle / release). '
                            'Confirm a regression test covers the change.')
        if messages:
            print('\n'.join(messages), file=sys.stderr)
            return 2
        return 0
    if kind == 'pre-bash':
        command = str(tool_input.get('command', ''))
        if not re.search(r'\bgit\s+commit\b', command):
            return 0
        problems = scan()
        if run(['git', 'diff', '--cached', '--check'], capture_output=True):
            problems.append('git diff --check reports whitespace errors in staged changes')
        if problems:
            print('Commit blocked by tools/dev.py:\n- ' + '\n- '.join(problems), file=sys.stderr)
            return 2
        return 0
    return 0


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    table = dict(setup=lambda: setup(), test=lambda: test(rest), full=lambda: full(), lint=lambda: lint(), check=lambda: check(),
                 env=lambda: env_report(), hook=lambda: hook(rest[0] if rest else ''))
    if command not in table:
        print(__doc__)
        return 2
    return table[command]()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
