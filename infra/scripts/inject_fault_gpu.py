#!/usr/bin/env python3
"""
GPU fault injection executor for CNSM 2027 study (cnsm-gpu-01 only).

Mirrors inject_fault.py: runs via cron every minute, reads the local
schedule CSV, executes any GPU fault due within the window. Writes the
same ground-truth markers (/var/run/cnsm-fault-active, cnsm-fault-class)
consumed by Zabbix, keeping the GPU node consistent with the workers.

Six GPU fault classes, reconciled to the locked protocol section 5.2
(EXPERIMENTAL_SETUP.md) and the 5.2.1 cross-environment mapping:

  gpu_utilization_spike           compute_saturation  (<- OVH cpu_spike)
  gpu_memory_pressure             memory_pressure     (<- OVH memory_pressure)
  disk_io_contention              io_bottleneck       (<- OVH disk_io)
  data_loader_bottleneck          network_degradation (<- OVH network_latency)
  batch_inference_overload        process_instability (<- OVH process_leak)
  cpu_contention_during_training  Lambda-only, excluded from paired analysis

Design constraint: the injector runs as a SEPARATE process via cron and must
not restart the resnet50 training process. IO/loader faults therefore act on
the shared NFS dataset mount the DataLoader reads from; inference overload
spawns concurrent CUDA processes contending for SM/VRAM.
"""
from __future__ import annotations

import argparse
import csv
import os
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

DATASET_DIR = "/lambda/nfs/cnsm-gpu-01-fs/cnsm-study/data"
IO_SCRATCH = "/lambda/nfs/cnsm-gpu-01-fs/cnsm-study/faultio"

DISRUPTIVE = ("gpu_memory_pressure", "batch_inference_overload")


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

def _gpu_utilization_spike(duration: int, params: dict) -> None:
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


def _gpu_memory_pressure(duration: int, params: dict) -> None:
    frac = float(params.get("fraction", "0.95"))
    code = (
        "import torch,time;"
        "d=torch.device('cuda');"
        "free,total=torch.cuda.mem_get_info();"
        f"target=int(total*{frac});"
        "blocks=[];"
        "step=256*1024*1024;"
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


def _disk_io_contention(duration: int, params: dict) -> None:
    """io_bottleneck. Protocol 5.2: 'fio stress on the SSD while data loader
    reads'. Persistent layout + fio self-timeout so the timed run never pays the
    NFS file-creation cost."""
    os.makedirs(IO_SCRATCH, exist_ok=True)
    size = params.get("size", "2G")
    cmd = [
        "fio",
        "--name=cnsm_disk_io_contention",
        f"--directory={IO_SCRATCH}",
        "--rw=randrw", "--rwmixread=70",
        "--bs=64k",
        f"--size={size}",
        "--iodepth=" + params.get("iodepth", "16"),
        "--numjobs=" + params.get("numjobs", "4"),
        "--ioengine=libaio",
        "--direct=1",
        "--group_reporting",
        f"--runtime={duration}", "--time_based",
        f"--timeout={duration}",
        "--allow_file_create=1",
        "--unlink=0",
        "--minimal",
    ]
    try:
        subprocess.run(cmd, check=False, timeout=duration + 180)
    except subprocess.TimeoutExpired:
        subprocess.run(["pkill", "-f", "cnsm_disk_io_contention"], check=False)


def _data_loader_bottleneck(duration: int, params: dict) -> None:
    """network_degradation concept. Protocol 5.2: 'artificial latency in data
    loading pipeline'. Mechanism: high-latency small random reads on the dataset
    mount, maximizing the per-op latency the DataLoader feels while reading
    shards. Chosen over tc netem because it is self-contained (no NIC topology
    assumptions) and validated 2026-07-08. Persistent layout + fio self-timeout,
    same pattern as disk_io_contention."""
    os.makedirs(IO_SCRATCH, exist_ok=True)
    cmd = [
        "fio",
        "--name=cnsm_data_loader_bottleneck",
        f"--directory={IO_SCRATCH}",
        "--rw=randread",
        "--bs=4k",
        "--size=" + params.get("size", "1G"),
        "--iodepth=" + params.get("iodepth", "1"),
        "--numjobs=" + params.get("numjobs", "8"),
        "--ioengine=libaio",
        "--direct=1",
        "--thinktime=" + params.get("thinktime_us", "2000"),
        "--thinktime_blocks=1",
        "--group_reporting",
        f"--runtime={duration}", "--time_based",
        f"--timeout={duration}",
        "--allow_file_create=1",
        "--unlink=0",
        "--minimal",
    ]
    try:
        subprocess.run(cmd, check=False, timeout=duration + 180)
    except subprocess.TimeoutExpired:
        subprocess.run(["pkill", "-f", "cnsm_data_loader_bottleneck"], check=False)


def _batch_inference_overload(duration: int, params: dict) -> None:
    """process_instability concept. Protocol 5.2: 'excessive concurrent
    inference requests'. Spawn N concurrent resnet50 inference processes on the
    same GPU, contending with training for SM time and VRAM."""
    n = int(params.get("concurrency", "6"))
    infer_batch = params.get("infer_batch", "128")
    worker_code = (
        "import torch,torchvision,time;"
        "d=torch.device('cuda');"
        "m=torchvision.models.resnet50().to(d).eval();"
        f"b=int({infer_batch});"
        "x=torch.randn(b,3,224,224,device=d);"
        f"end=time.time()+{duration};"
        "exec(\"\"\"\n"
        "with torch.no_grad():\n"
        " while time.time()<end:\n"
        "  y=m(x);torch.cuda.synchronize()\n"
        "\"\"\")"
    )
    procs = []
    try:
        for _ in range(n):
            procs.append(subprocess.Popen(["python3", "-c", worker_code]))
        deadline = time.time() + duration + 30
        for p in procs:
            remaining = max(1, int(deadline - time.time()))
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()


def _cpu_contention_during_training(duration: int, params: dict) -> None:
    """Lambda-only (5.2.1: excluded from paired SHAP analysis, kept for
    within-Lambda metrics). Protocol 5.2: 'stress-ng --cpu on host CPUs while
    GPU training runs'."""
    cpu = params.get("cpu", "0")
    load = params.get("load", "90")
    cmd = [
        "stress-ng", "--cpu", cpu,
        "--cpu-load", load,
        "--timeout", str(duration),
    ]
    subprocess.run(cmd, check=False, timeout=duration + 30)


# ---------- dispatch ----------

DISPATCH = {
    "gpu_utilization_spike": _gpu_utilization_spike,
    "gpu_memory_pressure": _gpu_memory_pressure,
    "disk_io_contention": _disk_io_contention,
    "data_loader_bottleneck": _data_loader_bottleneck,
    "batch_inference_overload": _batch_inference_overload,
    "cpu_contention_during_training": _cpu_contention_during_training,
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
    if fault_class not in DISRUPTIVE:
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
