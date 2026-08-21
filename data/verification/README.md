# Cycle 1 Verification Slice

This directory lets a reader check the core execution claims of the testbed
without waiting for the full Cycle 1 dataset release. It is a curated slice,
not the complete dataset.

## `schedule_vs_executed.csv`

One row per pre-registered Cycle 1 event (1008 rows), reconciling the schedule
locked before T-zero against the on-host execution logs.

| column | meaning |
|---|---|
| `scheduled_iso` | timestamp from the pre-registered schedule |
| `host`, `fault_class`, `scheduled_duration_s` | as pre-registered |
| `observed_start`, `observed_end` | from the on-host execution log |
| `observed_duration_s` | measured execution duration |
| `start_deviation_s` | observed start minus scheduled start |
| `duration_error_s` | observed minus scheduled duration |
| `status` | `executed` if a paired START/END record was found, else `missing` |

The schedule itself is `protocols/fault_schedule_cycle1.csv`, unchanged since
the lock commit; its git history is the audit trail.

Reconciliation is one to one: 909 paired START/END records were found in the
Cycle 1 window and all 909 matched a distinct schedule row within a 300 s
tolerance. No execution was observed outside the pre-registered schedule.

Summary over the 909 executed events:

- Duration error: median +0.11 s, p95 +0.64 s, max +5.66 s, against scheduled
  durations averaging 1059 s.
- Start deviation: bounded in (-60, 0] s, median -30.6 s. This is the cron
  one-minute resolution limit, not jitter: the injector fires at the top of the
  minute containing the scheduled instant.

The first data row is the T-zero event plotted as Figure 2 of the CNSM 2026
submission, and reproduces the timings reported there.

## Reproducing

```
python3 analysis/adherence.py
```

Reads `protocols/fault_schedule_cycle1.csv` and the per-host execution logs,
and regenerates the CSV.

## Known limitations

- 99 events are marked `missing`. They are concentrated on `cnsm-web-01` and
  `cnsm-web-04`, whose cron scheduler was terminated by an out-of-memory
  condition during a `memory_pressure` fault in mid-July and did not resume.
  The dated analysis is in `lab_notebook/2026-08-21.md`.
- Telemetry is unavailable for 9 to 17 July 2026, when the monitoring master
  was inactive. Fault injection continued on the hosts during that window, so
  those events appear here as `executed`.

## In preparation

Raw telemetry windows for selected events, at the native 15 s cadence,
including `cnsm.fault.active` and `cnsm.fault.class` alongside the resource
items, so that label and signal can be checked against each other on a single
clock.

## License

Apache 2.0, as for the rest of this repository.
