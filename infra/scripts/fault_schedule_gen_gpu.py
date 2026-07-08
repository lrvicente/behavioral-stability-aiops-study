#!/usr/bin/env python3
"""
GPU fault injection schedule generator for CNSM 2027 study, Sprint S2.

Generates a deterministic schedule for the single Lambda GPU host
(cnsm-gpu-01), covering the cross-environment fault injection window of
Sprint S2. Mirrors the OVH generator (fault_schedule_gen.py) conventions
(fixed seed, deterministic RNG, committed BEFORE collection as
pre-registration evidence) but uses:

  - six GPU fault classes reconciled to locked protocol section 5.2
  - DAILY frequencies per section 5.2 (not weekly like the OVH workers)
  - the 7-column GPU CSV schema:
      event_id,host,scheduled_iso,fault_class,duration_seconds,parameters,study
  - non-overlap enforcement: a single host with the injector's
    "SKIP another fault still active" guard means overlapping events would be
    silently dropped, so events are spaced with a minimum gap.

Frequencies (protocol 5.2, per day):
  gpu_utilization_spike           2/day
  gpu_memory_pressure             1/day
  disk_io_contention              1/day
  data_loader_bottleneck          1/day
  batch_inference_overload        1/day
  cpu_contention_during_training  1/day
  => 7 events/day * 28 days = 196 events (~200 per protocol)

Durations mirror the OVH equivalent class ranges via the 5.2.1 mapping;
cpu_contention_during_training (Lambda-only) uses its own range.

Usage:
  python3 fault_schedule_gen_gpu.py \
      --start 2026-07-10 --days 28 --seed 42 \
      --output protocols/fault_schedule_lambda_s2.csv
"""
from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOST = "cnsm-gpu-01"
STUDY_TAG = "cnsm2027-study"

# (class, per_day_freq, min_duration_s, max_duration_s)
# Durations mirror the mapped OVH class (5.2.1) where one exists.
FAULT_TYPES = [
    ("gpu_utilization_spike",          2, 300, 1800),   # <- cpu_spike range
    ("gpu_memory_pressure",            1, 600, 1800),   # <- memory_pressure (capped: A10 23GB)
    ("disk_io_contention",             1, 300, 1200),   # <- disk_io range
    ("data_loader_bottleneck",         1, 300, 1800),   # <- network_latency range
    ("batch_inference_overload",       1, 300, 900),    # <- process_leak range
    ("cpu_contention_during_training", 1, 300, 1200),   # Lambda-only
]

# Minimum gap (seconds) between the END of one fault and the START of the next,
# so the injector never hits "SKIP another fault still active".
MIN_GAP_S = 120

# Daytime window (UTC) to keep injections observable, matching OVH behaviour.
DAY_START_H = 6
DAY_END_H = 22


@dataclass
class Fault:
    scheduled: datetime
    fault_class: str
    duration_seconds: int
    parameters: str


def generate_parameters(fault_class: str, rng: random.Random) -> str:
    """Parameters use the class defaults validated 2026-07-08, with light
    deterministic variation where it is behaviourally meaningful."""
    if fault_class == "gpu_utilization_spike":
        size = rng.choice([6144, 8192, 10240])
        return f"matrix_size={size}"
    if fault_class == "gpu_memory_pressure":
        frac = rng.choice([0.80, 0.85, 0.90])
        return f"fraction={frac}"
    if fault_class == "disk_io_contention":
        numjobs = rng.choice([2, 4])
        iodepth = rng.choice([16, 32])
        return f"size=2G iodepth={iodepth} numjobs={numjobs}"
    if fault_class == "data_loader_bottleneck":
        thinktime = rng.choice([1000, 2000, 4000])
        numjobs = rng.choice([4, 8])
        return f"size=1G thinktime_us={thinktime} numjobs={numjobs}"
    if fault_class == "batch_inference_overload":
        conc = rng.choice([4, 6, 8])
        batch = rng.choice([64, 128])
        return f"concurrency={conc} infer_batch={batch}"
    if fault_class == "cpu_contention_during_training":
        load = rng.choice([80, 90, 100])
        return f"cpu=0 load={load}"
    return ""


def generate_schedule(start: datetime, days: int, seed: int) -> list[Fault]:
    """Deterministic per-day scheduling with non-overlap enforcement.

    For each day, we build the day's event list (2 spikes + 1 of each other
    class = 7 events), assign each a duration and params, then lay them out
    sequentially within the daytime window with random but non-overlapping
    start times (min gap between them). This guarantees the injector executes
    every scheduled event."""
    rng = random.Random(seed)
    schedule: list[Fault] = []

    # Build the per-day class multiset once (order shuffled per day for variety).
    day_classes: list[tuple[str, int, int]] = []
    for cls, per_day, dmin, dmax in FAULT_TYPES:
        for _ in range(per_day):
            day_classes.append((cls, dmin, dmax))

    for day in range(days):
        day_start = (start + timedelta(days=day)).replace(
            hour=DAY_START_H, minute=0, second=0, microsecond=0
        )
        day_end = (start + timedelta(days=day)).replace(
            hour=DAY_END_H, minute=0, second=0, microsecond=0
        )

        # Shuffle class order for this day (deterministic via seeded rng).
        todays = day_classes[:]
        rng.shuffle(todays)

        # Assign durations first, then compute required total span.
        events = []
        for cls, dmin, dmax in todays:
            dur = rng.randint(dmin, dmax)
            params = generate_parameters(cls, rng)
            events.append((cls, dur, params))

        total_busy = sum(d for _, d, _ in events)
        total_gaps = MIN_GAP_S * (len(events) - 1)
        window = int((day_end - day_start).total_seconds())
        slack = window - total_busy - total_gaps

        if slack < 0:
            # Day is over-subscribed: compress gaps to fit (rare with these
            # ranges, but guard anyway). Fall back to zero extra slack.
            slack = 0

        # Distribute the slack as random spacing before each event.
        # extra[i] = random extra idle inserted before event i.
        cuts = sorted(rng.randint(0, slack) for _ in range(len(events)))
        prev_extra = 0
        cursor = day_start
        for i, (cls, dur, params) in enumerate(events):
            extra = cuts[i] - prev_extra
            prev_extra = cuts[i]
            cursor = cursor + timedelta(seconds=extra)
            schedule.append(Fault(cursor, cls, dur, params))
            cursor = cursor + timedelta(seconds=dur + MIN_GAP_S)

    schedule.sort(key=lambda f: f.scheduled)
    return schedule


def write_csv(schedule: list[Fault], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["event_id", "host", "scheduled_iso", "fault_class",
             "duration_seconds", "parameters", "study"]
        )
        for i, fault in enumerate(schedule, 1):
            writer.writerow([
                f"gpu-s2-{i:04d}",
                HOST,
                fault.scheduled.isoformat(),
                fault.fault_class,
                fault.duration_seconds,
                fault.parameters,
                STUDY_TAG,
            ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    schedule = generate_schedule(start, args.days, args.seed)
    write_csv(schedule, args.output)

    print(f"Generated {len(schedule)} GPU fault injections over {args.days} days")
    print(f"Output: {args.output}")
    print(f"Seed: {args.seed}  Host: {HOST}  Study: {STUDY_TAG}")
    counts: dict[str, int] = {}
    for f in schedule:
        counts[f.fault_class] = counts.get(f.fault_class, 0) + 1
    print("Distribution by class:")
    for cls, count in sorted(counts.items()):
        print(f"  {cls}: {count}")
    # Sanity: report min inter-event gap actually produced.
    gaps = []
    for a, b in zip(schedule, schedule[1:]):
        gap = (b.scheduled - (a.scheduled + timedelta(seconds=a.duration_seconds))).total_seconds()
        gaps.append(gap)
    if gaps:
        print(f"Min gap between events: {min(gaps):.0f}s (should be >= 0)")


if __name__ == "__main__":
    main()
