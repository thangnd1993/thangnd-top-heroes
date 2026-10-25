import json
import subprocess
import sys
from pathlib import Path

import pytest

from top_heroes_auto import __version__
from top_heroes_auto.app.version_info import UNKNOWN, load_version_info

ROOT = Path(__file__).resolve().parents[1]
SHA = 'c2dac26e20db28f6e3e635960b2c0f34f31ffccb'


def write(tmp_path, **fields):
    path = tmp_path / 'build-info.json'
    path.write_text(json.dumps(fields), encoding='utf-8')
    return path


def test_valid_metadata_is_displayed_exactly(tmp_path):
    info = load_version_info(write(tmp_path, version='1.2.3', commit=SHA, release_date='2026-10-25',
                                   channel='ci-release', ci_run='40088053262'))
    assert (info.version, info.commit, info.release_date, info.channel) == ('1.2.3', SHA, '2026-10-25', 'CI Release')
    assert info.summary == 'V1.2.3 · c2dac26e · 2026-10-25 · CI Release'


def test_missing_file_is_explicit_development_unknown(tmp_path):
    info = load_version_info(tmp_path / 'absent.json')
    assert info.commit == info.release_date == info.ci_run == UNKNOWN
    assert info.channel == 'Development' and info.version == __version__
    assert info.short_commit == UNKNOWN


@pytest.mark.parametrize('fields', [
    dict(commit='not-a-sha', release_date='25/10/2026', ci_run='abc'),
    dict(commit=None, release_date=20261025, ci_run=True),
    dict(commit='../../etc', release_date='2026-10-25\nX', ci_run='1 2'),
])
def test_malformed_fields_are_never_invented_or_echoed(tmp_path, fields):
    info = load_version_info(write(tmp_path, channel='ci-release', **fields))
    assert info.commit == info.release_date == info.ci_run == UNKNOWN


def test_malformed_json_and_old_provenance_without_date(tmp_path):
    bad = tmp_path / 'build-info.json'
    bad.write_text('{broken', encoding='utf-8')
    assert load_version_info(bad).commit == UNKNOWN
    # Provenance written by earlier CI builds has no date/channel: keep commit, mark the rest unknown.
    info = load_version_info(write(tmp_path, commit=SHA, ci_run='40062497019', repository='x/y'))
    assert info.commit == SHA and info.release_date == UNKNOWN and info.channel == UNKNOWN


def test_write_build_info_tool_roundtrip(tmp_path):
    out = tmp_path / 'build-info.json'
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'write_build_info.py'), '--commit', SHA, '--ci-run', '7',
                    '--repository', 'o/r', '--release-date', '2026-10-25', '--output', str(out)], check=True)
    info = load_version_info(out)
    assert info.commit == SHA and info.release_date == '2026-10-25' and info.channel == 'CI Release'
    assert info.version == __version__


@pytest.mark.parametrize('args', [['--commit', 'abc'], ['--commit', SHA, '--release-date', '2026-13-45']])
def test_write_build_info_tool_rejects_bad_input(tmp_path, args):
    result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'write_build_info.py'), '--ci-run', '7',
                             '--repository', 'o/r', '--output', str(tmp_path / 'x.json'), *args],
                            capture_output=True)
    assert result.returncode != 0 and not (tmp_path / 'x.json').exists()


def test_version_file_cli_runs_without_qt(tmp_path):
    out = tmp_path / 'v.json'
    subprocess.run([sys.executable, '-c', 'import sys;from top_heroes_auto.app.main import main;sys.exit(main(sys.argv[1:]))',
                    '--version-file', str(out)], check=True, cwd=ROOT, env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'src')})
    assert set(json.loads(out.read_text())) == {'version', 'commit', 'release_date', 'channel', 'ci_run'}
