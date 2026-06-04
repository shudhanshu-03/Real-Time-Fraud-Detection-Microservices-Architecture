#!/usr/bin/env python3
"""
Fraud Attack Simulation Tool

Simulates advanced fraud attack vectors against the Real-Time Fraud Detection Platform.

Usage:
    pip install httpx
    python3 scripts/fraud_attack_simulation.py --help
"""

import argparse
import asyncio
import hashlib
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, List, Dict

try:
    import httpx
except ImportError:
    print("\033[31m[ERROR]\033[0m httpx is not installed. Run: pip install httpx")
    sys.exit(1)

# ==============================================================================
# Configuration & Constants
# ==============================================================================

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT: float = 10.0

class Color:
    RED     = "\033[0;31m"
    GREEN   = "\033[0;32m"
    YELLOW  = "\033[1;33m"
    BLUE    = "\033[0;34m"
    CYAN    = "\033[0;36m"
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

# Base static lists
CURRENCIES = ["USD", "EUR", "GBP"]
CHANNELS = ["online", "mobile", "pos", "atm", "phone"]

DOMESTIC_LOCATIONS = [
    (40.7128, -74.0060),   # New York
    (34.0522, -118.2437),  # Los Angeles
    (41.8781, -87.6298),   # Chicago
]

INTERNATIONAL_LOCATIONS = [
    (55.7558, 37.6173),    # Moscow
    (1.3521, 103.8198),    # Singapore
    (-23.5505, -46.6333),  # São Paulo
]

def _device_fingerprint(seed: str = None) -> str:
    raw = seed if seed else f"{uuid.uuid4()}-{random.random()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _random_ip(international: bool = False) -> str:
    first_octet = random.choice([41, 77, 91, 103, 176, 185]) if international else random.choice([12, 24, 50, 64, 72, 96])
    return f"{first_octet}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def _masked_card(seed: int = None) -> str:
    last4 = f"{seed:04d}" if seed is not None else f"{random.randint(1000, 9999)}"
    return f"****-****-****-{last4}"

def _timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def base_transaction() -> Dict[str, Any]:
    loc = random.choice(DOMESTIC_LOCATIONS)
    return {
        "transaction_id": str(uuid.uuid4()),
        "amount": round(random.uniform(10.0, 100.0), 2),
        "currency": "USD",
        "merchant_id": "MCH-001",
        "merchant_name": "Target",
        "merchant_category": "grocery",
        "card_number": _masked_card(),
        "customer_id": f"CUST-{random.randint(10000, 99999)}",
        "timestamp": _timestamp_now(),
        "location": {"latitude": loc[0], "longitude": loc[1]},
        "ip_address": _random_ip(international=False),
        "device_fingerprint": _device_fingerprint(),
        "channel": random.choice(CHANNELS),
        "risk_label": "fraudulent",
    }

# Attack Scenario Generators

def generate_velocity_attack(count: int) -> List[Dict[str, Any]]:
    """
    Velocity Attack / Credential Stuffing
    Single IP/Device rapidly testing many distinct cards with small amounts.
    """
    txns = []
    attacker_ip = _random_ip(international=True)
    attacker_device = _device_fingerprint("velocity-attacker-device")
    merchant_id = "MCH-006"
    merchant_name = "Amazon Prime"
    
    for _ in range(count):
        txn = base_transaction()
        txn.update({
            "amount": round(random.uniform(1.0, 5.0), 2),  # Small test amount
            "merchant_id": merchant_id,
            "merchant_name": merchant_name,
            "merchant_category": "subscription",
            "ip_address": attacker_ip,
            "device_fingerprint": attacker_device,
            "card_number": _masked_card(), # New card each time
            "channel": "online"
        })
        txns.append(txn)
    return txns

def generate_ato_attack(count: int) -> List[Dict[str, Any]]:
    """
    Account Takeover (ATO)
    Known customer ID, but completely different geo/IP/device and high amount.
    """
    txns = []
    for _ in range(count):
        victim_customer_id = f"CUST-{random.randint(1000, 5000)}"
        loc = random.choice(INTERNATIONAL_LOCATIONS)
        txn = base_transaction()
        txn.update({
            "customer_id": victim_customer_id,
            "amount": round(random.uniform(5000.0, 15000.0), 2), # High drain amount
            "merchant_id": "MCH-101",
            "merchant_name": "CryptoXchange Ltd",
            "merchant_category": "cryptocurrency",
            "ip_address": _random_ip(international=True),
            "device_fingerprint": _device_fingerprint(), # Unrecognized device
            "location": {"latitude": loc[0], "longitude": loc[1]},
            "channel": "online"
        })
        txns.append(txn)
    return txns

def generate_structuring_attack(count: int) -> List[Dict[str, Any]]:
    """
    Structuring / Smurfing
    Single customer sending multiple transactions just below the $10k threshold.
    """
    txns = []
    # Using 3 distinct customer IDs as "smurfs"
    smurfs = [f"SMURF-{i}" for i in range(1, 4)]
    for _ in range(count):
        txn = base_transaction()
        txn.update({
            "customer_id": random.choice(smurfs),
            "amount": round(random.uniform(9500.0, 9950.0), 2), # Just below 10k
            "merchant_id": "MCH-103",
            "merchant_name": "QuickWire International",
            "merchant_category": "wire_transfer",
            "channel": "mobile"
        })
        txns.append(txn)
    return txns

def generate_botnet_attack(count: int) -> List[Dict[str, Any]]:
    """
    Coordinated Botnet Attack
    Many different IPs/devices all hitting the exact same merchant simultaneously.
    """
    txns = []
    target_merchant_id = "MCH-904"
    target_merchant_name = "Darkmarket Store"
    for _ in range(count):
        txn = base_transaction()
        txn.update({
            "amount": round(random.uniform(50.0, 200.0), 2),
            "merchant_id": target_merchant_id,
            "merchant_name": target_merchant_name,
            "merchant_category": "darknet_marketplace",
            # Randomize all identity attributes
            "ip_address": _random_ip(international=True),
            "device_fingerprint": _device_fingerprint(),
            "customer_id": f"BOTCUST-{random.randint(10000, 99999)}"
        })
        txns.append(txn)
    return txns

def generate_synthetic_identity_attack(count: int) -> List[Dict[str, Any]]:
    """
    Synthetic Identity Probing
    Sequential customer IDs making initial low-risk purchases from similar devices.
    """
    txns = []
    base_device = _device_fingerprint("synthetic-ring")
    for i in range(count):
        txn = base_transaction()
        txn.update({
            "customer_id": f"SYNTH-ID-{1000+i}", # Sequential IDs
            "amount": round(random.uniform(5.0, 25.0), 2), # Low risk amount
            "merchant_id": "MCH-004",
            "merchant_name": "CVS Pharmacy",
            "merchant_category": "pharmacy",
            "device_fingerprint": base_device, # Shared device for the synthetic ring
            "ip_address": _random_ip(international=False)
        })
        txns.append(txn)
    return txns

# Simulation Engine

class SimulationStats:
    def __init__(self):
        self.sent = 0
        self.success = 0
        self.failed = 0
        self.total_time = 0.0
        self.error_messages_logged = 0

async def fire_transaction(client: httpx.AsyncClient, txn: Dict[str, Any], stats: SimulationStats) -> None:
    """Send a single transaction asynchronously and update stats."""
    stats.sent += 1
    start_time = time.time()
    try:
        response = await client.post("/api/v1/transactions", json=txn, timeout=REQUEST_TIMEOUT)
        if response.status_code in (200, 201, 202):
            stats.success += 1
        else:
            stats.failed += 1
            if stats.error_messages_logged < 5:
                log_warn(f"Transaction Failed. HTTP {response.status_code}: {response.text}")
                stats.error_messages_logged += 1
    except httpx.RequestError as exc:
        stats.failed += 1
        if stats.error_messages_logged < 5:
            log_warn(f"Request Error: {exc}")
            stats.error_messages_logged += 1
    stats.total_time += (time.time() - start_time)

async def run_attack(attack_type: str, tps: int, duration: int) -> None:
    total_txns = tps * duration
    log_info(f"Starting '{attack_type}' attack simulation.")
    log_info(f"Target TPS: {tps} | Duration: {duration}s | Total Transactions: {total_txns}")
    
    generators = {
        "velocity": generate_velocity_attack,
        "ato": generate_ato_attack,
        "structuring": generate_structuring_attack,
        "botnet": generate_botnet_attack,
        "synthetic": generate_synthetic_identity_attack
    }
    
    if attack_type not in generators and attack_type != "all":
        log_error(f"Unknown attack type '{attack_type}'")
        return

    # Prepare transactions
    txns_to_send = []
    if attack_type == "all":
        # Split evenly across all 5 types
        per_type = total_txns // 5
        for gen in generators.values():
            txns_to_send.extend(gen(per_type))
        # Fill remaining if not perfectly divisible
        rem = total_txns - len(txns_to_send)
        if rem > 0:
            txns_to_send.extend(generate_botnet_attack(rem))
    else:
        txns_to_send = generators[attack_type](total_txns)
        
    # Shuffle only if 'all', otherwise we want sequential patterns (like velocity/synthetic) to occur closely
    if attack_type == "all":
        random.shuffle(txns_to_send)
        
    stats = SimulationStats()
    
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        # Check API connectivity
        try:
            health = await client.get("/health", timeout=5.0)
            if health.status_code != 200:
                log_warn(f"API /health returned {health.status_code}")
        except httpx.RequestError:
            log_warn(f"API {API_BASE_URL} is unreachable or doesn't have /health endpoint. Proceeding anyway...")

        # Execute at desired TPS
        log_info("Firing transactions...")
        simulation_start = time.time()
        
        for i in range(0, len(txns_to_send), tps):
            batch = txns_to_send[i:i+tps]
            tasks = [fire_transaction(client, txn, stats) for txn in batch]
            
            # Fire batch concurrently
            batch_start = time.time()
            await asyncio.gather(*tasks)
            batch_elapsed = time.time() - batch_start
            
            # Sleep remainder of the second to maintain TPS
            sleep_time = 1.0 - batch_elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        simulation_duration = time.time() - simulation_start
    
    # Report Summary
    print()
    print(f"{Color.CYAN}{'-' * 50}{Color.NC}")
    print(f"{Color.BOLD}Simulation Summary Report{Color.NC}")
    print(f"{Color.CYAN}{'-' * 50}{Color.NC}")
    print(f"Attack Type     : {attack_type}")
    print(f"Duration        : {simulation_duration:.2f} seconds")
    print(f"Transactions    : {stats.sent} attempted")
    print(f"Success (20x)   : {Color.GREEN}{stats.success}{Color.NC}")
    print(f"Failed          : {Color.RED if stats.failed > 0 else Color.NC}{stats.failed}{Color.NC}")
    
    actual_tps = stats.sent / simulation_duration if simulation_duration > 0 else 0
    avg_latency = (stats.total_time / stats.sent * 1000) if stats.sent > 0 else 0
    print(f"Actual TPS      : {actual_tps:.2f} req/s")
    print(f"Avg Latency     : {avg_latency:.2f} ms")
    print(f"{Color.CYAN}{'-' * 50}{Color.NC}")
    print()
    
    if stats.failed > 0:
        log_warn("Some transactions failed. Check API Gateway logs.")
    else:
        log_success("Simulation completed successfully!")

# CLI Entry Point

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fraud Attack Simulation Tool")
    parser.add_argument(
        "--attack-type", 
        type=str, 
        choices=["velocity", "ato", "structuring", "botnet", "synthetic", "all"], 
        default="all",
        help="Type of attack to simulate (default: all)"
    )
    parser.add_argument(
        "--tps", 
        type=int, 
        default=50, 
        help="Target transactions per second (default: 50)"
    )
    parser.add_argument(
        "--duration", 
        type=int, 
        default=10, 
        help="Duration of the simulation in seconds (default: 10)"
    )
    
    args = parser.parse_args()
    
    print(f"{Color.CYAN}{Color.BOLD}")
    print("--------------------------------------------------------------")
    print("|                                                            |")
    print("|          Fraud Attack Simulation Engine                    |")
    print("|                                                            |")
    print("--------------------------------------------------------------")
    print(f"{Color.NC}")
    
    try:
        asyncio.run(run_attack(args.attack_type, args.tps, args.duration))
    except KeyboardInterrupt:
        print()
        log_warn("Simulation aborted by user.")
        sys.exit(0)
