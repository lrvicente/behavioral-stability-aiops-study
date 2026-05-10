#!/usr/bin/env python3
"""
Fault injection executor for CNSM 2027 cross-environment study.

Runs on each host via cron every minute. Reads the local schedule CSV,
identifies any faults due to start within the next minute, and executes them.

Each execution writes a marker file (/var/run/cnsm-fault-active) and a
log entry consumed by the Zabbix user parameter cnsm.fault.active. This
provides ground truth synchronized with the Zabbix metric stream.

Usage (typically called from cron):
  /opt/cnsm-study/scripts/inject_fault.py --schedule /etc/cnsm/fault_schedule.csv --host $(hostname)
"""
from __future__ import annotations

import argparse
import csv
import os
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACTIVE_MARKER = Path("/var/run/cnsm-fault-active")
CLASS_MARKER = Path("/var/run/cnsm-fault-class")
EXECUTION_LOG = Path("/var/log/cnsm-faults/executions.log")


def log(message: str) -> None:
    EXECUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EXECUTION_LOG.open("a") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


def parse_parameters(params_str: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in params_str.split():
        if "=" in token:
            k, v = token.split("=", 1)
            result[k] = v
    return result


def execute_fault(fault_class: str, duration: int, params: dict[str, str]) -> None:
    """Execute fault using stress-ng or tc, blocking for `duration` seconds."""
    log(f"START class={fault_class} duration={duration} params={params}")
    ACTIVE_MARKER.write_text("1")
    CLASS_MARKER.write_text(fault_class)

    try:
        cmd: list[str] = []
        if fault_class == "cpu_spike":
            cmd = [
                "stress-ng", "--cpu", params.get("cpu", "2"),
                "--cpu-load", params.get("load", "90"),
                "--timeout", str(duration),
            ]
        elif fault_class == "memory_pressure":
            cmd = [
                "stress-ng", "--vm", "2",
                "--vm-bytes", params.get("vm_bytes", "2G"),
                "--vm-keep", "--timeout", str(duration),
            ]
        elif fault_class == "disk_io":
            cmd = [
                "stress-ng", "--io", params.get("io", "4"),
                "--hdd", params.get("hdd", "4"),
                "--timeout", str(duration),
            ]
        elif fault_class == "network_latency":
            iface = subprocess.check_output(
                ["sh", "-c", "ip route | awk '/default/ {print $5; exit}'"]
            ).decode().strip()
            delay = params.get("delay", "100ms")
            subprocess.run(
                ["tc", "qdisc", "add", "dev", iface, "root", "netem", "delay", delay],
                check=False,
            )
            try:
                subprocess.run(["sleep", str(duration)], check=False)
            finally:
                subprocess.run(
                    ["tc", "qdisc", "del", "dev", iface, "root", "netem"],
                    check=False,
                )
            log(f"END class={fault_class}")
            return
        elif fault_class == "process_leak":
            cmd = [
                "stress-ng", "--fork", params.get("fork", "4"),
                "--timeout", str(duration),
            ]
        else:
            log(f"UNKNOWN class={fault_class}")
            return

        subprocess.run(cmd, check=False, timeout=duration + 30)
    except Exception as exc:
        log(f"ERROR class={fault_class} exc={exc}")
    finally:
        if ACTIVE_MARKER.exists():
            ACTIVE_MARKER.unlink()
        if CLASS_MARKER.exists():
            CLASS_MARKER.unlink()
        log(f"END class={fault_class}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--host", default=socket.gethostname())
    parser.add_argument("--window-seconds", type=int, default=60)
    args = parser.parse_args()

    if not args.schedule.exists():
        sys.stderr.write(f"Schedule file not found: {args.schedule}\n")
        return 1

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(seconds=args.window_seconds)

    if ACTIVE_MARKER.exists():
        log("SKIP another fault still active")
        return 0

    with args.schedule.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row["host"] != args.host:
                continue
            scheduled = datetime.fromisoformat(row["scheduled_iso"])
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            if now <= scheduled < window_end:
                execute_fault(
                    row["fault_class"],
                    int(row["duration_seconds"]),
                    parse_parameters(row["parameters"]),
                )
                return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
