#!/usr/bin/env python3
"""Cycle 1 telemetry windows for selected fault events.

Reads data/verification/schedule_vs_executed.csv, selects a small set of
events, and extracts the raw telemetry around each one from the nightly S3
exports. Writes one CSV per event plus an index.
"""
import csv
import gzip
import io
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta

REPO = os.path.expanduser("~/cnsm2027/behavioral-stability-aiops-study")
OUT = os.path.join(REPO, "data/verification/events")
BUCKET = "s3://cnsm2027-study/raw/zabbix/daily"
S3ARGS = ["--profile", "ovh-cnsm",
          "--endpoint-url", "https://s3.gra.io.cloud.ovh.net"]
KEEP = ("cnsm.", "system.cpu", "vm.memory", "system.load",
        "vfs.dev", "proc.num")
WINDOW_MIN = 30
P = lambda s: datetime.fromisoformat(s)


def s3_get(day, name):
    uri = BUCKET + "/" + day.replace("-", "/") + "/" + name
    r = subprocess.run(["aws", "s3", "cp", uri, "-"] + S3ARGS,
                       capture_output=True)
    if r.returncode:
        raise IOError(uri + ": " + r.stderr.decode()[:150])
    return r.stdout


def select(rows):
    ex = [r for r in rows if r["status"] == "executed"]
    out = []
    for r in ex:
        if r["scheduled_iso"].startswith("2026-05-15T06:14"):
            out.append(("paper_tzero_fig2", r))
    seen = set()
    for cls in ("cpu_spike", "disk_io", "memory_pressure",
                "network_latency", "process_leak"):
        for r in ex:
            if r["fault_class"] != cls or r["host"] in seen:
                continue
            if any(r is o[1] for o in out):
                continue
            out.append(("class_" + cls, r))
            seen.add(r["host"])
            break
    for host in ("cnsm-web-01", "cnsm-web-04"):
        c = [r for r in rows if r["host"] == host
             and r["status"] == "missing"
             and r["scheduled_iso"] > "2026-07-19"]
        if c:
            r = dict(c[0])
            st = P(r["scheduled_iso"])
            r["observed_start"] = st.isoformat()
            r["observed_end"] = (st + timedelta(
                seconds=int(r["scheduled_duration_s"]))).isoformat()
            out.append(("silent_absence_" + host, r))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(REPO, "data/verification/schedule_vs_executed.csv")
    rows = list(csv.DictReader(open(src)))
    jobs = defaultdict(list)
    index = []
    for tag, r in select(rows):
        t0 = P(r["observed_start"]) - timedelta(minutes=WINDOW_MIN)
        t1 = P(r["observed_end"]) + timedelta(minutes=WINDOW_MIN)
        for d in sorted({t0.strftime("%Y-%m-%d"), t1.strftime("%Y-%m-%d")}):
            jobs[d].append((tag, r["host"], int(t0.timestamp()),
                            int(t1.timestamp())))
        index.append({"tag": tag, "host": r["host"],
                      "fault_class": r["fault_class"],
                      "scheduled_iso": r["scheduled_iso"],
                      "observed_start": r["observed_start"],
                      "observed_end": r["observed_end"],
                      "duration_error_s": r["duration_error_s"],
                      "status": r["status"],
                      "window_basis": "scheduled window, event did not "
                      "execute" if r["status"] == "missing"
                      else "observed execution window"})
    counts = defaultdict(int)
    for day in sorted(jobs):
        try:
            blob = s3_get(day, "history.jsonl.gz")
        except IOError as e:
            print("  pulado " + str(e))
            continue
        handles = {}
        for tag, host, lo, hi in jobs[day]:
            path = os.path.join(OUT, tag + ".csv")
            new = not os.path.exists(path)
            fh = open(path, "a", newline="")
            w = csv.writer(fh)
            if new:
                w.writerow(["timestamp_utc", "host", "item_key", "value"])
            handles[tag] = (w, fh, host, lo, hi)
        with gzip.open(io.BytesIO(blob), "rt") as gz:
            for line in gz:
                rec = json.loads(line)
                if not rec["item_key"].startswith(KEEP):
                    continue
                c = rec["clock"]
                for tag, (w, fh, host, lo, hi) in handles.items():
                    if rec["host"] == host and lo <= c <= hi:
                        w.writerow([rec["clock_iso"], rec["host"],
                                    rec["item_key"], rec["value"]])
                        counts[tag] += 1
        for tag, (w, fh, host, lo, hi) in handles.items():
            fh.close()
        print("  " + day + " ok")
    for e in index:
        e["samples"] = counts.get(e["tag"], 0)
    with open(os.path.join(OUT, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
    print("")
    for e in index:
        print("  %-26s %7d amostras" % (e["tag"], e["samples"]))


main()
