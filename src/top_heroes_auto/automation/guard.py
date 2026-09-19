from dataclasses import dataclass

from top_heroes_auto.ldplayer.client import Instance
from top_heroes_auto.storage.store import Store


class SafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunSnapshot:
    namespace: str
    members: tuple[tuple[int, str], ...]
    immutable: bool = False


def create_snapshot(store: Store, namespace: str, instances: tuple[Instance, ...]) -> RunSnapshot:
    members = []
    for instance in instances:
        metadata = store.metadata(namespace, instance.index)
        if metadata.selected and not metadata.protected:
            members.append((instance.index, instance.name))
    return RunSnapshot(namespace, tuple(members))


def require_selected(
    store: Store, snapshot: RunSnapshot, current: tuple[Instance, ...], index: int
) -> Instance:
    if type(index) is not int or index < 0:
        raise SafetyError("Index không hợp lệ; không fallback về index 0.")
    matches = [i for i in current if i.index == index]
    if len(matches) != 1 or (index, matches[0].name) not in snapshot.members:
        raise SafetyError("Giả lập không tồn tại, đổi tên hoặc không nằm trong hàng đợi hiện tại.")
    metadata = store.metadata(snapshot.namespace, index)
    if not metadata.selected or metadata.protected:
        raise SafetyError("Đã chặn: giả lập chưa được chọn hoặc đang được bảo vệ.")
    return matches[0]


def require_run_member(
    store: Store, snapshot: RunSnapshot, current: tuple[Instance, ...], index: int
) -> Instance:
    """Validate an immutable queued member without re-reading its checkbox.

    Selection is intentionally captured at run creation. Protection, presence,
    and identity are always live safety checks and may still revoke execution.
    """
    if type(index) is not int or index < 0:
        raise SafetyError("Index không hợp lệ; không fallback về index 0.")
    matches = [item for item in current if item.index == index]
    if len(matches) != 1 or (index, matches[0].name) not in snapshot.members:
        raise SafetyError("Giả lập không tồn tại, đổi tên hoặc không nằm trong hàng đợi hiện tại.")
    if store.metadata(snapshot.namespace, index).protected:
        raise SafetyError("Đã chặn: giả lập đang được bảo vệ.")
    return matches[0]
