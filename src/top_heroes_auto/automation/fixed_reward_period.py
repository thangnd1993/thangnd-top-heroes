"""Only observed reset policies; no inferred VIP policy for unrelated rewards."""
from datetime import datetime, timedelta, timezone

from top_heroes_auto.vision.fixed_rewards import REWARDS


def period_start(reward, now=None):
    if reward not in REWARDS:
        raise ValueError('Unsupported fixed reward period.')
    if reward != 'shop-daily-gift':
        return None
    # Clean daily-offer frame written 2026-09-23 01:05:26 UTC: 00:54:33 left,
    # giving 01:59:59 UTC (one second capture/rounding uncertainty).
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Reward period requires an aware timestamp.')
    now = now.astimezone(timezone.utc)
    start = now.replace(hour=2, minute=0, second=0, microsecond=0)
    return start if now >= start else start-timedelta(days=1)


def cycle_key(reward, now=None):
    start = period_start(reward, now)
    return f'fixed:{reward}:{start.isoformat() if start else "initial-period-unqualified"}'


def current_attempts(rows, reward, now=None):
    start = period_start(reward, now)
    result = []
    for row in rows:
        if row['reward_id'] != reward:
            continue
        try:
            reserved = datetime.fromisoformat(row['reserved_at'])
            locked = start is None or reserved.tzinfo is None or reserved >= start
        except (KeyError, ValueError, TypeError):
            locked = True
        if locked:
            result.append(row)
    return result
