#!/usr/bin/env python3
"""
PredictiveOps Outage Injector
─────────────────────────────
Sends synthetic telemetry to the RiskEngine to demo the full
predict → detect → auto-heal pipeline.

Usage:
    python inject.py --mode gradual    # latency creeps up, heal fires, metrics recover
    python inject.py --mode spike      # instant max risk, immediate heal
    python inject.py --mode scenarios  # cycles all 4 runbook scenarios
    python inject.py --mode chaos      # random signals, unpredictable noise

Options:
    --url      RiskEngine base URL   (default: http://localhost:7071)
    --interval Seconds between steps (default: 2.0)
    --resource Target resource ID    (default: demo-app-service-prod)
    --verbose  Print full JSON responses
"""

import argparse
import json
import random
import sys
import time
from typing import Optional

try:
    import requests
except ImportError:
    print("[error] 'requests' not installed. Run: pip install requests")
    sys.exit(1)


# ─── ANSI colours ────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
GREY   = "\033[90m"
BLUE   = "\033[94m"
ORANGE = "\033[38;5;208m"


def risk_colour(risk: float) -> str:
    if risk >= 0.75:
        return RED
    if risk >= 0.45:
        return YELLOW
    return GREEN


def risk_bar(risk: float, width: int = 20) -> str:
    filled = round(risk * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{risk_colour(risk)}{bar}{RESET}"


def banner(title: str, colour: str = CYAN) -> None:
    line = "─" * 58
    print(f"\n{colour}{BOLD}{line}")
    print(f"  {title}")
    print(f"{line}{RESET}\n")


# ─── Core send ───────────────────────────────────────────────────────────────

def send(
    base_url: str,
    resource_id: str,
    latency: float,
    error_rate: float,
    nxdomain: bool,
    verbose: bool = False,
    label: str = "",
) -> Optional[dict]:
    url = f"{base_url.rstrip('/')}/api/RiskEngine"
    payload = {
        "resourceId": resource_id,
        "latency": round(latency, 1),
        "errorRate": round(error_rate, 3),
        "nxdomainAnomaly": nxdomain,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
    except requests.exceptions.ConnectionError:
        print(f"  {RED}[error] Cannot connect to {url}{RESET}")
        print(f"  {GREY}Is 'func start' running?{RESET}\n")
        return None
    except Exception as e:
        print(f"  {RED}[error] {e}{RESET}")
        return None

    risk    = data.get("risk", 0)
    healed  = data.get("autoHealTriggered", False)
    written = data.get("cosmosWrite", False)

    tag = f"{GREY}[{label}]{RESET} " if label else ""

    print(
        f"  {tag}"
        f"latency={CYAN}{latency:>6.1f}ms{RESET}  "
        f"err={CYAN}{error_rate:>5.2f}%{RESET}  "
        f"nx={CYAN}{str(nxdomain):<5}{RESET}  "
        f"risk={risk_colour(risk)}{risk:.2f}{RESET} {risk_bar(risk, 16)}  "
        f"{'🔥 AUTO-HEAL FIRED' if healed else ''}"
        f"{'💾 cosmos' if written else GREY + 'no cosmos' + RESET}"
    )

    if healed:
        print(f"\n  {GREEN}{BOLD}  ✓ System self-healed → metrics recovering...{RESET}\n")

    if verbose:
        print(f"  {GREY}{json.dumps(data, indent=2)}{RESET}")

    return data


# ─── Mode: gradual ───────────────────────────────────────────────────────────

def mode_gradual(args) -> None:
    banner("GRADUAL DEGRADATION → AUTO-HEAL", ORANGE)
    print(f"  {GREY}Simulating a real-world failure pattern:{RESET}")
    print(f"  {GREY}latency creeps up → error rate follows → threshold crossed → system heals{RESET}\n")

    resource = args.resource

    steps = [
        # label,                  latency,  error_rate, nxdomain
        ("healthy baseline",        85.0,      0.05,    False),
        ("normal load",            110.0,      0.08,    False),
        ("slight slowdown",        145.0,      0.12,    False),
        ("degradation begins",     175.0,      0.30,    False),
        ("latency spike",          210.0,      0.55,    False),
        ("errors climbing",        240.0,      0.90,    False),
        ("dns anomaly detected",   255.0,      1.10,    True),
        ("critical — risk > 0.75", 280.0,      1.60,    True),  # ← heal fires here
        ("post-heal recovery",      95.0,      0.10,    False),
        ("back to baseline",        80.0,      0.04,    False),
    ]

    for label, latency, error_rate, nxdomain in steps:
        send(
            args.url, resource, latency, error_rate, nxdomain,
            verbose=args.verbose, label=label,
        )
        time.sleep(args.interval)

    print(f"\n  {GREEN}{BOLD}Demo complete.{RESET} Full event history is in the dashboard.\n")


# ─── Mode: spike ─────────────────────────────────────────────────────────────

def mode_spike(args) -> None:
    banner("INSTANT SPIKE → IMMEDIATE HEAL", RED)
    print(f"  {GREY}Firing a sudden max-risk event — heal should trigger immediately.{RESET}\n")

    resource = args.resource

    # One baseline, one spike, one recovery
    send(args.url, resource, 90.0,  0.05, False, args.verbose, "pre-spike baseline")
    time.sleep(args.interval)
    send(args.url, resource, 350.0, 2.50, True,  args.verbose, "SPIKE  ← max risk")
    time.sleep(args.interval)
    send(args.url, resource, 88.0,  0.04, False, args.verbose, "post-heal")

    print(f"\n  {GREEN}{BOLD}Done.{RESET}\n")


# ─── Mode: scenarios ─────────────────────────────────────────────────────────

RUNBOOK_SCENARIOS = [
    {
        "runbook":      "restart-appservice",
        "resource":     "prod-api-app-service",
        "description":  "App service memory leak — high latency + errors",
        "latency":      260.0,
        "error_rate":   1.8,
        "nxdomain":     False,
    },
    {
        "runbook":      "failover-storage",
        "resource":     "prod-storage-account-east",
        "description":  "Storage account unresponsive — timeouts spiking",
        "latency":      310.0,
        "error_rate":   2.1,
        "nxdomain":     False,
    },
    {
        "runbook":      "reroute-network",
        "resource":     "prod-vnet-gateway",
        "description":  "Network gateway degraded — DNS anomaly + latency",
        "latency":      230.0,
        "error_rate":   1.2,
        "nxdomain":     True,
    },
    {
        "runbook":      "clear-socket-connections",
        "resource":     "prod-load-balancer",
        "description":  "Load balancer socket exhaustion — error rate critical",
        "latency":      195.0,
        "error_rate":   1.5,
        "nxdomain":     False,
    },
]


def mode_scenarios(args) -> None:
    banner("ALL 4 RUNBOOK SCENARIOS", BLUE)
    print(f"  {GREY}Cycling through every automation runbook to show full coverage.{RESET}\n")

    for i, scenario in enumerate(RUNBOOK_SCENARIOS, 1):
        print(f"  {BOLD}Scenario {i}/4 — {scenario['runbook']}{RESET}")
        print(f"  {GREY}{scenario['description']}{RESET}")

        # Baseline first
        send(
            args.url, scenario["resource"],
            85.0, 0.05, False,
            args.verbose, "baseline",
        )
        time.sleep(args.interval * 0.5)

        # Trigger
        send(
            args.url, scenario["resource"],
            scenario["latency"], scenario["error_rate"], scenario["nxdomain"],
            args.verbose, f"trigger → {scenario['runbook']}",
        )
        time.sleep(args.interval * 1.5)

        # Recovery
        send(
            args.url, scenario["resource"],
            82.0, 0.03, False,
            args.verbose, "recovered",
        )

        print()
        if i < len(RUNBOOK_SCENARIOS):
            time.sleep(args.interval)

    print(f"  {GREEN}{BOLD}All 4 runbook scenarios complete.{RESET}\n")


# ─── Mode: chaos ─────────────────────────────────────────────────────────────

def mode_chaos(args) -> None:
    banner("CHAOS MODE — RANDOM SIGNALS", YELLOW)
    print(f"  {GREY}Unpredictable telemetry stream. Watch the risk score react in real time.{RESET}")
    print(f"  {GREY}Press Ctrl+C to stop.{RESET}\n")

    resource = args.resource
    count = 0

    try:
        while True:
            count += 1

            # Weighted random — biased toward healthy with occasional spikes
            roll = random.random()
            if roll < 0.55:
                # Healthy range
                latency    = random.uniform(60, 160)
                error_rate = random.uniform(0, 0.4)
                nxdomain   = False
            elif roll < 0.80:
                # Degraded
                latency    = random.uniform(160, 260)
                error_rate = random.uniform(0.4, 1.2)
                nxdomain   = random.random() < 0.2
            else:
                # Critical
                latency    = random.uniform(260, 400)
                error_rate = random.uniform(1.0, 3.0)
                nxdomain   = random.random() < 0.5

            send(
                args.url, resource, latency, error_rate, nxdomain,
                args.verbose, f"#{count:04d}",
            )
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n  {GREY}Chaos stopped after {count} events.{RESET}\n")


# ─── Entry point ─────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="PredictiveOps outage injector — demo the predict → heal pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--mode",
        choices=["gradual", "spike", "scenarios", "chaos"],
        default="gradual",
        help="Injection mode (default: gradual)",
    )
    p.add_argument(
        "--url",
        default="http://localhost:7071",
        help="RiskEngine base URL (default: http://localhost:7071)",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between telemetry steps (default: 2.0)",
    )
    p.add_argument(
        "--resource",
        default="demo-app-service-prod",
        help="Target resourceId to use in payloads",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print full JSON response for each event",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"\n{BOLD}PredictiveOps Outage Injector{RESET}")
    print(f"{GREY}target : {args.url}")
    print(f"mode   : {args.mode}")
    print(f"resource: {args.resource}{RESET}")

    modes = {
        "gradual":   mode_gradual,
        "spike":     mode_spike,
        "scenarios": mode_scenarios,
        "chaos":     mode_chaos,
    }
    modes[args.mode](args)


if __name__ == "__main__":
    main()