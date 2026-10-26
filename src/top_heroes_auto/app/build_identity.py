"""Bounded local build provenance; never enumerate unrelated configuration."""
import hashlib
import json
import sys
from pathlib import Path

from top_heroes_auto.app.version_info import load_version_info
from top_heroes_auto.vision.resources import template_folder


def build_identity():
    exe = Path(sys.executable)
    result = dict(executable=str(exe), standalone=bool(getattr(sys, 'frozen', False)))
    if result['standalone']:
        with exe.open('rb') as stream:
            result['exe_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata = template_folder().parent / 'build-info.json'
    if metadata.is_file():
        raw = json.loads(metadata.read_text(encoding='utf-8-sig'))
        result['build'] = {k:raw.get(k) for k in ('commit','ci_run','repository')}
    result['version_info'] = load_version_info().as_report()
    return result
