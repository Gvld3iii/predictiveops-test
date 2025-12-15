import json
import time
import azure.functions as func

def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "no-store",
    }

def main(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=cors_headers())

    try:
        body = req.get_json()
    except Exception:
        body = {}

    # simulate a real runbook doing work
    time.sleep(0.6)

    resp = {
        "ok": True,
        "action": body.get("action", "restart_appservice"),
        "resourceId": body.get("resourceId", "—"),
        "healed": True,
    }

    return func.HttpResponse(
        json.dumps(resp),
        status_code=200,
        mimetype="application/json",
        headers=cors_headers(),
    )
