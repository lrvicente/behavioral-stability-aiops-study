# GPU Node Setup — cnsm-gpu-01 (Lambda A10)

CNSM/NOMS 2027 behavioral stability study — heterogeneous GPU node addition.

Date: 2026-05-28 (Cycle 1 pre-pilot window, 27–29 May).
Operator: Lucas Renan Vicente Bandeira.

## Purpose

Add a heterogeneous GPU node to the cross-environment testbed. Until now the
testbed consisted of 12 homogeneous OVH VPS workers (web/db/memory/io). The GPU
node introduces hardware heterogeneity (NVIDIA A10) while keeping the collection
mechanism identical to the workers, so that the only differing variable is the
hardware class. This strengthens the generalization of the behavioral-stability
thesis.

## Instance

- Host: cnsm-gpu-01
- Provider: Lambda Cloud (GPU-only voucher, non-fungible; OVH voucher preserved).
- Type: 1x A10 (24 GB PCIe), 30 vCPU, ~200 GiB RAM, 1.4 TB SSD.
- Region: us-east-1 (Virginia) — closest available to OVH master/S3 in Gravelines.
- Public IP: 129.80.21.156
- Base image: Lambda Stack 24.04 (Ubuntu 24.04.4 LTS — matches master/workers).
- Persistent filesystem: cnsm-gpu-01-fs (us-east-1), elastic, \$0.20/GB/month.
- GPU stack: driver 580.105.08, CUDA 13.0, PyTorch 2.7.0.

## Access / credentials

Three SSH keys authorized: cnsm-gpu-key (operator PC), master-ansible-key
(automation, generated on master), cnsm2027_ed25519 (same key as the 12 workers,
so Ansible treats the GPU node like any study host).

Firewall (Lambda global rules): inbound TCP 22 + ICMP open; inbound TCP 10050
opened to 137.74.116.37/32 only (master), required for Zabbix passive checks. No
agent PSK, so the /32 restriction is the only protection on 10050.

Backlog: restrict SSH (22) to operator + master IPs instead of 0.0.0.0/0.

## Ansible isolation design

The GPU node is deliberately NOT in study_hosts. It lives in its own [gpu]
group. Rationale: worker playbooks target study_hosts and carry the worker fault
schedule (seed 42, CPU/web/io/memory classes); if the GPU node were in
study_hosts those could touch it by accident and contaminate the live cycle-1
collection. Every GPU step is a hosts: gpu playbook:

- 00-bootstrap-gpu.yml — baseline (role common).
- 10-zabbix-gpu.yml — agent 2 7.0.26 + dual-write + 9 common UserParameters;
  HostMetadata derives "cnsm2027-study gpu" from group name.
- 15-gpu-userparameters.yml — 15 nvidia-smi metrics via systemd-timer cache (10s).
- 20-workload-gpu.yml — role workload_gpu.
- 25-heartbeat-gpu.yml — workload heartbeat sidecar.
- 30-fault-injector-gpu.yml — GPU fault injection (pending).

## Monitoring

Registered in master Zabbix as cnsm-gpu-01, groups cnsm2027-study and
cnsm2027-study/gpu, templates "Linux by Zabbix agent active" + "Template CNSM
Study Custom" + "Template CNSM GPU" (15 GPU items). All collection via active
checks, identical to workers.

GPU idle baseline: util 0%, mem_used 0 MiB, temp ~28 °C, power ~15 W, pcie_gen 1.

## Workload (baseline of normalcy)

Role workload_gpu: continuous ResNet50 inference loop (PyTorch, synthetic
tensors, seed 142), systemd service cnsm-workload, batch 64, self-calibrating.
Duty-cycle controlled to oscillate util 50–85% on a 15-min sinusoidal period
(realistic yet stable). Sprint load profiles (training/ablation) deferred.

Observed under load: util 50–85%, mem_used ~1427 MiB, temp ~41 °C, power ~140 W,
pcie_gen rises 1 → 4.

## Fault injection — 5 GPU classes

Separate executor infra/scripts/inject_fault_gpu.py (mirrors inject_fault.py:
same CSV format, same ground-truth markers, cron every minute). Classes mapped
1:1 from worker classes:

- gpu_compute_stress  (matmul loop)              <- cpu_spike
- vram_pressure       (alloc VRAM to fraction)    <- memory_pressure
- pcie_bandwidth_sat  (host<->device transfers)   <- disk_io
- network_degradation (tc netem, identical)       <- network_latency
- cuda_process_kill   (SIGKILL CUDA procs)        <- process_leak

Safety: vram_pressure allocates in a child process (OS reclaims all VRAM on
exit); cuda_process_kill self-protects (never kills injector/metrics/zabbix);
post-fault watchdog confirms workload recovery after vram_pressure and
cuda_process_kill.

### Validated fault signatures (manual tests, 2026-05-28)

- gpu_compute_stress: util pinned 100%, stable; temp 28->64 C; power ~150 W.
- pcie_bandwidth_sat: util 79-98% oscillating; pcie_gen 4. Distinguished from
  compute_stress mainly by variance, not absolute level.
- network_degradation: +100 ms latency (ping 0.4 -> 101 ms); netem cleanly
  removed; GPU unaffected.
- vram_pressure (0.95): mem_used -> 22396 MiB (97%), free -> 193 MiB; workload
  survived (no OOM — chosen as cleaner behavior); VRAM fully released afterward.
- cuda_process_kill: GPU 0% / 0 MiB for ~8 s, then recovers; killed only the
  workload PID; watchdog confirmed recovery.

All five correctly raised/cleared the ground-truth markers.

## Pre-pilot schedule

protocols/pre_pilot_schedule.csv — 10 events (5 classes x 2 days), manual, seed
142 namespace. Day 1 (28/05): 5 short events (5 min). Day 2 (29/05): 5 events
with larger durations / varied parameters. Manual schedule chosen because
fault_schedule_gen.py targets long windows (days//7 weeks) and yields zero events
for a 3-day window. A GPU-adapted generator (seed 142) is deferred to the sprints.

## Open items / pending

- Role fault_injector_gpu + playbook 30-fault-injector-gpu.yml (in progress).
- Pre-registration amendment v1.1: document GPU node addition, 5 GPU classes,
  workload, hostname/entry date — to be filed AFTER pre-pilot validation.
- Decide sprint load profiles (training vs inference); reconcile with Gantt
  labels (S1 "training", S2 "steady-state").
- Update Gantt cost line: computed on OVH a10-45 (EUR 0.76/h); actual is Lambda
  A10 (\$1.29/h ~= \$4,922 for the 3-cycle GPU program, within \$7,500 voucher).
- Remove /tmp test artifacts (test_gpu_faults.py, test_schedule.csv).
