import datetime
import threading
from collections import deque

_MAX_EVENTS = 500

_lock = threading.Lock()
_events: deque[dict] = deque(maxlen=_MAX_EVENTS)
_total_appended = 0


def log_event(kind: str, text: str) -> None:
    """Record an event.

    Args:
        kind: One of "status", "user", or "nova" - used by the viewer to
            color-code and format the line.
        text: The event text (a status description, or what was said).
    """
    global _total_appended

    if not text:
        return

    with _lock:
        _events.append({
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "kind": kind,
            "text": text,
        })
        _total_appended += 1


def get_new_events(since_total: int) -> tuple[list[dict], int]:
    """Return events appended since `since_total`, plus the new total to pass next time.

    Safe even if the caller is far behind and some of what they missed has
    since been evicted by the rolling cap - in that case they just get
    everything currently held, starting from the oldest available.
    """
    with _lock:
        total = _total_appended
        dropped = total - len(_events)
        start = max(0, since_total - dropped)
        return list(_events)[start:], total
