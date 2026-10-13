"""Explicitly authorized single-field remediation; never restore or rename config."""
import ctypes
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from top_heroes_auto.app.automation_ownership import mutation_ownership
from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity

FIELD = 'basicSettings.adbDebug'


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate configuration key; no write.')
        result[key] = value
    return result


def patch_field(original):
    """Preserve every original byte outside the one value or inserted member."""
    text = original.decode('utf-8-sig')
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    before = decoder.decode(text)
    if not isinstance(before, dict):
        raise ValueError('Configuration must be an object.')
    pos = text.index('{') + 1
    insertion = pos
    span = None
    while True:
        while text[pos].isspace():
            pos += 1
        if text[pos] == '}':
            break
        key, end = decoder.raw_decode(text, pos)
        pos = end
        while text[pos].isspace():
            pos += 1
        if text[pos] != ':':
            raise ValueError('Invalid member separator.')
        pos += 1
        while text[pos].isspace():
            pos += 1
        _, end = decoder.raw_decode(text, pos)
        if key == FIELD:
            span = pos, end
        pos = end
        while text[pos].isspace():
            pos += 1
        if text[pos] == '}':
            break
        if text[pos] != ',':
            raise ValueError('Invalid member separator.')
        pos += 1
    if span:
        changed = text[:span[0]] + '1' + text[span[1]:]
    else:
        changed = text[:insertion] + f'"{FIELD}":1' + (',' if before else '') + text[insertion:]
    after = decoder.decode(changed)
    expected = dict(before)
    expected[FIELD] = 1
    if after != expected:
        raise ValueError('Unexpected configuration change.')
    bom = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    return bom + changed.encode('utf-8'), dict(present=FIELD in before, value=before.get(FIELD))


@contextmanager
def writer_lock(path):
    """Windows kernel sharing denies any concurrent writer or file replacement."""
    if os.name != 'nt':
        raise ValueError('Windows exclusive writer required.')
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0xC0000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    with os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY), 'r+b') as stream:
        yield stream


def enable(manager, index, stable_id, backup, *, authorized_indexes):
    if index not in authorized_indexes:
        raise ValueError('No explicit field-change authorization for this index.')
    path = manager.ld.installation.console.parent / 'vms' / 'config' / f'leidian{index}.config'
    if path.resolve() != path.absolute():
        raise ValueError('Config association is not an exact ordinary path.')
    backup = Path(backup)
    if backup.exists() or backup.resolve() == path.resolve():
        raise ValueError('A new separate backup path is required.')

    def guard():
        live = manager.query(index)
        if manager.store.metadata(manager.namespace, index).protected or live.running:
            raise ValueError('Config target must be stopped and non-Protected.')
        if persistent_identity(manager, index) != stable_id or live.stable_id != stable_id:
            raise ValueError('Config backing-file association changed.')

    with mutation_ownership(manager):
        guard()
        with writer_lock(path) as stream:
            original = stream.read()
            changed, old = patch_field(original)
            guard()
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open('xb') as saved:
                saved.write(original)
                saved.flush()
                os.fsync(saved.fileno())
            guard()
            stream.seek(0)
            if stream.read() != original:
                raise ValueError('Config changed before write; no overwrite.')
            stream.seek(0)
            stream.write(changed)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            if stream.read() != changed:
                raise ValueError('Config verification failed; preserve backup, never restore names.')
    return dict(index=index, persistent_identity=stable_id, config=str(path), backup=str(backup),
                field=FIELD, original=old, new=1, other_values_unchanged=True,
                before_sha256=hashlib.sha256(original).hexdigest(),
                after_sha256=hashlib.sha256(changed).hexdigest())
