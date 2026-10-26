"""Write assets/build-info.json during CI packaging (run from the repository root)."""
import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from top_heroes_auto import __version__  # noqa: E402


def build_info(commit: str, ci_run: str, repository: str, release_date: str | None = None,
               channel: str = 'ci-release') -> dict:
    if not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
        raise ValueError('commit must be the full 40-character source revision')
    if not re.fullmatch(r'\d+', ci_run):
        raise ValueError('ci_run must be numeric')
    date = release_date or datetime.now(UTC).strftime('%Y-%m-%d')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('release_date must be YYYY-MM-DD')
    datetime.fromisoformat(date)  # rejects impossible dates such as 2026-13-45
    return dict(version=__version__, commit=commit.lower(), ci_run=ci_run, repository=repository,
                release_date=date, release_timezone='UTC', channel=channel)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    parser.add_argument('--ci-run', required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--release-date')
    parser.add_argument('--output', type=Path, default=Path('assets/build-info.json'))
    options = parser.parse_args(argv)
    info = build_info(options.commit, options.ci_run, options.repository, options.release_date)
    options.output.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    print(f"build-info: {info['version']} {info['commit'][:8]} {info['release_date']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
