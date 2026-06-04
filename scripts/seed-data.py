#!/usr/bin/env python3
"""
Seed test data for the Fraud Detection Platform.

Generates and submits realistic synthetic transactions, alerts, and cases via
the platform's REST API to populate the local development environment.

Usage:
    pip install httpx
    python3 scripts/seed-data.py

Environment Variables:
    API_BASE_URL  - Base URL of the API Gateway (default: http://localhost:8000)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import httpx
except ImportError:
    print("\033[31m[ERROR]\033[0m  httpx is not installed. Run: pip install httpx")
    sys.exit(1)

# Configuration

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT: float = 30.0

# Color helpers

class Color:
    RED     = "\033[0;31m"
    GREEN   = "\033[0;32m"
    YELLOW  = "\033[1;33m"
    BLUE    = "\033[0;34m"
    CYAN    = "\033[0;36m"
    MAGENTA = "\033[0;35m"
    BOLD    = "\033[1m"
    NC      = "\033[0m"


def log_info(msg: str) -> None:
    print(f"{Color.BLUE}[INFO]{Color.NC}    {msg}")

def log_success(msg: str) -> None:
    print(f"{Color.GREEN}[OK]{Color.NC}      {msg}")

def log_warn(msg: str) -> None:
    print(f"{Color.YELLOW}[WARN]{Color.NC}    {msg}")

def log_error(msg: str) -> None:
    print(f"{Color.RED}[ERROR]{Color.NC}   {msg}")


# Data Generators

# --- Constants ----------------------------------------------------------------

CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"]

MERCHANT_CATEGORIES_NORMAL = [
    "grocery", "restaurant", "gas_station", "pharmacy", "clothing",
    "electronics", "subscription", "utility", "insurance", "education",
]

MERCHANT_CATEGORIES_SUSPICIOUS = [
    "jewelry", "cryptocurrency", "wire_transfer", "luxury_goods",
    "casino", "adult_entertainment", "pawn_shop",
]

MERCHANT_CATEGORIES_FRAUD = [
    "unknown", "shell_company", "offshore_services", "darknet_marketplace",
    "unregistered_mso", "anonymous_prepaid",
]

MERCHANTS_NORMAL = [
    ("MCH-001", "Whole Foods Market"),
    ("MCH-002", "Starbucks"),
    ("MCH-003", "Shell Gas Station"),
    ("MCH-004", "CVS Pharmacy"),
    ("MCH-005", "Target"),
    ("MCH-006", "Amazon Prime"),
    ("MCH-007", "Netflix"),
    ("MCH-008", "Walmart"),
    ("MCH-009", "Costco"),
    ("MCH-010", "Home Depot"),
]

MERCHANTS_SUSPICIOUS = [
    ("MCH-101", "CryptoXchange Ltd"),
    ("MCH-102", "LuxuryBags Online"),
    ("MCH-103", "QuickWire International"),
    ("MCH-104", "GoldVault Jewelers"),
    ("MCH-105", "PremiumElite Casino"),
]

MERCHANTS_FRAUD = [
    ("MCH-901", "Unknown Vendor #4821"),
    ("MCH-902", "Offshore Holdings LLC"),
    ("MCH-903", "Anonymous Prepaid Svcs"),
    ("MCH-904", "Darkmarket Store"),
    ("MCH-905", "ShellCorp Intl"),
]

CHANNELS = ["web", "mobile_app", "pos", "atm", "phone"]

DOMESTIC_LOCATIONS = [
    (40.7128, -74.0060),   # New York
    (34.0522, -118.2437),  # Los Angeles
    (41.8781, -87.6298),   # Chicago
    (29.7604, -95.3698),   # Houston
    (33.4484, -112.0740),  # Phoenix
    (39.7392, -104.9903),  # Denver
    (47.6062, -122.3321),  # Seattle
    (25.7617, -80.1918),   # Miami
]

INTERNATIONAL_LOCATIONS = [
    (55.7558, 37.6173),    # Moscow
    (1.3521, 103.8198),    # Singapore
    (-23.5505, -46.6333),  # São Paulo
    (51.5074, -0.1278),    # London
    (31.2304, 121.4737),   # Shanghai
    (35.6762, 139.6503),   # Tokyo
    (19.0760, 72.8777),    # Mumbai
    (6.5244, 3.3792),      # Lagos
]


def _masked_card() -> str:
    """Generate a masked card number like ****-****-****-1234."""
    last4 = f"{random.randint(1000, 9999)}"
    return f"****-****-****-{last4}"


def _device_fingerprint() -> str:
    """Generate a pseudo-random device fingerprint hash."""
    raw = f"{uuid.uuid4()}-{random.random()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _random_ip(international: bool = False) -> str:
    """Generate a plausible IP address."""
    if international:
        first_octet = random.choice([41, 77, 91, 103, 176, 185, 195, 202])
    else:
        first_octet = random.choice([12, 24, 50, 64, 72, 96, 104, 172])
    return f"{first_octet}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _timestamp_within(days_back: int = 30) -> str:
    """Return an ISO-8601 timestamp within the last N days."""
    offset = timedelta(seconds=random.randint(0, days_back * 86400))
    dt = datetime.now(timezone.utc) - offset
    return dt.isoformat()


# Transaction Generators

def generate_normal_transactions(count: int = 70) -> list[dict[str, Any]]:
    """Generate realistic low-risk domestic transactions."""
    txns: list[dict[str, Any]] = []
    for _ in range(count):
        merchant = random.choice(MERCHANTS_NORMAL)
        loc = random.choice(DOMESTIC_LOCATIONS)
        txns.append({
            "transaction_id": str(uuid.uuid4()),
            "amount": round(random.uniform(10.0, 500.0), 2),
            "currency": "USD",
            "merchant_id": merchant[0],
            "merchant_name": merchant[1],
            "merchant_category": random.choice(MERCHANT_CATEGORIES_NORMAL),
            "card_number": _masked_card(),
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "timestamp": _timestamp_within(30),
            "location": {"latitude": loc[0], "longitude": loc[1]},
            "ip_address": _random_ip(international=False),
            "device_fingerprint": _device_fingerprint(),
            "channel": random.choice(CHANNELS),
            "risk_label": "normal",
        })
    return txns


def generate_suspicious_transactions(count: int = 20) -> list[dict[str, Any]]:
    """Generate medium-risk transactions with unusual patterns."""
    txns: list[dict[str, Any]] = []
    for _ in range(count):
        merchant = random.choice(MERCHANTS_SUSPICIOUS)
        use_intl = random.random() > 0.5
        loc = random.choice(INTERNATIONAL_LOCATIONS if use_intl else DOMESTIC_LOCATIONS)
        txns.append({
            "transaction_id": str(uuid.uuid4()),
            "amount": round(random.uniform(500.0, 5000.0), 2),
            "currency": random.choice(CURRENCIES),
            "merchant_id": merchant[0],
            "merchant_name": merchant[1],
            "merchant_category": random.choice(MERCHANT_CATEGORIES_SUSPICIOUS),
            "card_number": _masked_card(),
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "timestamp": _timestamp_within(14),
            "location": {"latitude": loc[0], "longitude": loc[1]},
            "ip_address": _random_ip(international=use_intl),
            "device_fingerprint": _device_fingerprint(),
            "channel": random.choice(CHANNELS),
            "risk_label": "suspicious",
        })
    return txns


def generate_fraudulent_transactions(count: int = 10) -> list[dict[str, Any]]:
    """Generate high-risk transactions matching known fraud patterns."""
    txns: list[dict[str, Any]] = []
    for _ in range(count):
        merchant = random.choice(MERCHANTS_FRAUD)
        loc = random.choice(INTERNATIONAL_LOCATIONS)
        txns.append({
            "transaction_id": str(uuid.uuid4()),
            "amount": round(random.uniform(5000.0, 50000.0), 2),
            "currency": random.choice(["USD", "EUR", "CHF"]),
            "merchant_id": merchant[0],
            "merchant_name": merchant[1],
            "merchant_category": random.choice(MERCHANT_CATEGORIES_FRAUD),
            "card_number": _masked_card(),
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "timestamp": _timestamp_within(7),
            "location": {"latitude": loc[0], "longitude": loc[1]},
            "ip_address": _random_ip(international=True),
            "device_fingerprint": _device_fingerprint(),
            "channel": random.choice(["web", "mobile_app"]),
            "risk_label": "fraudulent",
        })
    return txns


# Alert Generator

ALERT_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
ALERT_TYPES = [
    "velocity_breach",
    "geo_anomaly",
    "amount_threshold",
    "device_mismatch",
    "card_not_present_fraud",
    "account_takeover",
    "identity_theft",
    "money_laundering_pattern",
]


def generate_alerts(count: int = 10) -> list[dict[str, Any]]:
    """Generate sample fraud alerts of varying severity."""
    alerts: list[dict[str, Any]] = []
    for i in range(count):
        severity = ALERT_SEVERITIES[i % len(ALERT_SEVERITIES)]
        alerts.append({
            "alert_id": str(uuid.uuid4()),
            "alert_type": random.choice(ALERT_TYPES),
            "severity": severity,
            "title": f"Fraud Alert — {severity} severity detected",
            "description": (
                f"Automated detection flagged a {severity.lower()}-severity pattern. "
                f"Alert type: {random.choice(ALERT_TYPES)}. "
                "Review transaction details and linked entities for investigation."
            ),
            "transaction_id": str(uuid.uuid4()),
            "customer_id": f"CUST-{random.randint(10000, 99999)}",
            "risk_score": round(random.uniform(
                0.85 if severity == "CRITICAL" else
                0.65 if severity == "HIGH" else
                0.45 if severity == "MEDIUM" else 0.25,
                1.0 if severity in ("CRITICAL", "HIGH") else
                0.65 if severity == "MEDIUM" else 0.45,
            ), 3),
            "status": random.choice(["new", "acknowledged", "investigating"]),
            "created_at": _timestamp_within(7),
            "assigned_to": None,
        })
    return alerts


# Case Generator

CASE_STATUSES = ["open", "investigating", "resolved"]


def generate_cases(count: int = 3) -> list[dict[str, Any]]:
    """Generate sample investigation cases."""
    cases: list[dict[str, Any]] = []
    for i in range(count):
        status = CASE_STATUSES[i % len(CASE_STATUSES)]
        num_alerts = random.randint(1, 5)
        cases.append({
            "case_id": str(uuid.uuid4()),
            "title": f"Investigation Case #{i + 1} — {status.replace('_', ' ').title()}",
            "description": (
                f"Consolidated investigation case containing {num_alerts} related alerts. "
                f"Current status: {status}."
            ),
            "status": status,
            "priority": random.choice(["critical", "high", "medium"]),
            "alert_ids": [str(uuid.uuid4()) for _ in range(num_alerts)],
            "assigned_to": f"analyst-{random.randint(1, 5)}@fraudteam.local",
            "created_at": _timestamp_within(14),
            "updated_at": _timestamp_within(3),
            "resolution": (
                "Confirmed fraudulent activity. Card blocked and customer notified."
                if status == "resolved"
                else None
            ),
        })
    return cases


# API Client

async def post_batch(
    client: httpx.AsyncClient,
    endpoint: str,
    records: list[dict[str, Any]],
    label: str,
) -> tuple[int, int]:
    """
    POST each record to the given endpoint.
    Returns (success_count, failure_count).
    """
    successes = 0
    failures = 0

    for record in records:
        try:
            response = await client.post(endpoint, json=record, timeout=REQUEST_TIMEOUT)
            if response.status_code in (200, 201, 202):
                successes += 1
            else:
                failures += 1
                if failures <= 3:
                    log_warn(
                        f"{label}: HTTP {response.status_code} for "
                        f"{record.get('transaction_id') or record.get('alert_id') or record.get('case_id', '?')}"
                    )
        except httpx.RequestError as exc:
            failures += 1
            if failures <= 3:
                log_warn(f"{label}: Request error — {exc}")

    return successes, failures


# Main

async def main() -> None:
    print()
    print(f"{Color.CYAN}{Color.BOLD}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║       Fraud Detection Platform — Data Seeder               ║")
    print("║                                                            ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Color.NC}")
    log_info(f"API Base URL: {API_BASE_URL}")
    print()

    # ---- Generate data -------------------------------------------------------
    log_info("Generating synthetic data…")

    normal_txns     = generate_normal_transactions(70)
    suspicious_txns = generate_suspicious_transactions(20)
    fraud_txns      = generate_fraudulent_transactions(10)
    all_transactions = normal_txns + suspicious_txns + fraud_txns
    random.shuffle(all_transactions)

    alerts = generate_alerts(10)
    cases  = generate_cases(3)

    log_success(f"Generated {len(all_transactions)} transactions, {len(alerts)} alerts, {len(cases)} cases")

    # ---- Connectivity check --------------------------------------------------
    log_info("Checking API connectivity…")
    try:
        async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
            health = await client.get("/health", timeout=10.0)
            if health.status_code == 200:
                log_success("API is reachable")
            else:
                log_warn(f"API returned status {health.status_code} on /health")
    except httpx.RequestError as exc:
        log_error(f"Cannot reach API at {API_BASE_URL}: {exc}")
        log_error("Make sure the platform is running (./scripts/setup-local.sh)")
        sys.exit(1)

    # ---- Seed data -----------------------------------------------------------
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:

        # Transactions
        log_info("Seeding transactions…")
        txn_ok, txn_fail = await post_batch(
            client, "/api/v1/transactions", all_transactions, "Transaction"
        )

        # Alerts
        log_info("Seeding alerts…")
        alert_ok, alert_fail = await post_batch(
            client, "/api/v1/alerts", alerts, "Alert"
        )

        # Cases
        log_info("Seeding cases…")
        case_ok, case_fail = await post_batch(
            client, "/api/v1/cases", cases, "Case"
        )

    # ---- Summary Table -------------------------------------------------------
    print()
    print(f"{Color.CYAN}{'─' * 62}{Color.NC}")
    print(f"{Color.BOLD}  {'Entity':<25} {'Sent':>8} {'OK':>8} {'Failed':>8}{Color.NC}")
    print(f"{Color.CYAN}{'─' * 62}{Color.NC}")

    rows = [
        ("Normal Transactions",      len(normal_txns),     None, None),
        ("Suspicious Transactions",  len(suspicious_txns), None, None),
        ("Fraudulent Transactions",  len(fraud_txns),      None, None),
        ("Transactions (total)",     len(all_transactions), txn_ok,   txn_fail),
        ("Alerts",                   len(alerts),           alert_ok, alert_fail),
        ("Cases",                    len(cases),            case_ok,  case_fail),
    ]

    for label, sent, ok, fail in rows:
        ok_str   = str(ok)   if ok is not None else "—"
        fail_str = str(fail) if fail is not None else "—"
        fail_color = Color.RED if (fail and fail > 0) else Color.NC
        print(
            f"  {label:<25} {sent:>8} "
            f"{Color.GREEN}{ok_str:>8}{Color.NC} "
            f"{fail_color}{fail_str:>8}{Color.NC}"
        )

    print(f"{Color.CYAN}{'─' * 62}{Color.NC}")
    print()

    total_fail = txn_fail + alert_fail + case_fail
    if total_fail == 0:
        log_success("All data seeded successfully!")
    else:
        log_warn(f"{total_fail} records failed — check API logs for details")

    print()


if __name__ == "__main__":
    asyncio.run(main())
