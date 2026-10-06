from dataclasses import dataclass

from top_heroes_auto.ldplayer.client import Instance
from top_heroes_auto.storage.store import Store


class SafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunSnapshot:
    namespace: str
    members: tuple[tuple[int, str], ...]  # labels for UI only
    immutable: bool = False
    identities: tuple[tuple[int, str], ...] = ()


def bound_snapshot(store, namespace, members, immutable=False):
    if len({index for index, _ in members}) != len(members):
        raise SafetyError('Ambiguous snapshot indices.')
    identities = tuple((index, store.require_identity(namespace, index)) for index, _ in members)
    return RunSnapshot(namespace, members, immutable, identities)


def create_snapshot(store: Store, namespace: str, instances: tuple[Instance, ...]) -> RunSnapshot:
    members = tuple((i.index, i.name) for i in instances
                    if store.metadata(namespace, i.index).selected
                    and not store.metadata(namespace, i.index).protected)
    return bound_snapshot(store, namespace, members)


def require_run_member(store, snapshot, current, index):
    if type(index) is not int or index < 0:
        raise SafetyError('Invalid index; no fallback.')
    matches = [i for i in current if i.index == index]
    expected = [sid for idx, sid in snapshot.identities if idx == index]
    if (len(matches) != 1 or sum(idx == index for idx, _ in snapshot.members) != 1
            or len(expected) != 1 or not expected[0]):
        raise SafetyError('IDENTITY_UNVERIFIED: missing or ambiguous stable snapshot binding.')
    try:
        store.require_identity(snapshot.namespace, index, expected[0])
    except ValueError as exc:
        raise SafetyError(str(exc)) from exc
    if matches[0].stable_id != expected[0]:
        raise SafetyError('IDENTITY_CHANGED: current backing disk differs from snapshot.')
    if store.metadata(snapshot.namespace, index).protected:
        raise SafetyError('Protected instance; execution blocked.')
    return matches[0]


def require_selected(store, snapshot, current, index):
    instance = require_run_member(store, snapshot, current, index)
    if not store.metadata(snapshot.namespace, index).selected:
        raise SafetyError('Instance is not selected.')
    return instance
