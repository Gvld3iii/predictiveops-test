# PredictiveOps

> **Cloud-native predictive reliability platform** — ingests real-time telemetry, scores infrastructure risk using a weighted model, persists events to Azure Cosmos DB, and automatically triggers self-healing runbooks before outages occur.

---

## What It Does

PredictiveOps continuously monitors your Azure infrastructure by ingesting telemetry signals (latency, error rates, DNS anomalies), computing a composite risk score, and autonomously executing remediation when risk exceeds a configurable threshold — all without human intervention.

**Key capabilities:**
- Real-time risk scoring across multiple telemetry dimensions
- Automatic self-healing via webhook-triggered Azure Automation runbooks
- Persistent audit trail of all risk events in Azure Cosmos DB
- Live streaming dashboard for observability
- Modular Azure Functions architecture (Python 3.x, v2 runtime)

---

## Architecture

```
Telemetry Producers
        │
        ▼
┌──────────────────┐      HTTP POST       ┌──────────────────────┐
│   External Apps  │ ──────────────────▶  │   RiskEngine         │
│   / Monitors     │                      │   (Azure Function)   │
└──────────────────┘                      │                      │
                                          │  • Parses telemetry  │
                                          │  • Scores risk 0–1   │
                                          │  • Writes to Cosmos  │
                                          │  • Triggers AutoHeal │
                                          └──────────┬───────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────┐
                          │                          │                      │
                          ▼                          ▼                      ▼
               ┌──────────────────┐    ┌──────────────────────┐  ┌─────────────────┐
               │  Cosmos DB       │    │  AutoHeal            │  │  shared_state   │
               │  (riskEvents)    │    │  (Azure Function)    │  │  (in-memory     │
               │                  │    │                      │  │   event bus)    │
               │  Persistent      │    │  Simulates runbook   │  │                 │
               │  audit log of    │    │  execution; returns  │  │  Ring buffer    │
               │  all risk events │    │  heal confirmation   │  │  (500 events)   │
               └──────────────────┘    └──────────────────────┘  └────────┬────────┘
                                                                           │
                                                                           ▼ polling
                                                               ┌──────────────────────┐
                                                               │  RiskStream          │
                                                               │  (Azure Function)    │
                                                               │                      │
                                                               │  SSE-style polling   │
                                                               │  endpoint; returns   │
                                                               │  events since seq N  │
                                                               └──────────┬───────────┘
                                                                          │
                                                                          ▼
                                                               ┌──────────────────────┐
                                                               │  Dashboard           │
                                                               │  (HTML/JS/CSS)       │
                                                               │                      │
                                                               │  Live risk feed,     │
                                                               │  charts, heal log    │
                                                               └──────────────────────┘
```

### PowerShell Automation Runbooks
When AutoHeal fires, it can invoke any of the following runbooks via Azure Automation:

| Runbook | What It Does |
|---|---|
| `restart-appservice.ps1` | Restarts a target Azure App Service using Managed Identity auth |
| `failover-storage.ps1` | Fails over storage to a secondary region |
| `reroute-network.ps1` | Reroutes traffic around a degraded network segment |
| `clear-socket-connections.ps1` | Clears stale socket connections on overloaded resources |

---

## Risk Scoring Model

The `compute_risk()` function in `RiskEngine` combines three telemetry signals into a composite score between `0.0` and `1.0`:

| Signal | Threshold | Weight |
|---|---|---|
| Latency | ≥ 200ms | +0.45 |
| Error Rate | ≥ 1.0% | +0.45 |
| NXDOMAIN Anomaly | `true` | +0.15 |

**Auto-heal fires when `risk ≥ RISK_THRESHOLD` (default: `0.75`).**

After a successful heal, the engine re-evaluates with reduced metrics and pushes a recovery event to the stream — so the dashboard reflects the actual healed state in real time.

---

## Project Structure

```
predictiveops/
├── RiskEngine/             # Core scoring + Cosmos write + heal trigger
│   ├── __init__.py         # Azure Function entrypoint + all logic
│   ├── main.py             # Standalone scoring logic
│   └── function.json       # HTTP trigger config
│
├── AutoHeal/               # Auto-heal webhook receiver
│   ├── __init__.py         # Simulates runbook execution
│   └── function.json       # HTTP trigger config
│
├── RiskStream/             # Polling stream for the dashboard
│   ├── __init__.py         # Returns events since a given sequence number
│   └── function.json       # HTTP trigger config
│
├── automation-runbooks/    # PowerShell runbooks for Azure Automation
│   ├── restart-appservice.ps1
│   ├── failover-storage.ps1
│   ├── reroute-network.ps1
│   └── clear-socket-connections.ps1
│
├── dashboard/              # Live observability UI
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── shared_state.py         # Thread-safe in-memory event ring buffer
├── host.json               # Azure Functions v2 runtime config
├── requirements.txt        # Python dependencies
└── local.settings.example.json  # Example env config (copy → local.settings.json)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Compute | Azure Functions v2 (Python 3.x) |
| Database | Azure Cosmos DB (NoSQL, `riskEvents` container) |
| Automation | Azure Automation + PowerShell runbooks |
| Frontend | Vanilla HTML/CSS/JavaScript |
| HTTP client | `requests` 2.32.5 |
| Cosmos SDK | `azure-cosmos` 4.14.2 |

---

## Local Setup

### Prerequisites
- Python 3.9+
- [Azure Functions Core Tools v4](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- Azure Cosmos DB account (or use the emulator for local dev)

### 1. Clone and install dependencies

```bash
git clone https://github.com/Gvld3iii/predictiveops-test.git
cd predictiveops-test

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp local.settings.example.json local.settings.json
```

Edit `local.settings.json` and fill in your values:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "COSMOS_URL": "https://<your-account>.documents.azure.com:443/",
    "COSMOS_KEY": "<your-cosmos-primary-key>",
    "COSMOS_DB": "predictiveops",
    "COSMOS_CONTAINER": "riskEvents",
    "RISK_THRESHOLD": "0.75",
    "WEBHOOK_RESTART": "http://localhost:7071/api/AutoHeal",
    "VERBOSE": "false"
  }
}
```

> **Note:** `WEBHOOK_RESTART` points to the AutoHeal function. In local dev it's the same host. In Azure, replace with the deployed AutoHeal function URL + key.

### 3. Run locally

```bash
func start
```

Functions will be available at:
- `POST http://localhost:7071/api/RiskEngine`
- `POST http://localhost:7071/api/AutoHeal`
- `GET  http://localhost:7071/api/RiskStream?since=0`

### 4. Open the dashboard

Open `dashboard/index.html` in your browser. Point it at `http://localhost:7071` and it will begin polling `RiskStream` for live events.

---

## Usage

### Submit a telemetry event

```bash
curl -X POST http://localhost:7071/api/RiskEngine \
  -H "Content-Type: application/json" \
  -d '{
    "resourceId": "my-app-service-prod",
    "latency": 250,
    "errorRate": 1.5,
    "nxdomainAnomaly": false
  }'
```

**Example response:**

```json
{
  "id": "my-app-service-prod-20241209T120000-a1b2c3d4",
  "resourceId": "my-app-service-prod",
  "latency": 250,
  "errorRate": 1.5,
  "nxdomainAnomaly": false,
  "risk": 0.9,
  "ok": true,
  "cosmosWrite": true,
  "autoHealTriggered": true,
  "timestamp": "2024-12-09T12:00:00.000000+00:00"
}
```

A `risk` of `0.9` exceeds the default threshold of `0.75`, so `autoHealTriggered: true` means the restart webhook fired and the runbook executed.

### Poll the event stream

```bash
curl "http://localhost:7071/api/RiskStream?since=0"
```

Returns all buffered events. Pass `?since=<latestSeq>` to get only new events since your last poll.

---

## Deploy to Azure

```bash
# Create a Function App in Azure (if not already created)
az functionapp create \
  --resource-group <your-rg> \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name predictiveops \
  --storage-account <your-storage>

# Deploy
func azure functionapp publish predictiveops

# Set environment variables
az functionapp config appsettings set \
  --name predictiveops \
  --resource-group <your-rg> \
  --settings \
    COSMOS_URL="https://<account>.documents.azure.com:443/" \
    COSMOS_KEY="<key>" \
    COSMOS_DB="predictiveops" \
    COSMOS_CONTAINER="riskEvents" \
    RISK_THRESHOLD="0.75" \
    WEBHOOK_RESTART="https://predictiveops.azurewebsites.net/api/AutoHeal?code=<key>"
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `COSMOS_URL` | `""` | Cosmos DB endpoint URL |
| `COSMOS_KEY` | `""` | Cosmos DB primary key |
| `COSMOS_DB` | `predictiveops` | Database name |
| `COSMOS_CONTAINER` | `riskEvents` | Container name (partition key: `/resourceId`) |
| `RISK_THRESHOLD` | `0.75` | Risk score at which auto-heal fires |
| `WEBHOOK_RESTART` | `""` | URL of AutoHeal function (or external runbook endpoint) |
| `VERBOSE` | `false` | Enables verbose logging |

---

## How Auto-Heal Works

1. `RiskEngine` computes a risk score for the incoming telemetry.
2. If `risk >= RISK_THRESHOLD`, it POSTs to `WEBHOOK_RESTART` (the `AutoHeal` function) with the resource ID, risk score, and full telemetry.
3. `AutoHeal` simulates the runbook execution and returns a heal confirmation.
4. `RiskEngine` pushes a follow-up "healed" event with reduced metrics to `shared_state`, so the dashboard immediately shows recovery.
5. All events (pre- and post-heal) are written to Cosmos DB for audit and analysis.

---

## Contributing

Pull requests welcome. For major changes, open an issue first to discuss what you'd like to change.

---

## License

MIT

---

## Outage Injector

Sends synthetic telemetry to demo the full **predict → detect → auto-heal** pipeline without needing a real outage.

### Install

```bash
pip install requests
```

### Modes

```bash
# Best for demos — latency creeps up, threshold crossed, system heals itself
python outage-injector/inject.py --mode gradual

# Instant max-risk event, heal fires immediately
python outage-injector/inject.py --mode spike

# Cycles all 4 runbook scenarios with different resource IDs
python outage-injector/inject.py --mode scenarios

# Unpredictable random signals, runs until Ctrl+C
python outage-injector/inject.py --mode chaos
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--url` | `http://localhost:7071` | RiskEngine base URL |
| `--interval` | `2.0` | Seconds between telemetry steps |
| `--resource` | `demo-app-service-prod` | Target resourceId |
| `--verbose` | off | Print full JSON responses |

```bash
# Point at a deployed Azure function
python outage-injector/inject.py \
  --mode gradual \
  --url https://predictiveops.azurewebsites.net \
  --interval 3.0 \
  --verbose
```

---

## Dashboard Demo Mode

No Azure account needed. Opens a fully self-contained demo that simulates the entire system locally.

```bash
open dashboard/demo.html
# or just double-click it in your file explorer
```

All 4 scenarios are available in the browser — gradual degradation, spike, all runbooks, and chaos mode. The risk scoring model is identical to the Python implementation so the behaviour is authentic.

---

## CI/CD — GitHub Actions

The workflow in `.github/workflows/deploy.yml` deploys to Azure Functions on every push to `main`.

### Required GitHub secrets

| Secret | Where to find it |
|---|---|
| `AZURE_CREDENTIALS` | Output of `az ad sp create-for-rbac --sdk-auth` |
| `AZURE_RESOURCE_GROUP` | Your Azure resource group name |
| `COSMOS_URL` | Azure Portal → Cosmos DB → Keys → URI |
| `COSMOS_KEY` | Azure Portal → Cosmos DB → Keys → Primary Key |
| `RISKENGINE_FUNCTION_KEY` | Azure Portal → Function App → Functions → RiskEngine → Function Keys |
| `AUTOHEAL_FUNCTION_KEY` | Azure Portal → Function App → Functions → AutoHeal → Function Keys |

### Set up the service principal

```bash
az ad sp create-for-rbac \
  --name predictiveops-deploy \
  --role contributor \
  --scopes /subscriptions/<sub-id>/resourceGroups/<rg-name> \
  --sdk-auth
```

Paste the JSON output as the `AZURE_CREDENTIALS` secret. After that, every push to `main` deploys automatically and runs a smoke test against the live RiskEngine endpoint.