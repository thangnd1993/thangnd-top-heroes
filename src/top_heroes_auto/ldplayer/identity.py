"""Read-only backing-file identity. Display labels and config contents are excluded."""
import hashlib
from pathlib import Path


def disk_identity(console: Path, index: int) -> str:
    if type(index) is not int or index < 0:
        raise ValueError('IDENTITY_UNVERIFIED: invalid index.')
    path = console.parent / 'vms' / f'leidian{index}' / 'data.vmdk'
    first = path.stat()
    birth = getattr(first, 'st_birthtime_ns', None)
    second = path.stat()
    def key(stat):
        return stat.st_dev, stat.st_ino, getattr(stat, 'st_birthtime_ns', None)
    if birth is None or not first.st_ino or key(first) != key(second):
        raise ValueError('IDENTITY_UNVERIFIED: stable backing-file evidence unavailable.')
    # Preserve the historical project fingerprint; never invent/write a device ID.
    return hashlib.sha256(f'{path.resolve()}:{first.st_dev}:{first.st_ino}:{birth}'.encode()).hexdigest()


def runtime_key(value):
    """Project evidence tuples: index, display label, optional serial and boot."""
    if len(value) not in (2, 3, 4):
        raise ValueError('Invalid indexed runtime evidence.')
    return (value[0], *value[2:])
