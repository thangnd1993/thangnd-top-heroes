"""VIP daily period, anchored to the observed game countdown (02:00 UTC)."""
from datetime import datetime, timedelta, timezone

VIP_REWARDS = frozenset({'vip-upper-gift', 'vip-daily'})


def period_start(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('VIP period requires an aware UTC timestamp.')
    now = now.astimezone(timezone.utc)
    start = now.replace(hour=2, minute=0, second=0, microsecond=0)
    return start if now >= start else start - timedelta(days=1)


def cycle_key(reward_id, now=None):
    if reward_id not in VIP_REWARDS:
        raise ValueError('Period policy is only qualified for fixed VIP rewards.')
    return f'vip:{reward_id}:{period_start(now).isoformat()}'


def current_attempts(rows, reward_id, now=None):
    start = period_start(now)
    # Unknown legacy dates remain locked. No historical row is deleted/relabelled.
    locked = []
    for row in rows:
        if row['reward_id'] != reward_id or row['status'] not in {'RESERVED', 'VERIFIED'}:
            continue
        try:
            reserved = datetime.fromisoformat(row['reserved_at'])
            current = reserved.tzinfo is None or reserved >= start
        except (KeyError, TypeError, ValueError):
            current = True
        if current:
            locked.append(row)
    return locked
