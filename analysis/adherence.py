#!/usr/bin/env python3
"""Cycle 1 schedule adherence.

Reconciles the pre-registered fault schedule against the on-host execution
logs and writes data/verification/schedule_vs_executed.csv.
"""
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

REPO = os.path.expanduser("~/cnsm2027/behavioral-stability-aiops-study")
LOGS = os.path.expanduser("~/cnsm2027/rebuttal/full")
OUT = os.path.join(REPO, "data/verification")
P = lambda s: datetime.fromisoformat(s)


def load_executions():
    out = defaultdict(list)
    files = sorted(glob.glob(os.path.join(LOGS, "*/tmp/exec_full.log")))
    if not files:
        sys.exit("nenhum log encontrado em " + LOGS)
    for f in files:
        host = f.split("/")[-3]
        act = None
        for ln in open(f):
            p = ln.split()
            if len(p) < 2:
                continue
            if p[1] == "START":
                m = re.search(r"class=(\S+).*?duration=(\d+)", ln)
                if m:
                    act = [P(p[0]), m.group(1), int(m.group(2))]
            elif p[1] == "END" and act:
                if "2026-05-15" <= act[0].isoformat()[:10] <= "2026-08-12":
                    out[host].append((act[0], act[1], act[2], P(p[0])))
                act = None
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    sched_path = os.path.join(REPO, "protocols/fault_schedule_cycle1.csv")
    sched = list(csv.DictReader(open(sched_path)))
    execs = load_executions()
    rows = []
    n = 0
    used = set()
    for r in sched:
        st = P(r["scheduled_iso"])
        host = r["host"]
        dur = int(r["duration_seconds"])
        best = None
        for i, e in enumerate(execs.get(host, [])):
            if (host, i) in used:
                continue
            d = abs((e[0] - st).total_seconds())
            if d <= 300 and (best is None or d < best[0]):
                best = (d, e, i)
        if best:
            e = best[1]
            used.add((host, best[2]))
            obs = (e[3] - e[0]).total_seconds()
            n += 1
            rows.append([r["scheduled_iso"], host, r["fault_class"], dur,
                         e[0].isoformat(), e[3].isoformat(),
                         "%.2f" % obs,
                         "%.2f" % (e[0] - st).total_seconds(),
                         "%+.2f" % (obs - dur), "executed"])
        else:
            rows.append([r["scheduled_iso"], host, r["fault_class"], dur,
                         "", "", "", "", "", "missing"])
    out_path = os.path.join(OUT, "schedule_vs_executed.csv")
    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scheduled_iso", "host", "fault_class",
                    "scheduled_duration_s", "observed_start", "observed_end",
                    "observed_duration_s", "start_deviation_s",
                    "duration_error_s", "status"])
        w.writerows(rows)
    err = sorted(float(x[8]) for x in rows if x[9] == "executed")
    dev = sorted(float(x[7]) for x in rows if x[9] == "executed")
    q = lambda a, p: a[int(len(a) * p)]
    print(out_path)
    print("  execucoes pareadas nos logs (janela C1): %d"
          % sum(len(v) for v in execs.values()))
    print("  %d de %d pareados (%.1f%%)"
          % (n, len(sched), 100.0 * n / len(sched)))
    print("  erro duracao s: p50 %+.2f  p95 %+.2f  max %+.2f"
          % (q(err, .5), q(err, .95), err[-1]))
    print("  desvio inicio s: p50 %.1f  p95 %.1f"
          % (q(dev, .5), q(dev, .95)))


main()
