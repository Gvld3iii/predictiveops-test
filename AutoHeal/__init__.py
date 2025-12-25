import json
import time
import logging
import azure.functions as func

try:
    # your in-memory event bus for RiskStream
    from shared_state import add_event
except Exception:
    add_event = None


def cors_headers():
    return {
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("[AutoHeal] Simulator triggered")

    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=cors_headers())

    try:
        body = req.get_json()
    except Exception:
        body = {}

    resource_id = str(body.get("resourceId", "")).strip() or "unknown"
    risk = float(body.get("risk", 0) or 0)
    cloud = str(body.get("cloud", "azure"))

    # simulate doing work (restart / reroute / runbook)
    time.sleep(0.35)

    # Push a “recovery” event into the stream so the UI needle drops
    if add_event is not None:
        add_event({
            "resourceId": resource_id,
            "latency": 120,
            "errorRate": 0.2,
            "nxdomainAnomaly": False,
            "risk": 0.10,
            "autoHealTriggered": True,
            "cosmosWrite": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cloud": cloud
        })

    result = {
        "ok": True,
        "action": "restart_appservice",
        "resourceId": resource_id,
        "risk": risk,
        "status": "completed",
        "message": "Auto-heal simulated: restart completed"
    }

    return func.HttpResponse(
        body=json.dumps(result),
        status_code=200,
        mimetype="application/json",
        headers=cors_headers(),
    )
