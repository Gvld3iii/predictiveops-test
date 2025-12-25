import threading
import time

_lock = threading.Lock()
_seq = 0
_events = []  # list of dicts, each dict should include "seq"


def add_event(evt: dict) -> int:
    global _seq, _events
    with _lock:
        _seq += 1
        evt = dict(evt)
        evt["seq"] = _seq
        # Keep a timestamp if caller didn’t include one
        evt.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        _events.append(evt)

        # cap memory so it doesn’t grow forever
        if len(_events) > 400:
            _events = _events[-400:]
        return _seq


def get_events_since(since: int):
    with _lock:
        new_events = [e for e in _events if int(e.get("seq", 0)) > int(since)]
        latest = _seq
        return new_events, latest
