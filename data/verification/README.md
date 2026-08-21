# Cycle 1 Verification Slice

This directory lets a reader check the core claims of the testbed without
waiting for the full Cycle 1 dataset release. It is a curated slice, not the
complete dataset.

## schedule_vs_executed.csv

One row per pre-registered Cycle 1 event (1008 rows), reconciling the schedule
locked before T-zero against the on-host execution logs. Columns: scheduled_iso,
host, fault_class, scheduled_duration_s, observed_start, observed_end,
observed_duration_s, start_deviation_s, duration_error_s, status. status is
executed if a paired START/END record was found, else missing.

Reconciliation is one to one: 909 paired START/END records were found in the
Cycle 1 window and all 909 matched a distinct schedule row within a 300 s
tolerance. No execution was observed outside the pre-registered schedule.

Over the 909 executed events, duration error has median +0.11 s, p95 +0.64 s,
max +5.66 s, against scheduled durations averaging 1059 s. Start deviation is
bounded in (-60, 0] s, median -30.6 s: this is the cron one-minute resolution
limit, not jitter, since the injector fires at the top of the minute containing
the scheduled instant.

## events/

Raw telemetry windows for eight events, at the native cadence, covering the
fault plus 30 minutes on each side. Each CSV has columns timestamp_utc, host,
item_key, value. events/index.json maps each window to its schedule row.

Cadence note: cnsm.fault.active is sampled every 15 s; cnsm.fault.class and
cnsm.workload.heartbeat are sampled every 60 s. The resource items follow their
own Zabbix intervals. The camera-ready will state these per-item cadences
precisely.

Two window types are present, distinguished by window_basis in the index:

Executed events (observed execution window). Six windows: the T-zero event
plotted as Figure 2 of the CNSM 2026 submission, and one event per fault class.
In each, cnsm.fault.active transitions 0 to 1 to 0 and cnsm.fault.class reports
the executing class, alongside the resource response. The T-zero window
reproduces the timings and the marker transition shown in Figure 2.

Silent-absence events (scheduled window, event did not execute). Two windows on
cnsm-web-01 and cnsm-web-04, taken after the monitoring master was restored on
18 July, at times where the pre-registered schedule specifies a fault but the
execution log has no record. Throughout each window cnsm.fault.active stays 0,
cnsm.fault.class reports none, and cnsm.workload.heartbeat stays 1: the host is
up and serving, the monitoring plane shows nothing wrong, and only
reconciliation against the frozen schedule reveals that the event never ran.
These two hosts had their cron scheduler terminated by an out-of-memory
condition during a memory_pressure fault in mid-July; see
lab_notebook/2026-08-21.md for the dated root-cause analysis.

## Reproducing

Run: python3 analysis/adherence.py to regenerate schedule_vs_executed.csv, and
python3 analysis/telemetry_windows.py to regenerate events/ from the S3 exports.

## Redactions

IPv4 addresses have been removed from any copied metadata. Telemetry values,
timestamps and item keys are verbatim from the preserved nightly exports; no
aggregation or resampling was applied inside the published windows beyond the
item selection above.

## License

Apache 2.0, as for the rest of this repository.
