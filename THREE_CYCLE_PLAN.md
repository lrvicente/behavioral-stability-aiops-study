# Three-Cycle Research Plan

This document describes the structure of three sequential 90-day cycles that form the experimental backbone of the 18-month research program. Each cycle uses the same physical infrastructure (12 OVH VPS + Lambda A10 sprints) but varies one key experimental dimension to generate independent but related research contributions.

## Rationale

A single 180-day study would yield a single robust paper. Three sequential 90-day cycles, each varying one experimental dimension, yield three independent papers plus derivative outputs (workshops, journal extensions). For a PhD by Publication portfolio, the latter approach is strictly better: more peer-reviewed publications, coherent narrative through shared infrastructure and core hypothesis, and lower risk of total loss if any single cycle has issues.

## Common foundation across all cycles

These elements remain constant to enable cross-cycle comparison:

- **Infrastructure**: 12 OVH VPS provisioned identically, hostnames preserved across cycles
- **Telemetry stack**: same Zabbix server, same agent configuration, same metric set, 15-second polling
- **Monitoring backbone**: production-grade Zabbix server of TheMonitoring.AI
- **Core hypothesis**: behavioral stability as proxy for operational normalcy
- **Statistical framework**: 5 runs per configuration, 95% CI via bootstrap, Wilcoxon signed-rank for pairwise tests
- **Pre-registration discipline**: each cycle's protocol committed to GitHub before data collection begins

## Cycle 1: Cross-environment generalization (May to Sep 2026)

**Variable under study**: behavioral stability model generalization between heterogeneous CPU/IO environments (OVH) and GPU environment (Lambda A10).

**Research question**: Does a model trained on diverse CPU/IO/network workloads generalize zero-shot to GPU-accelerated workloads, with or without ontology-mediated feature mapping?

**Experimental setup**:
- 12 OVH VPS, 5 workload profiles (web, postgres, redis, memory, IO)
- Lambda A10 sprint S2 (4-6 weeks) at end of cycle, A10 becomes monitored host
- Fault schedule: `fault_schedule_cycle1.csv`, density 1.0x, 1008 events over 90 days

**Target paper**: "Behavioral Stability Modeling for Cross-Environment AIOps Generalization"

**Target venue**: NOMS 2027 (deadline ~September/October 2026, full paper)

**Secondary outputs**:
- Dataset descriptor paper: Scientific Data or IEEE Dataport
- Position paper on Decision Governance: AIOps Workshop colocation

## Cycle 2: Fault diversity impact (Oct 2026 to Feb 2027)

**Variable under study**: density and diversity of fault injections during training, holding the model architecture constant.

**Research question**: How does the diversity and density of training-time fault exposure affect AIOps model robustness when faced with previously unseen fault types?

**Experimental setup**:
- Same 12 OVH VPS, same workloads (continuity)
- Fault schedule: `fault_schedule_cycle2.csv`, density 1.5x, 1728 events over 90 days
- New fault subtypes added: cascading faults (CPU spike triggers IO contention), correlated faults (multiple hosts simultaneously)
- Lambda used for ablation training: 5 model variants trained with different fault diversity levels

**Target paper**: "The Impact of Fault Diversity on AIOps Model Robustness: An Empirical Study"

**Target venue**: CNSM 2027 (deadline June 2027, full paper, comfortable margin)

**Secondary outputs**:
- Workshop paper on cascading fault detection
- Journal extension to CNSM 2027 paper (TNSM invitation if accepted)

## Cycle 3: LLM-augmented decision governance (Mar to Jul 2027)

**Variable under study**: integration of large language model agent into the decision governance loop, monitoring the same hosts.

**Research question**: Can an LLM-mediated decision agent improve the explainability and operator trust in AIOps anomaly detection without sacrificing detection performance?

**Experimental setup**:
- Same 12 OVH VPS
- LLM agent (deployed via OVH AI Endpoints with Llama or Mistral) consumes anomaly detections, generates natural language explanations and recommended actions
- Fault schedule: `fault_schedule_cycle3.csv`, density 2.0x, 2016 events over 90 days, focused stress
- Operator-in-the-loop study: simulated operators (or real with consent from TheMonitoring.AI team) evaluate explanations on Likert scale

**Target paper**: "LLM-Mediated Decision Governance for Behavioral Stability Detection in AIOps"

**Target venue**: IM 2027 or IEEE Software (industry track)

**Secondary outputs**:
- Position paper on agentic AIOps for CNSM 2026 short or AIOps Workshop NOMS
- Demo paper for IEEE NOMS Demo Track

## Cumulative outputs over 18 months

If all three cycles execute as planned:

- 3 full conference papers (one per cycle)
- 2 workshop papers (Decision Governance, cascading faults)
- 1 dataset paper (Scientific Data or IEEE Dataport)
- 1 to 2 journal extensions (TNSM)
- 1 demo paper (NOMS demo track)

Total: 7 to 9 peer-reviewed publications, with coherent thematic unity (behavioral stability as central concept).

For the doctoral portfolio, this provides:
- Multiple chapters of contribution
- Clear methodological evolution (generalization → robustness → human-AI integration)
- Demonstration of independent research direction
- Volume that compensates for non-traditional academic background

## Risk management across cycles

**If cycle 1 paper is rejected**: re-target NOMS 2027 secondary deadline or CNSM 2027. Cycle 2 still proceeds.

**If a cycle has data quality issues**: that cycle becomes a learning round. Pre-registration discipline allows transparent reporting of issues. Subsequent cycles incorporate lessons.

**If Lambda budget is depleted**: scale back GPU experiments to local inference using open-source models, no significant impact on core papers.

**If OVH credits run out before cycle 3**: contact OVH Startup Program manager (Jonathan B. Clarke for Southern Europe) for extension based on publication track record from cycles 1 and 2.

## Timeline summary

| Period | Activity |
|--------|----------|
| May 2026 | Setup + cycle 1 collection start |
| Aug to Sep 2026 | Cycle 1 Lambda S2 + analysis + paper draft |
| Sep to Oct 2026 | Cycle 1 paper submission |
| Oct 2026 | Cycle 2 collection start |
| Jan to Feb 2027 | Cycle 2 analysis + paper draft |
| Mar to Apr 2027 | Cycle 2 paper submission + cycle 3 setup |
| Mar 2027 | Cycle 3 collection start |
| Jun to Jul 2027 | Cycle 3 analysis + paper draft |
| Aug to Sep 2027 | Cycle 3 paper submission + portfolio consolidation |
| Oct 2027 | Portfolio consolidation and doctoral writing |
| Nov 2027 | Doctoral submission readiness |

## Pre-registration commits

Each cycle's protocol must be committed to the public GitHub repository BEFORE data collection begins. Specifically:

- Cycle 1: `protocols/fault_schedule_cycle1.csv` committed before May 15 2026
- Cycle 2: `protocols/fault_schedule_cycle2.csv` committed before Oct 15 2026 (or relevant cycle 2 start date)
- Cycle 3: `protocols/fault_schedule_cycle3.csv` committed before Mar 15 2027

Each commit serves as timestamped evidence of pre-registration.
