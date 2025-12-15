# shared_state.py
import threading
import copy

_lock = threading.Lock()
_seq = 0
_events = []  # list of dicts with "seq"

def push_event(evt: dict) -> int:
    """Append an event and return its sequence number."""
    global _seq
    with _lock:
        _seq += 1
        e = dict(evt or {})
        e["seq"] = _seq
        _events.append(e)
        # cap memory
        if len(_events) > 500:
            del _events[:-500]
        return _seq

def get_events_since(since: int):
    """Return (events_after_since, latest_seq)."""
    with _lock:
        since = int(since or 0)
        new_events = [e for e in _events if int(e.get("seq", 0)) > since]
        return copy.deepcopy(new_events), _seq
