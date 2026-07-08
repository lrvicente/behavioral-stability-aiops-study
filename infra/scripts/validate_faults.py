#!/usr/bin/env python3
"""
Validation runner for the reconciled GPU fault injector (CNSM 2027 S2).

Invokes ONE fault primitive at a time (60s each by default), directly from
inject_fault_gpu.py, without cron and without the schedule CSV. Between each
class it prints a 5s cooldown so you can watch nvidia-smi / Zabbix cleanly.

Run on cnsm-gpu-01:
  sudo python3 /opt/cnsm-study/scripts/validate_faults.py
  sudo python3 /opt/cnsm-study/scripts/validate_faults.py --only disk_io_contention
  sudo python3 /opt/cnsm-study/scripts/validate_faults.py --duration 90

Watch in a second SSH pane:
  watch -n1 nvidia-smi
  tail -f /var/log/cnsm-faults/executions.log
  watch -n1 'cat /var/run/cnsm-fault-active /var/run/cnsm-fault-class 2>/dev/null'
"""
import argparse
import importlib.util
import sys
import time

INJECTOR = "/opt/cnsm-study/scripts/inject_fault_gpu.py"

# class -> validation params (short, safe for a 60s probe)
VALIDATION = [
    ("gpu_utilization_spike",          {"matrix_size": "8192"}),
    ("gpu_memory_pressure",            {"fraction": "0.90"}),
    ("disk_io_contention",             {"size": "4G", "iodepth": "16", "numjobs": "4"}),
    ("data_loader_bottleneck",         {"mechanism": "fio", "thinktime_us": "2000", "numjobs": "8"}),
    ("batch_inference_overload",       {"concurrency": "6", "infer_batch": "128"}),
    ("cpu_contention_during_training", {"cpu": "0", "load": "90"}),
]


def load_injector():
    spec = importlib.util.spec_from_file_location("inj", INJECTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--only", default=None, help="run a single class by name")
    ap.add_argument("--cooldown", type=int, default=5)
    args = ap.parse_args()

    inj = load_injector()

    targets = VALIDATION
    if args.only:
        targets = [(c, p) for c, p in VALIDATION if c == args.only]
        if not targets:
            print(f"unknown class: {args.only}")
            print("available:", ", ".join(c for c, _ in VALIDATION))
            return 1

    for cls, params in targets:
        print(f"\n===== {cls} ({args.duration}s) params={params} =====", flush=True)
        t0 = time.time()
        # execute_fault handles markers + watchdog exactly as production would
        inj.execute_fault(cls, args.duration, params)
        print(f"----- {cls} done in {time.time()-t0:.1f}s -----", flush=True)
        if len(targets) > 1:
            print(f"cooldown {args.cooldown}s...", flush=True)
            time.sleep(args.cooldown)

    print("\nvalidation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
