# Behavioral Stability for AIOps Decision Governance

A cross-environment study on behavioral stability modeling for AI Operations decision governance, conducted at TheMonitoring.AI.

## Status

Cycle 1 in pre-registration phase. Data collection begins May 15, 2026. See `lab_notebook/` for current status entries.

## Target venues

Primary: NOMS 2027 full paper (subject to confirmed CFP timeline)
Secondary: CNSM 2027 full paper

## Repository structure

```
.
├── EXPERIMENTAL_SETUP.md   locked canonical scientific protocol (v3.1)
├── THREE_CYCLE_PLAN.md     18-month research program covering 3 cycles
├── OPERATIONAL_GUIDE.md    step-by-step execution manual (v2)
├── README.md               this file
├── LICENSE                 Apache 2.0
├── .gitignore
├── infra/                  infrastructure as code
│   ├── README.md
│   ├── ansible/            Ansible playbooks and roles
│   │   ├── ansible.cfg
│   │   ├── group_vars/
│   │   ├── inventory/      hosts.ini.template (real inventory git-ignored)
│   │   ├── playbooks/      00-bootstrap, 20-workloads, 25-workload-heartbeat, 30-fault-injector
│   │   └── roles/          common, workload_*, fault_injector
│   └── scripts/
│       ├── fault_schedule_gen.py   deterministic schedule generator
│       └── inject_fault.py         fault execution per host
├── scripts/
│   └── nightly_export.py   nightly export from Zabbix API to OVH Object Storage
├── protocols/              pre-registered fault schedules
│   ├── fault_schedule_cycle1.csv
│   ├── fault_schedule_cycle2.csv
│   └── fault_schedule_cycle3.csv
├── code/                   data analysis and modeling code (added during the study)
├── data/                   dataset descriptors (raw data on OVH Object Storage)
├── paper/                  LaTeX source of papers (added when drafting begins)
└── lab_notebook/           research diary entries
```

## Three-cycle research program

| Cycle | Window | Density | Events | Focus | Target paper |
|-------|--------|---------|--------|-------|--------------|
| 1 | May to Aug 2026 | 1.0x | 1008 | Cross-environment generalization | NOMS 2027 |
| 2 | Aug 2026 to Jan 2027 | 1.5x | 1728 | Fault diversity impact | CNSM 2027 |
| 3 | Mar to Jun 2027 | 2.0x | 2016 | LLM-augmented decision governance | IM 2027 |

See `THREE_CYCLE_PLAN.md` for detailed rationale and outputs per cycle.

## Reproducibility

All experiments are pre-registered. The fault injection schedules were generated with deterministic random seeds (42, 43, 44 for cycles 1, 2, 3 respectively) and committed to this public repository BEFORE any data collection began. See git history for timestamp evidence.

To regenerate cycle 1 schedule and verify reproducibility:

```bash
python3 infra/scripts/fault_schedule_gen.py \
    --start 2026-05-15 --days 90 --seed 42 --density 1.0 \
    --output /tmp/verify_cycle1.csv
diff /tmp/verify_cycle1.csv protocols/fault_schedule_cycle1.csv
# expected: no differences
```

The same command with seeds 43 and 44 (and corresponding start dates) regenerates cycles 2 and 3.

## Infrastructure overview

The study uses two environments to test cross-environment generalization:

Environment A (production-grade monitoring stack): 12 OVH VPS in Strasbourg datacenter, monitored via dedicated Zabbix 7.0 LTS server on OVH Public Cloud, operated by TheMonitoring.AI for the duration of the study. Hosts are distributed across 5 functional groups (web, postgres, redis, memory-bound, IO-bound).

Environment B (GPU machine learning workloads): Lambda Cloud A10 GPU instance, sprint-based usage during designated windows of cycle 1 and 2. Same monitoring stack with GPU-aware custom items.

## Data availability

Raw Zabbix metrics for the duration of each cycle are exported nightly to OVH Object Storage (bucket cnsm2027-study, Gravelines datacenter, S3-compatible API). The complete dataset will be released publicly after acceptance of the first associated paper.

## Author

Lucas Renan Vicente Bandeira, TheMonitoring.AI, Malaga, Spain.

## License

Apache License 2.0. See `LICENSE` file.
