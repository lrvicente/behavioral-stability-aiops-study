# Experimental Setup v3.1: Cycle 1, Cross-Environment Behavioral Stability Study

**Study identifier:** P-cycle1-cross-env-2026
**Principal investigator:** Lucas Renan Vicente Bandeira (TheMonitoring.AI)
**Affiliation:** TheMonitoring.AI, Malaga, Spain
**Target venue (primary):** NOMS 2027 full paper, subject to confirmed CFP timeline (deadline approximately September/October 2026)
**Target venue (secondary):** CNSM 2027 full paper if NOMS misses
**Status:** v3.1 LOCKED, 2026-05-07 (canonical scientific protocol)

This document is the canonical scientific protocol. The companion `OPERATIONAL_GUIDE.md` describes how to execute this protocol step by step. If conflict arises between documents, this one takes precedence and the operational guide must be updated.

This document describes Cycle 1 of a three-cycle research program. See `THREE_CYCLE_PLAN.md` for the broader 18-month plan.

## 1. Research Questions

**RQ1.** Does behavioral stability modeling, trained on heterogeneous CPU/IO/network workloads, generalize to GPU-accelerated workloads when both environments are subject to controlled fault injection?

**RQ2.** When applying a model trained in Environment A (OVH, CPU/IO bound) to Environment B (Lambda, GPU bound), what is the performance degradation in F1, MTTD, and false alarm rate, and does ontology-mediated feature mapping reduce that degradation?

**RQ3.** How stable are SHAP attributions, computed in the ontology-mapped feature space, for matched fault classes across environments? Is attribution stability a useful early-warning signal of model degradation under distribution shift?

## 2. Hypotheses (registered predictions)

These hypotheses are pre-registered. **All results will be reported regardless of whether predictions are confirmed.** The point of pre-registration is honesty about expectations, not commitment to specific outcomes.

**H1 (registered prediction).** The proposed behavioral stability model will degrade by less than 15 F1 percentage points under cross-environment evaluation (Environment A training, Environment B testing), while baseline ML methods (Isolation Forest, LSTM-Autoencoder, Prophet+threshold) will degrade by more than 30 percentage points.

**H2 (registered prediction).** Ontology-mediated feature mapping will reduce cross-environment F1 degradation by at least 8 percentage points compared to direct raw-feature transfer.

**H3 (registered prediction).** SHAP attribution cosine similarity, computed in the ontology-mapped feature space for matched fault classes across environments, will correlate with model F1 (Pearson r > 0.6, p < 0.05). Attribution similarity may serve as an unsupervised drift indicator.

**Secondary registered predictions** (exploratory, weaker thresholds):
- H1b: even if H1's specific thresholds are not met, the proposed model will outperform all baselines on cross-environment F1 by a statistically significant margin (Wilcoxon p < 0.05).
- H3b: attribution stability will be higher within-environment than cross-environment for all methods.

## 3. Infrastructure

### 3.1 Environment A (always-on for 90 days): OVH Public Cloud VPS

**12 hosts, heterogeneous, 90 days continuous collection (May 15 to August 13, 2026).**

| Group | Count | VPS Type | Profile | Workload |
|-------|-------|----------|---------|----------|
| web | 6 | VPS-1 (4 vCPU, 8GB) | CPU-bound web | nginx + ApacheBench variable load |
| db_postgres | 2 | VPS-2 (6 vCPU, 12GB) | DB workers | postgres + pgbench |
| db_redis | 2 | VPS-2 (6 vCPU, 12GB) | Cache workers | redis + redis-benchmark |
| memory | 1 | VPS-3 (8 vCPU, 24GB) | Memory-bound | stress-ng vm |
| io | 1 | VPS-3 (8 vCPU, 24GB) | I/O-bound | fio + stress-ng disk |

**Provisioning**: manual via OVH Manager. Configuration management via Ansible (idempotent, version-controlled).
**Region**: Strasbourg (SBG) for all 12 hosts.
**OS**: Ubuntu 24.04 LTS Server.
**Estimated cost**: approximately 101 EUR/month, 303 EUR for 90 days. Within 10000 EUR OVH Startup Program budget.

#### 3.1.1 Justification of architectural choices

The decision to use 12 VPS in a single datacenter, provisioned manually rather than via Terraform with Bare Metal in a virtual rack, is documented here transparently because it affects external validity claims.

Rationale:
- **Cost efficiency**: VPS via Startup Program voucher costs approximately 1/4 of equivalent Public Cloud Compute hourly billing for the same period.
- **Operational simplicity for solo execution**: this study is conducted by a single researcher in parallel with industry responsibilities. Bare Metal with vRack and Terraform automation is appropriate for production deployments at scale, but adds operational risk for a 90-day scientific study.
- **Focus on behavioral observability, not infrastructure benchmarking**: the research question concerns whether a model trained on operational telemetry generalizes across environments. The diversity of telemetry patterns (CPU/IO/network/memory/database) matters more than infrastructure heterogeneity at the hardware layer.
- **Stability over 90 days**: a simpler infrastructure topology reduces the probability of mid-study disruption from infrastructure-level changes.

The trade-off is acknowledged: results from a single-datacenter VPS deployment provide less external validity than a multi-region, multi-provider, multi-hardware-class study would. This is addressed in Section 9 (Threats to Validity) and reflected in the framing of the paper.

### 3.2 Environment B (sprint-based with continuous fault injection): Lambda Cloud GPU

**A10 instance**: 24 GB PCIe, 30 vCPUs, 200 GiB RAM, 1.4 TiB SSD. 1.29 USD/hour.

#### 3.2.1 Sprint plan for cycle 1

**Sprint S1 (model training, 2 weeks, weeks 5-6 of cycle)**: train heavy models (LSTM-Autoencoder, Transformer encoder for behavioral stability) on first 30 days of OVH Environment A data. The A10 acts only as compute resource here, not as monitored host.
- Cost: approximately 430 USD.

**Sprint S2 (cross-environment data collection with fault injection, 4 weeks, weeks 9-12)**: A10 instance becomes a monitored host. Runs continuous ML workload (resnet50 training loop, batch inference jobs every 30 minutes) while Zabbix Agent collects system + GPU telemetry. **GPU-aware fault injection runs in parallel**, providing ground truth synchronized with metric stream (see Section 5.2). Cost: approximately 870 USD.

**Sprint S3 (ablation analysis, 1 week, week 13)**: ablation studies, sensitivity analysis on cross-environment results. Cost: approximately 220 USD.

**Total Lambda budget cycle 1**: approximately 1520 USD of 7500 available. Sufficient buffer for cycles 2 and 3.

**Snapshot strategy**: after S1 setup is validated, take filesystem snapshot. S2 and S3 boot from snapshot to preserve state and avoid reconfiguration overhead.

### 3.3 Monitoring backbone: production-grade Zabbix server

The study reuses the Zabbix server operated by TheMonitoring.AI for production monitoring. This is described as a "production-grade monitoring stack operated by TheMonitoring.AI", not as "validation in production infrastructure", because the monitored hosts (12 OVH VPS + Lambda A10) are dedicated to the study, not production workloads.

Configuration:
- Dedicated host group `cnsm2027-study` isolating study hosts from production
- 15-second polling for study hosts (vs 60s production default)
- 90-day history retention minimum for study items
- Dedicated Grafana dashboards
- Nightly Parquet export to OVH Object Storage for long-term preservation
- All host configuration applied via importable Zabbix template (`artifacts/zabbix_template_cnsm2027.xml`), eliminating manual configuration drift

## 4. Workload definition

### 4.1 OVH workloads (Environment A)

Each host runs continuous workload with scheduled variation patterns to produce realistic operational telemetry:

- **Daily pattern**: load varies between 20% and 80% utilization with 4-hour ramp-up and ramp-down cycles
- **Weekly pattern**: weekend traffic 30% lower than weekday
- **Random spikes**: 5 to 10 random load spikes per week per host (outside scheduled fault injections, treated as natural workload variability)

**Important labeling rule**: random workload spikes are labeled as normal operational variability unless they overlap temporally with a registered fault injection window. Models that alert on these natural spikes count as generating false positives.

Workload generators are version-controlled in `infra/ansible/roles/workload_*/templates/` and applied via Ansible. Reproducibility: any researcher with the same playbooks can recreate equivalent workload patterns.

### 4.2 Lambda workload (Environment B)

A10 instance runs:
- Continuous resnet50 training loop on synthetic data (long-running, predictable GPU utilization in 80% to 95% range)
- Concurrent batch inference jobs every 30 minutes (creates GPU utilization spikes)
- Periodic dataset refresh (creates I/O activity bursts)

This workload is intentionally different in *kind* from OVH workloads. The cross-environment study tests whether a model trained on CPU/IO/network patterns can detect anomalies in GPU-bound patterns, where "GPU at 95% utilization" is normal behavior (not anomalous as it would be on a CPU host).

## 5. Ground truth via controlled fault injection

The study uses synthetic, controlled fault injection in **both environments** to provide reliable ground truth for F1, MTTD, and false alarm rate computation. The framing throughout the paper is explicit: this is a controlled-fault-injection study, not real-world incident detection. This is acknowledged as a limitation in Section 9.

### 5.1 OVH fault injection (Environment A)

**Schedule file**: `protocols/fault_schedule_cycle1.csv`
**Generation parameters**: `--start 2026-05-15 --days 90 --seed 42 --density 1.0`
**Total events**: 1008 fault injections over 90 days (approximately 11 per day across 12 hosts)

| Fault class | Mechanism | Events | Duration range |
|-------------|-----------|--------|----------------|
| cpu_spike | stress-ng --cpu N --cpu-load L | 288 | 5 to 30 min |
| memory_pressure | stress-ng --vm N --vm-bytes XGB | 144 | 10 to 60 min |
| disk_io | stress-ng --io N --hdd N | 288 | 5 to 20 min |
| network_latency | tc qdisc add netem delay | 144 | 5 to 30 min |
| process_leak | stress-ng --fork N | 144 | 5 to 15 min |

Each fault writes a marker file (`/var/run/cnsm-fault-active`) consumed by the Zabbix user parameter `cnsm.fault.active`, providing ground truth synchronized with the 15-second metric stream.

### 5.2 Lambda fault injection (Environment B): GPU-aware

This subsection resolves the methodological gap identified in v2 of this protocol: F1 and MTTD computation requires ground truth in BOTH environments. Lambda also receives controlled fault injection during Sprint S2.

**Schedule file**: `protocols/fault_schedule_lambda_cycle1.csv`
**Generation parameters**: equivalent script with GPU-aware classes, seed 42, 28 days (4 weeks of S2)
**Estimated total events**: approximately 200 fault injections over 28 days

GPU-aware fault classes:

| Fault class | Mechanism | Approximate frequency |
|-------------|-----------|------------------------|
| gpu_utilization_spike | additional CUDA kernel launching, monopolizing GPU compute | 2 per day |
| gpu_memory_pressure | allocate large CUDA tensors near memory limit | 1 per day |
| cpu_contention_during_training | stress-ng --cpu on host CPUs while GPU training runs | 1 per day |
| disk_io_contention | fio stress on the SSD while data loader reads | 1 per day |
| data_loader_bottleneck | artificial latency in data loading pipeline | 1 per day |
| batch_inference_overload | excessive concurrent inference requests | 1 per day |

Implementation: Python script running on the Lambda instance, parallel to the resnet50 training workload. Same marker file pattern as OVH (`/var/run/cnsm-fault-active`), allowing the same Zabbix user parameter to provide ground truth.

The Lambda fault injector is provided as `artifacts/lambda_fault_injector.py` (separate deliverable).

#### 5.2.1 Cross-environment fault class mapping

The following table formally maps OVH fault classes to their Lambda equivalents via the shared ontology. This mapping is the foundation for RQ2 (cross-environment generalization) and RQ3 (SHAP attribution stability).

| OVH class | Lambda class | Ontology concept |
|-----------|--------------|------------------|
| cpu_spike | gpu_utilization_spike | compute_saturation |
| memory_pressure | gpu_memory_pressure | memory_pressure |
| disk_io | disk_io_contention | io_bottleneck |
| network_latency | data_loader_bottleneck | network_degradation |
| process_leak | batch_inference_overload | process_instability |

The Lambda class `cpu_contention_during_training` is retained as a Lambda-specific stress condition and is evaluated in aggregate Lambda metrics, but it is excluded from paired cross-environment SHAP similarity analysis unless explicitly mapped to `compute_saturation` in an ablation. This keeps the primary cross-environment comparison clean (5 paired classes via 5 ontology concepts) while preserving the GPU-specific stressor for within-Lambda analysis.

When the proposed model is trained on OVH and evaluated on Lambda (or vice versa), the ontology concept is the unit of comparison. F1, MTTD, and SHAP cosine similarity are all computed at the ontology level using this mapping.

### 5.3 Sample size justification

Combined OVH + Lambda fault counts: 1008 + 200 = 1208 ground-truth events.

Per RQ analysis:
- 5 fault classes (OVH) + 6 fault classes (Lambda) = 11 distinct categories
- Per category: 24 to 288 events, sufficient for non-parametric statistical testing
- Cross-environment comparison: 200 Lambda events can be matched against ontology-equivalent OVH classes for direct F1 comparison

## 6. Data collection

Metrics collected every 15 seconds per host via Zabbix Agent 2:

**System metrics (all hosts)**: CPU (utilization breakdown, load averages, context switches), memory (used/cached/buffers/swap, PSI pressure), disk (IOPS, throughput, queue depth, utilization, PSI pressure), network (bytes/packets in/out, errors, retransmits, TCP states), process counts by state, system file descriptors.

**Application metrics**: nginx request rates and latency percentiles, postgres connection counts and cache hit ratios, redis ops/sec and eviction counts.

**GPU metrics (Lambda only)**: nvidia-smi output (GPU utilization, memory used/free, temperature, power draw), CUDA kernel launches, memory transfers.

**Study-specific metrics (custom Zabbix items)**: `cnsm.fault.active`, `cnsm.fault.class`, TCP state counts, PSI pressure indicators, workload heartbeat.

Storage: Zabbix internal database for live access, nightly export to Parquet on OVH Object Storage for long-term preservation and analytical workflows.

Estimated dataset size cycle 1: approximately 100 GB raw, 15 GB after Parquet compression. Manageable.

## 7. Modeling approach

### 7.1 Proposed: Behavioral Stability Model

Builds on preprint v1, archived on Zenodo. DOI to be inserted after final archival version is confirmed.

**Architecture**: encoder-only Transformer (4 layers, 8 attention heads, 256 hidden dimensions) operating on rolling 5-minute windows of metrics (20 timesteps at 15s polling).

**Training objective**: contrastive loss (NT-Xent) mapping windows from the same host with no fault active to nearby points in 128-dimensional embedding space, while pushing apart windows from different hosts or windows where faults were active.

**Inference**: at test time, compute the distance from the test window's embedding to the centroid of stable embeddings for that host. Distances above a threshold (calibrated on validation set, F1-optimal threshold) are flagged as anomalous.

### 7.2 Baselines

- **Isolation Forest** (scikit-learn): standard tabular anomaly detection on raw features
- **LSTM-Autoencoder** (PyTorch, trained on Lambda S1): time-series reconstruction error as anomaly score
- **Prophet + threshold** (Facebook Prophet): per-metric forecast residuals, threshold-based detection

All baselines trained on same OVH data, evaluated on same test sets.

### 7.3 Cross-environment adaptation: ontology-mediated feature mapping

Builds on preprint v2 (DOI 10.5281/zenodo.19025889). The ontology defines an abstract feature space common to both environments. Examples:

| Ontology concept | OVH instance | Lambda instance |
|------------------|--------------|-----------------|
| compute_saturation | CPU utilization > 85% | GPU utilization > 90% |
| memory_pressure | RAM > 85% AND swap_used > 0 | GPU memory > 90% |
| io_bottleneck | disk_queue > 5 AND iowait > 20% | disk_queue > 5 (Lambda training I/O) |
| network_degradation | retransmit_rate > 1% | data_loader stalls |
| process_instability | zombie_count > 5 OR fd_count growth | CUDA kernel launch failures |

Models receive ontology-mapped features (5 dimensions) instead of raw metrics (40+ dimensions), allowing transfer between environments without retraining.

### 7.4 SHAP attribution stability metric

This subsection specifies what was vague in v2.

**Computation**: SHAP values are computed on the **anomaly score output** of each model, **using the ontology-mapped feature space** as input. The SHAP attribution for a given fault detection event is therefore a 5-dimensional vector (one component per ontology concept).

**Cross-environment comparison**: for matched fault classes (using ontology mapping, e.g., `cpu_spike` in OVH maps to `gpu_utilization_spike` in Lambda via `compute_saturation`), compute the cosine similarity between mean SHAP attribution vectors:

```
similarity(C_OVH, C_Lambda) = cos(mean_SHAP(detections_OVH_C), mean_SHAP(detections_Lambda_C))
```

where C is a class in the ontology.

**Interpretation**: high cosine similarity means the model "explains" similar faults using similar feature contributions across environments. Low similarity may indicate that the model has learned environment-specific shortcuts.

**Tool**: SHAP library (Lundberg & Lee), specifically `KernelExplainer` for the proposed model and `TreeExplainer` for Isolation Forest, with appropriate explainers for each baseline.

## 8. Evaluation protocol

### 8.1 Train-test splits

- **Training set**: first 60 days of OVH data, all 12 hosts
- **In-domain test set**: last 30 days of OVH data, same hosts (temporal holdout)
- **Cross-environment test set**: full Lambda S2 dataset (28 days with fault injection)

### 8.2 Metrics

**Primary**:
- F1-score, precision, recall (per fault class and aggregate)
- MTTD (Mean Time To Detect): seconds between fault injection start and first alert
- False Alarm Rate: false positives per host per day

**Detection window definition (for F1 and MTTD)**:
- A detection is counted as a true positive if the first anomaly alert occurs between the fault start timestamp and fault end timestamp inclusive.
- An alert occurring within 60 seconds before fault start is logged as an early-warning event and analyzed separately, not counted as TP or FP for the primary metrics.
- An alert occurring after fault end is counted as a false positive unless explicitly part of an early-warning analysis.
- Alerts during natural workload spikes (outside any registered fault window) are counted as false positives.

**Secondary**:
- AUC-ROC, AUC-PR
- SHAP attribution cosine similarity (Section 7.4)

### 8.3 Statistical analysis

- 5 runs per configuration with different random seeds (model initialization, data shuffling)
- 95% confidence intervals via bootstrap (n=1000)
- Pairwise comparison via Wilcoxon signed-rank test
- Multiple comparison correction via Bonferroni
- Effect size via Cohen's d for parametric comparisons, rank-biserial correlation for non-parametric

### 8.4 Reproducibility checklist

- All random seeds fixed and documented in YAML config files
- All hyperparameters in version-controlled configs
- Conda environment exported (`environment.yml`)
- Dataset versioned with DVC, snapshots tied to git tags
- Pipeline orchestrated with Snakemake, single command runs the full analysis
- Code released on GitHub with archival DOI via Zenodo upon paper submission
- Datasets released on Zenodo with their own DOI
- Pre-registration documents (this file + fault schedules) committed to git BEFORE data collection

## 9. Threats to validity

**Internal:**
- Workload generators may not represent real production diversity. Mitigation: include real applications (postgres, redis, nginx) alongside synthetic generators (stress-ng, fio).
- Synthetic fault injection may differ from real production faults in subtle ways. **This is acknowledged explicitly in the paper framing**: this is a controlled-fault-injection study with reliable ground truth, complementary to (not replacement for) real-world incident studies.
- Behavioral stability operationalization is one of multiple possible operationalizations. Mitigation: ablation comparing variance-based, distance-based, and rank-based stability metrics.

**External:**
- Single-datacenter, single-provider OVH deployment limits generalization claims. **Explicitly addressed in framing**: paper claims evidence of cross-environment generalization between OVH (CPU/IO/network) and Lambda (GPU), not universal generalization across all infrastructures. Multi-provider studies are appropriate future work.
- 90-day window may miss longer seasonal patterns. Mitigation: cycles 2 and 3 in subsequent quarters provide additional temporal coverage; combined dataset of 270 days will be analyzed in cycle 3 paper.

**Construct:**
- "Behavioral stability" is operationalized via specific embedding distance metric. Alternative operationalizations may yield different results. Mitigation: ablation with three stability operationalizations, robustness to operationalization choice tested.

**Statistical:**
- Multiple comparisons across fault classes and methods. Mitigation: Bonferroni correction, pre-registered primary hypotheses limit family-wise error rate.
- 5 runs per configuration is the minimum for stable statistics. Mitigation: bootstrap CIs explicitly model the uncertainty.

## 10. Pre-registration

Before any data collection or model training:

1. This document committed to public GitHub repository with timestamp
2. `protocols/fault_schedule_cycle1.csv` (OVH) committed
3. `protocols/fault_schedule_lambda_cycle1.csv` (Lambda, generated when Lambda fault injector is finalized) committed
4. Both documents archived on OSF (osf.io) with DOI
5. Git commit hashes documented in lab notebook
6. Pre-registration referenced explicitly in submitted paper

## 11. Timeline (cycle 1, 90 days)

| Week | Activity | Output |
|------|----------|--------|
| -2 | Pre-registration commits, Zabbix template imported, repo finalized | Protocol locked |
| -1 | OVH provisioning (12 VPS), Ansible bootstrap runs | 12 hosts configured |
| 0 | Workload calibration, OVH fault injection dry run | OVH data flowing |
| 1-13 | Continuous OVH collection | OVH dataset (90 days) |
| 5-6 | Lambda S1 (training sprint, no GPU monitoring yet) | Trained models |
| 9-12 | Lambda S2 (cross-environment collection with GPU fault injection) | Cross-env dataset |
| 13 | Lambda S3 (ablation analysis) | Ablation results |
| 14-16 | Paper drafting | Paper submitted to NOMS 2027 |

## 12. Outputs aligned to PhD by Publication portfolio

Cycle 1 produces:
- **Primary paper**: NOMS 2027 full paper, behavioral stability + cross-environment generalization
- **Secondary paper**: dataset descriptor, Scientific Data or IEEE Dataport
- **Tertiary paper**: position paper on Decision Governance, AIOps Workshop colocation NOMS

Cycles 2 and 3 will produce additional papers per `THREE_CYCLE_PLAN.md`.

## 13. Required artifacts (must exist before execution begins)

The following artifacts must be present in the repository before the experiment starts. Their absence is a no-go condition (see operational guide go/no-go checklist).

- `EXPERIMENTAL_SETUP.md` (this document, committed)
- `THREE_CYCLE_PLAN.md` (committed)
- `protocols/fault_schedule_cycle1.csv` (committed, OVH faults)
- `protocols/fault_schedule_lambda_cycle1.csv` (committed before Lambda S2 start)
- `infra/` (Ansible playbooks, scripts, fully version-controlled)
- `artifacts/zabbix_template_cnsm2027.xml` (importable Zabbix template, replaces all manual item creation)
- `artifacts/lambda_fault_injector.py` (GPU-aware fault injection script)
- `OPERATIONAL_GUIDE.md` (consolidated v2 reflecting this protocol)

Without all of the above, do not start data collection.
