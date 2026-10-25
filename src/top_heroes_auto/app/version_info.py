"""Build-generated version metadata. Nothing here is hardcoded per release:
the CI step writes assets/build-info.json and this module only validates and
presents it. Missing or malformed fields are shown as unknown, never invented."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from top_heroes_auto import __version__
from top_heroes_auto.vision.resources import template_folder

UNKNOWN = 'không rõ'
APP_NAME = 'Top Heroes Auto Manager'
_COMMIT = re.compile(r'[0-9a-f]{7,40}')
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
_CI_RUN = re.compile(r'\d{1,20}')
CHANNELS = {'ci-release': 'CI Release', 'development': 'Development'}


@dataclass(frozen=True)
class VersionInfo:
    version: str
    commit: str
    release_date: str
    channel: str
    ci_run: str

    @property
    def short_commit(self) -> str:
        return self.commit[:8] if self.commit != UNKNOWN else UNKNOWN

    @property
    def summary(self) -> str:
        return f'V{self.version} · {self.short_commit} · {self.release_date} · {self.channel}'

    def as_report(self) -> dict:
        return dict(version=self.version, commit=self.commit, release_date=self.release_date,
                    channel=self.channel, ci_run=self.ci_run)


def _field(raw: dict, key: str, pattern: re.Pattern, lower: bool = False) -> str:
    value = raw.get(key)
    if not isinstance(value, str | int) or isinstance(value, bool):
        return UNKNOWN
    text = str(value).strip()
    text = text.lower() if lower else text
    return text if pattern.fullmatch(text) else UNKNOWN


def metadata_path() -> Path:
    return template_folder().parent / 'build-info.json'


def load_version_info(path: Path | None = None) -> VersionInfo:
    path = metadata_path() if path is None else path
    raw: dict = {}
    try:
        loaded = json.loads(path.read_text(encoding='utf-8-sig'))
        raw = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        raw = {}
    version = raw.get('version')
    version = version.strip() if isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+[\w.+-]*', version.strip()) else __version__
    channel = CHANNELS.get(str(raw.get('channel', '')).strip().lower(), 'Development' if not raw else UNKNOWN)
    return VersionInfo(version, _field(raw, 'commit', _COMMIT, lower=True),
                       _field(raw, 'release_date', _DATE), channel, _field(raw, 'ci_run', _CI_RUN))
