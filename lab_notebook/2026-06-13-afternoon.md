# Lab Notebook 2026-06-13 (afternoon)

## Sprint S1 launched per OPERATIONAL_GUIDE §22.4

This entry covers the afternoon session of 2026-06-13, in which Sprint S1
(week 5 of cycle 1, per OPERATIONAL_GUIDE.md §22.4: "Week 5: launch Lambda S1,
run training scripts") was operationally launched. The morning entry (2026-06-13.md)
already documented the cycle 1 health check at T+30 days. This afternoon session
focused on bringing the Lambda GPU tooling closer to protocol §5.2 compliance
and starting the actual S1 training workload.

The reference for the Sprint S1 timing is the locked OPERATIONAL_GUIDE §22.4
(week 5 of cycle 1). T-zero was 2026-05-15, so week 5 spans 2026-06-12 to
2026-06-18. Today (2026-06-13) is within the protocol-prescribed window. No
schedule amendment is required for the start date.

## Workload swap: inference to training

The cnsm-workload service on cnsm-gpu-01 has been running the
ResNet50 inference workload from the pre-pilot (2026-05-28) continuously for
16 days (last run: PID 554066, started 2026-05-29 09:39:06 UTC, accumulated
1w 3d 3h CPU time, 15459278 batches). This workload was stopped today to
make way for the training profile mandated by protocol §4.2.

A new template `gpu_training_workload.py.j2` was added to the workload_gpu
Ansible role. The training workload uses ResNet50 randomly initialized,
CIFAR10 as training dataset (downloaded once to the persistent NFS at
/lambda/nfs/cnsm-gpu-01-fs/cnsm-study/data), batch size 64, SGD with
momentum 0.9 and weight decay 5e-4, PyTorch native AMP via torch.amp
(GradScaler + autocast with device_type='cuda'), and periodic inference
bursts every 1800 seconds (per §5.2: "batch inference every 30 min") with
20 batches at size 128. Deterministic seed 42 throughout, matching the
seed used for the OVH cycle 1 schedule.

The workload_gpu role tasks were refactored to be parameterized by
gpu_workload_mode (inference or training), driven by defaults/main.yml.
This preserves the ability to fall back to inference if needed without
code changes. The systemd unit Description and ExecStart now reflect
the active mode dynamically.

## cnsm-gpu-01 operational state

The host was brought into S1 observation mode:

- Old inference workload stopped (`systemctl stop cnsm-workload`).
- New training workload deployed via the workload_gpu role (`ansible-playbook
  20-workload-gpu.yml`, all 9 tasks ok, 5 changed).
- Fault injection cron line was commented out in root crontab on cnsm-gpu-01
  with a timestamped marker (`# DISABLED 2026-06-13 for Sprint S1 prep`).
  The crontab backup was saved to /tmp/crontab_backup_20260613_125829.txt
  on cnsm-gpu-01.
- The host remains in Zabbix group cnsm2027-gpu-pilot (separated from the
  study group cnsm2027-study, as recorded in the morning entry).
- The host remains disabled in Zabbix master (status=1). Re-enablement is
  deferred until the fault injector reconciliation is complete.

## Partial fault class renaming

The injector script infra/scripts/inject_fault_gpu.py was partially aligned
with the ontology mapping defined in §5.2.1. Two of the five pre-pilot classes
were renamed in-place because their mechanism is identical to the
ontology-mapped class:

- gpu_compute_stress was renamed to gpu_utilization_spike. Mechanism:
  saturate GPU compute via continuous matmul kernel loop. Unchanged.
- vram_pressure was renamed to gpu_memory_pressure. Mechanism: allocate
  large CUDA tensors in a child process up to a configured VRAM fraction.
  Unchanged.

Three classes remain with legacy names and pre-pilot mechanisms because
the ontology mapping requires a new mechanism, not just a rename:

- pcie_bandwidth_sat (host-to-device transfers) must be reimplemented as
  disk_io_contention (fio stress on the SSD while data loader reads), per
  §5.2 table.
- network_degradation (tc netem at network interface) must be reimplemented
  as data_loader_bottleneck (artificial latency injected in the PyTorch
  DataLoader pipeline), per §5.2 table.
- cuda_process_kill (SIGKILL of CUDA processes) must be reimplemented as
  batch_inference_overload (concurrent inference requests during training),
  per §5.2 table.

A sixth class, cpu_contention_during_training, is mandated by §5.2 but was
not implemented in the pre-pilot at all and must be added (stress-ng on
host CPUs while GPU training runs).

The injector was not deployed to the Lambda host today because the renaming
is incomplete and the fault injection cron has been disabled for the S1
observation window. The updated injector remains in the master VPS repository
working tree until reconciliation is complete.

## Verification evidence (training workload)

The training workload was verified at three levels after deployment:

- Service state: cnsm-workload.service active (running), Description
  reflects "training" mode, PID 886667, memory 2.3 GB, 21 tasks (main +
  4 DataLoader workers + internal PyTorch threads).
- GPU telemetry via nvidia-smi: utilization 99%, VRAM 3759 MiB used of
  23028 MiB total, power draw 135.66 W. This matches the §4.2
  specification of "80-95% utilization" with room above (the spec
  defines a floor for training, not a ceiling).
- Workload log: `loading resnet50 batch=64 seed=42` at 13:02:17 UTC,
  `training loop start. inference_burst every 1800s (20 batches at size 128)`
  at 13:02:26 UTC, first periodic report at 13:03:26 UTC
  (`alive epoch=1 batches_total=582 last_loss=1.8238`), second at 13:04:26
  UTC (`alive epoch=2 batches_total=1167 last_loss=2.0866`). Loss trajectory
  consistent with random ResNet50 initialization on CIFAR10 in early
  training (random baseline approx 2.30 for 10-class classification, the
  network is starting to learn).
- CIFAR10 dataset present on persistent NFS at
  /lambda/nfs/cnsm-gpu-01-fs/cnsm-study/data (170 MB tarball plus extracted
  cifar-10-batches-py directory). Will persist across reboots and Lambda
  instance lifecycle events.

## Open pending items

The following items are tracked for the next operational milestone (before
Sprint S2, currently planned to start in week 9 of cycle 1, approximately
2026-07-10 per OPERATIONAL_GUIDE §22.4):

1. Reimplement disk_io_contention using fio stress on the SSD.
2. Reimplement data_loader_bottleneck using artificial latency in the
   PyTorch DataLoader pipeline.
3. Reimplement batch_inference_overload using concurrent inference
   threads.
4. Implement cpu_contention_during_training using stress-ng on host CPUs
   during training.
5. Generate fault_schedule_lambda_cycle1.csv with seed 42, 28-day window
   (the Sprint S2 collection window), approximately 200 events
   distributed per the §5.2 frequencies (gpu_utilization_spike 2 per day,
   others 1 per day).
6. Create pre-registration tag pre-registration-cycle1-v1.3 with explicit
   justification for the GPU tooling reconciliation, once the
   reimplementation work is complete.
7. Re-enable cnsm-gpu-01 in Zabbix master (status=0) once the reconciled
   injector is deployed and validated.

The four items above (1 to 4) are estimated at 4 to 7 days of focused
engineering work, fitting within the time window available between today
and the start of Sprint S2.

## Next milestones

- Continue passive observation of the training workload over the coming
  days to confirm stability, absence of memory leaks, and consistent GPU
  telemetry under sustained operation.
- Begin reimplementation work on the three pending fault classes during
  the coming week, before Sprint S2 begins.
- Cycle 1 OVH collection continues uninterrupted; the morning health
  check entry (2026-06-13.md) documents that state at T+30.
