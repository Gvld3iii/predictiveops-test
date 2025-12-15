import os
import json
import re
import uuid
import datetime
import logging
import time

import azure.functions as func
from shared_state import push_event

try:
    import requests
except Exception:
    requests = None

try:
    from azure.cosmos import CosmosClient
except Exception:
    CosmosClient = None


# =========================
# Env config
# =========================
COSMOS_URL = os.getenv("COSMOS_URL", "").strip()
COSMOS_KEY = os.getenv("COSMOS_KEY", "").strip()
COSMOS_DB = os.getenv("COSMOS_DB", "predictiveops").strip()
COSMOS_CONTAINER = os.getenv("COSMOS_CONTAINER", "riskEvents").strip()

RISK_THRESHOLD = float(os.getenv("RISK_THRESHOLD", "0.75"))
WEBHOOK_RESTART = os.getenv("WEBHOOK_RESTART", "").strip()
VERBOSE = os.getenv("VERBOSE", "false").lower() in ("1", "true", "yes")

_cosmos_container = None


# =========================
# Helpers
# =========================
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "no-store",
    }

def now_utc_iso() -> str:
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def safe_cosmos_id(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    s = s.strip("._-")
    return s or "resource"

def compute_risk(latency_ms: float, error_rate_pct: float, nxdomain_anomaly: bool) -> float:
    risk = 0.0
    if latency_ms >= 200:
        risk += 0.45
    if error_rate_pct >= 1.0:
        risk += 0.45
    if nxdomain_anomaly:
        risk += 0.15
    return clamp(round(risk, 2), 0.0, 1.0)

def get_cosmos_container():
    global _cosmos_container
    if _cosmos_container is not None:
        return _cosmos_container

    if not COSMOS_URL or not COSMOS_KEY:
        logging.warning("[RiskEngine] Cosmos not configured (COSMOS_URL/COSMOS_KEY missing).")
        return None

    if CosmosClient is None:
        logging.warning("[RiskEngine] azure-cosmos not installed; skipping Cosmos.")
        return None

    logging.info("[RiskEngine] Initializing Cosmos client...")
    client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY)

    db = client.get_database_client(COSMOS_DB)
    container = db.get_container_client(COSMOS_CONTAINER)

    _cosmos_container = container
    logging.info(f"[RiskEngine] Connected to Cosmos DB '{COSMOS_DB}', container '{COSMOS_CONTAINER}'")
    return _cosmos_container

def write_risk_event(container, item: dict) -> bool:
    if not container:
        return False
    try:
        # IMPORTANT: do NOT pass partition_key kwarg (caused your error).
        # If container partition key is /resourceId, Cosmos uses item["resourceId"].
        container.create_item(body=item)
        return True
    except Exception as e:
        logging.exception(f"[RiskEngine] Failed to write item to Cosmos: {e}")
        return False

def call_restart_webhook(resource_id: str, risk: float, telemetry: dict) -> bool:
    if not WEBHOOK_RESTART:
        logging.warning("[RiskEngine] WEBHOOK_RESTART not set; skipping auto-heal.")
        return False

    if requests is None:
        logging.warning("[RiskEngine] requests not installed; cannot call webhook.")
        return False

    payload = {
        "action": "restart_appservice",
        "resourceId": resource_id,
        "risk": risk,
        "timestamp": now_utc_iso(),
        "telemetry": telemetry,
    }

    try:
        resp = requests.post(WEBHOOK_RESTART, json=payload, timeout=10)
        if 200 <= resp.status_code < 300:
            logging.info(f"[RiskEngine] Restart webhook OK ({resp.status_code}) for {resource_id}")
            return True

        logging.warning(f"[RiskEngine] Restart webhook failed ({resp.status_code}): {resp.text[:400]}")
        return False
    except Exception as e:
        logging.exception(f"[RiskEngine] Failed to call restart webhook: {e}")
        return False


# =========================
# Azure Function entrypoint
# =========================
def main(req: func.HttpRequest) -> func.HttpResponse:
    # CORS preflight
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=cors_headers())

    logging.info("PredictiveOps Azure RiskEngine triggered")

    try:
        body = req.get_json()
    except Exception:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
            headers=cors_headers(),
        )

    # Support: {detail:{...}} OR flat
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        body = body["detail"]

    resource_id = str(body.get("resourceId", "")).strip()
    if not resource_id:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "resourceId is required"}),
            status_code=400,
            mimetype="application/json",
            headers=cors_headers(),
        )

    latency = float(body.get("latency", 0) or 0)
    error_rate = float(body.get("errorRate", 0) or 0)
    nxdomain = bool(body.get("nxdomainAnomaly", False))

    risk = compute_risk(latency, error_rate, nxdomain)

    telemetry = {
        "latency": latency,
        "errorRate": error_rate,
        "nxdomainAnomaly": nxdomain,
    }

    safe_resource = safe_cosmos_id(resource_id)
    event_id = f"{safe_resource}-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    ts = now_utc_iso()

    item = {
        "id": event_id,
        "resourceId": resource_id,
        "latency": latency,
        "errorRate": error_rate,
        "nxdomainAnomaly": nxdomain,
        "risk": risk,
        "timestamp": ts,
    }

    container = get_cosmos_container()
    wrote = write_risk_event(container, item)

    healed = False
    if risk >= RISK_THRESHOLD:
        healed = call_restart_webhook(resource_id, risk, telemetry)

    resp_obj = {
        "id": event_id,
        "resourceId": resource_id,
        "latency": latency,
        "errorRate": error_rate,
        "nxdomainAnomaly": nxdomain,
        "risk": risk,
        "ok": True,
        "cosmosWrite": bool(wrote),
        "autoHealTriggered": bool(healed),
        "timestamp": ts,
    }

    # Push the risk event to the stream buffer so the UI can see it live
    push_event(resp_obj)

    # If auto-heal happened, simulate recovery with a follow-up event that drops risk
    if healed:
        # tiny delay so UI feels "real time"
        time.sleep(0.35)
        healed_evt = dict(resp_obj)
        healed_evt["id"] = f"{event_id}-healed"
        healed_evt["timestamp"] = now_utc_iso()
        healed_evt["notes"] = "auto-heal completed"
        healed_evt["latency"] = min(latency, 120.0)
        healed_evt["errorRate"] = min(error_rate, 0.2)
        healed_evt["nxdomainAnomaly"] = False
        healed_evt["risk"] = compute_risk(healed_evt["latency"], healed_evt["errorRate"], False)
        healed_evt["autoHealTriggered"] = True
        push_event(healed_evt)

    return func.HttpResponse(
        json.dumps(resp_obj),
        status_code=200,
        mimetype="application/json",
        headers=cors_headers(),
    )
