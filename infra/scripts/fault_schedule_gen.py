#!/usr/bin/env python3
"""
Fault injection schedule generator for CNSM 2027 cross-environment study.

Generates a deterministic schedule of fault injections across all 12 study
hosts, using a fixed random seed for reproducibility.

Supports density multiplier to differentiate cycles of the three-cycle
research program:
- Cycle 1: density 1.0 (baseline)
- Cycle 2: density 1.5 (more diverse)
- Cycle 3: density 2.0 (stress)

The output schedule is committed to the repository BEFORE any data
collection begins, serving as pre-registration evidence against
p-hacking accusations.

Usage:
  # Cycle 1 (baseline)
  python3 fault_schedule_gen.py --start 2026-05-15 --days 90 --seed 42 \
      --density 1.0 --output protocols/fault_schedule_cycle1.csv

  # Cycle 2 (1.5x density)
  python3 fault_schedule_gen.py --start 2026-08-15 --days 90 --seed 43 \
      --density 1.5 --output protocols/fault_schedule_cycle2.csv

  # Cycle 3 (2.0x density)
  python3 fault_schedule_gen.py --start 2026-11-15 --days 90 --seed 44 \
      --density 2.0 --output protocols/fault_schedule_cycle3.csv

Output format (CSV):
  scheduled_iso,host,fault_class,duration_seconds,parameters
"""
from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOSTS = [
    "cnsm-web-01", "cnsm-web-02", "cnsm-web-03",
    "cnsm-web-04", "cnsm-web-05", "cnsm-web-06",
    "cnsm-db-postgres-01", "cnsm-db-postgres-02",
    "cnsm-db-redis-01", "cnsm-db-redis-02",
    "cnsm-mem-01", "cnsm-io-01",
]

# (class, weekly_freq_per_host, min_duration_s, max_duration_s)
FAULT_TYPES = [
    ("cpu_spike",        2, 300, 1800),
    ("memory_pressure",  1, 600, 3600),
    ("disk_io",          2, 300, 1200),
    ("network_latency",  1, 300, 1800),
    ("process_leak",     1, 300, 900),
]


@dataclass
class Fault:
    scheduled: datetime
    host: str
    fault_class: str
    duration_seconds: int
    parameters: str


def generate_parameters(fault_class: str, rng: random.Random) -> str:
    if fault_class == "cpu_spike":
        n = rng.choice([1, 2, 4])
        load = rng.choice([85, 90, 95])
        return f"cpu={n} load={load}"
    if fault_class == "memory_pressure":
        gb = rng.choice([1, 2, 4, 8])
        return f"vm_bytes={gb}G"
    if fault_class == "disk_io":
        n = rng.choice([2, 4, 8])
        return f"io={n} hdd={n}"
    if fault_class == "network_latency":
        ms = rng.choice([50, 100, 200, 500])
        return f"delay={ms}ms"
    if fault_class == "process_leak":
        n = rng.choice([2, 4, 8])
        return f"fork={n}"
    return ""


def generate_schedule(
    start: datetime,
    days: int,
    seed: int,
    density_multiplier: float = 1.0,
) -> list[Fault]:
    """
    Generate a deterministic fault injection schedule.

    Args:
        start: study start datetime (UTC)
        days: total study duration in days
        seed: random seed for reproducibility
        density_multiplier: scales the per-host weekly frequency.
            1.0 = baseline density (cycle 1)
            1.5 = 50% more events (cycle 2 with more diversity)
            2.0 = double events (cycle 3 with stress test focus)
    """
    rng = random.Random(seed)
    schedule: list[Fault] = []

    for host in HOSTS:
        for fault_class, weekly_freq, dmin, dmax in FAULT_TYPES:
            adjusted_freq = max(1, int(round(weekly_freq * density_multiplier)))
            total_injections = adjusted_freq * (days // 7)
            for _ in range(total_injections):
                # Random offset within the study window
                offset_seconds = rng.randint(0, days * 86400)
                scheduled = start + timedelta(seconds=offset_seconds)
                # Avoid overnight injections (constrain to 06:00..22:00 UTC)
                if scheduled.hour < 6 or scheduled.hour >= 22:
                    scheduled = scheduled.replace(
                        hour=rng.randint(6, 21), minute=rng.randint(0, 59)
                    )
                duration = rng.randint(dmin, dmax)
                params = generate_parameters(fault_class, rng)
                schedule.append(Fault(scheduled, host, fault_class, duration, params))

    schedule.sort(key=lambda f: (f.scheduled, f.host))
    return schedule


def write_csv(schedule: list[Fault], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["scheduled_iso", "host", "fault_class", "duration_seconds", "parameters"])
        for fault in schedule:
            writer.writerow([
                fault.scheduled.isoformat(),
                fault.host,
                fault.fault_class,
                fault.duration_seconds,
                fault.parameters,
            ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--density", type=float, default=1.0,
        help="Density multiplier (1.0=baseline, 1.5=more diverse, 2.0=stress)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    schedule = generate_schedule(start, args.days, args.seed, args.density)
    write_csv(schedule, args.output)

    print(f"Generated {len(schedule)} fault injections")
    print(f"Output: {args.output}")
    print(f"Density multiplier: {args.density}")
    print(f"Distribution by class:")
    counts: dict[str, int] = {}
    for f in schedule:
        counts[f.fault_class] = counts.get(f.fault_class, 0) + 1
    for cls, count in sorted(counts.items()):
        print(f"  {cls}: {count}")


if __name__ == "__main__":
    main()
