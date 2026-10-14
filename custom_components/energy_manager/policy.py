"""Pure functions used by the control engine; independently testable."""
from __future__ import annotations

from datetime import datetime, time
import math


def within(now: datetime, start: str, end: str) -> bool:
    """Check local half-open time window, including midnight wrap."""
    a = time.fromisoformat(start)
    b = time.fromisoformat(end)
    t = now.time().replace(tzinfo=None)
    return a <= t < b if a <= b else t >= a or t < b


def after(now: datetime, threshold: str) -> bool:
    return now.time().replace(tzinfo=None) >= time.fromisoformat(threshold)


def net_surplus(pcc_w: float, battery_w: float) -> float:
    """Positive PCC=export; positive battery=charge, negative=discharge.

    Charging energy is reserved to the house battery. Discharge is penalized
    so managed loads will not be sustained using battery energy.
    """
    return pcc_w + min(battery_w, 0.0)


def recompute_capacity(pcc_w: float, battery_w: float, managed_active_w: float) -> float:
    """Reclaimable solar capacity BEFORE controllable running loads.

    Add loads back exactly once for allocation, avoiding the usual trap of
    switching them off as soon as the measured surplus falls on activation.
    """
    return net_surplus(pcc_w, battery_w) + managed_active_w


def current_target(available_w: float, watts_per_amp: float, min_amp: int, max_amp: int, reserve_w: float) -> int:
    """Return 0 when even minimum EV charge current cannot be solar supplied."""
    if watts_per_amp <= 0 or not math.isfinite(available_w):
        return 0
    permitted = math.floor(max(0, available_w - reserve_w) / watts_per_amp)
    return min(max_amp, permitted) if permitted >= min_amp else 0


def normalized_loads(loads: list[dict]) -> list[dict]:
    return sorted(loads, key=lambda x: (int(x.get("priority", 999)), str(x["id"])))
