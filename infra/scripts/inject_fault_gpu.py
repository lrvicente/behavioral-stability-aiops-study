#!/usr/bin/env python3
"""
GPU fault injection executor for CNSM 2027 study (cnsm-gpu-01 only).

Mirrors inject_fault.py: runs via cron every minute, reads the local
schedule CSV, executes any GPU fault due within the window. Writes the
same ground-truth markers (/var/run/cnsm-fault-active, cnsm-fault-class)
consumed by Zabbix, keeping the GPU node consistent with the workers.

Five GPU fault classes (mapped from the worker classes):
  gpu_compute_stress  - saturate GPU compute (matmul loop)
  vram_pressure       - allocate VRAM up to a target fraction (may OOM workload)
  pcie_bandwidth_sat  - continuous host<->device transfers
  network_degradation - tc netem (identical to workers' network_latency)
  cuda_process_kill   - SIGKILL CUDA processes (workload restarts via systemd)
"""
from __future__ import annotations

import argparse
import csv
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACTIVE_MARKER = Path("/var/run/cnsm-fault-active")
CLASS_MARKER = Path("/var/run/cnsm-fault-class")
EXECUTION_LOG = Path("/var/log/cnsm-faults/executions.log")
HEARTBEAT = Path("/var/run/cnsm-workload-heartbeat")

# PIDs we must never kill in cuda_process_kill
SELF_PROTECT_NAMES = ("inject_fault_gpu", "gpu_metrics", "zabbix")


def log(message: str) -> None:
    EXECUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EXECUTION_LOG.open("a") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


def parse_parameters(params_str: str) -> dict:
    result = {}
    for token in params_str.split():
        if "=" in token:
            k, v = token.split("=", 1)
            result[k] = v
    return result


# ---------- GPU fault primitives ----------

def _gpu_compute_stress(duration: int, params: dict) -> None:
    size = int(params.get("matrix_size", "8192"))
    code = (
        "import torch,time;"
        "d=torch.device('cuda');"
        f"a=torch.randn({size},{size},device=d);"
        f"b=torch.randn({size},{size},device=d);"
        f"t=time.time()+{duration};"
        "c=a@b;"
        "import sys;"
        "exec(\"while time.time()<t:\\n c=(a@b);torch.cuda.synchronize()\")"
    )
    subprocess.run(["python3", "-c", code], check=False, timeout=duration + 30)


def _vram_pressure(duration: int, params: dict) -> None:
    frac = float(params.get("fraction", "0.95"))
    # Allocate in a dedicated child process so the OS reclaims ALL VRAM on kill.
    code = (
        "import torch,time;"
        "d=torch.device('cuda');"
        "free,total=torch.cuda.mem_get_info();"
        f"target=int(total*{frac});"
        "blocks=[];"
        "step=256*1024*1024;"  # 256MB chunks
        "alloc=0;"
        "exec(\""
        "while alloc<target:\\n"
        " try:\\n"
        "  blocks.append(torch.empty(step//2,dtype=torch.float16,device=d));alloc+=step\\n"
        " except RuntimeError:\\n"
        "  break\");"
        f"time.sleep({duration})"
    )
    proc = subprocess.Popen(["python3", "-c", code])
    try:
        proc.wait(timeout=duration + 30)
    except subprocess.TimeoutExpired:
        proc.kill()
    finally:
        if proc.poll() is None:
            proc.kill()


def _pcie_bandwidth_sat(duration: int, params: dict) -> None:
    mb = int(params.get("transfer_mb", "512"))
    code = (
        "import torch,time;"
        "d=torch.device('cuda');"
        f"n={mb}*1024*1024//4;"
        "host=torch.randn(n,pin_memory=True);"
        f"t=time.time()+{duration};"
        "exec(\""
        "while time.time()<t:\\n"
        " g=host.to(d,non_blocking=True);back=g.cpu();torch.cuda.synchronize()\")"
    )
    subprocess.run(["python3", "-c", code], check=False, timeout=duration + 30)


def _network_degradation(duration: int, params: dict) -> None:
    iface = subprocess.check_output(
        ["sh", "-c", "ip route | awk '/default/ {print $5; exit}'"]
    ).decode().strip()
    delay = params.get("delay", "100ms")
    subprocess.run(
        ["tc", "qdisc", "add", "dev", iface, "root", "netem", "delay", delay],
        check=False,
    )
    try:
        time.sleep(duration)
    finally:
        subprocess.run(
            ["tc", "qdisc", "del", "dev", iface, "root", "netem"], check=False
        )


def _cuda_process_kill(duration: int, params: dict) -> None:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"]
    ).decode().strip()
    killed = []
    for line in out.splitlines():
        pid = line.strip()
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode(errors="ignore")
            if any(name in cmd for name in SELF_PROTECT_NAMES):
                continue
            os.kill(int(pid), signal.SIGKILL)
            killed.append(pid)
        except (ProcessLookupError, FileNotFoundError, PermissionError):
            continue
    log(f"cuda_process_kill killed_pids={killed}")
    # Hold the marker for `duration` so the event has a measurable window.
    time.sleep(duration)


# ---------- dispatch ----------

DISPATCH = {
    "gpu_compute_stress": _gpu_compute_stress,
    "vram_pressure": _vram_pressure,
    "pcie_bandwidth_sat": _pcie_bandwidth_sat,
    "network_degradation": _network_degradation,
    "cuda_process_kill": _cuda_process_kill,
}


def execute_fault(fault_class: str, duration: int, params: dict) -> None:
    if fault_class not in DISPATCH:
        log(f"UNKNOWN class={fault_class}")
        return
    log(f"START class={fault_class} duration={duration} params={params}")
    ACTIVE_MARKER.write_text("1")
    CLASS_MARKER.write_text(fault_class)
    try:
        DISPATCH[fault_class](duration, params)
    except Exception as exc:
        log(f"ERROR class={fault_class} exc={exc}")
    finally:
        if ACTIVE_MARKER.exists():
            ACTIVE_MARKER.unlink()
        if CLASS_MARKER.exists():
            CLASS_MARKER.unlink()
        log(f"END class={fault_class}")
        _post_fault_watchdog(fault_class)


def _post_fault_watchdog(fault_class: str) -> None:
    """After disruptive faults, confirm the workload recovered."""
    if fault_class not in ("vram_pressure", "cuda_process_kill"):
        return
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if HEARTBEAT.exists() and HEARTBEAT.read_text().strip() == "1":
                log(f"WATCHDOG workload recovered after {fault_class}")
                return
        except Exception:
            pass
        time.sleep(5)
    log(f"WATCHDOG WARNING workload not recovered after {fault_class}")


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
