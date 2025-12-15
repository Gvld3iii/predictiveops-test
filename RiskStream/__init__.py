import json
import azure.functions as func

from shared_state import get_events_since

def main(req: func.HttpRequest) -> func.HttpResponse:
    # Polling-style "stream"
    since_raw = req.params.get("since", "0")
    try:
        since = int(since_raw)
    except ValueError:
        since = 0

    events, latest = get_events_since(since)

    payload = {
        "events": events,
        "latestSeq": latest
    }

    return func.HttpResponse(
        body=json.dumps(payload),
        status_code=200,
        mimetype="application/json",
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*"
        }
    )
