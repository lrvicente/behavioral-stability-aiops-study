# Infrastructure for CNSM 2027 Cross-Environment Study

This directory contains all infrastructure code needed to provision and configure
the 12 OVH VPS hosts that form Environment A of the cross-environment behavioral
stability study.

## Execution sequence

The entire setup follows this order. Do not skip steps.

### 1. Manual VPS provisioning (1 to 2 hours)

Follow `docs/01_VPS_PROVISIONING.md` to provision 12 VPS via OVH Manager.
Output: 12 VPS running Ubuntu 24.04, accessible via SSH key.

### 2. Generate fault injection schedule (5 minutes)

```bash
cd ../  # study_p3 root
mkdir -p protocols
python3 infra/scripts/fault_schedule_gen.py \
    --start 2026-05-15 \
    --days 180 \
    --seed 42 \
    --output protocols/fault_schedule_v1.csv

git add protocols/fault_schedule_v1.csv
git commit -m "Pre-register fault injection schedule (seed=42, 180 days)"
git push
```

The git commit timestamp is your pre-registration evidence.

### 3. Configure Ansible inventory (15 minutes)

```bash
cp infra/ansible/inventory/hosts.ini.template infra/ansible/inventory/hosts.ini
# edit hosts.ini, replace REPLACE_WITH_OVH_HOSTNAME with actual hostnames
```

Test connectivity:

```bash
cd infra/ansible
ansible all -i inventory/hosts.ini -m ping
```

All 12 hosts should respond `pong`. If any fails, debug SSH access before
proceeding.

### 4. Configure Zabbix server connection (5 minutes)

Edit `infra/ansible/group_vars/all.yml` and set `zabbix_server` and
`zabbix_server_active` to the actual TheMonitoring.AI Zabbix server FQDN.

### 5. Run bootstrap playbook (10 to 15 minutes)

```bash
cd infra/ansible
ansible-playbook -i inventory/hosts.ini playbooks/00-bootstrap.yml
```

This installs baseline packages, configures sysstat, sets hostname.

### 6. Run Zabbix agent playbook (10 to 15 minutes)

```bash
ansible-playbook -i inventory/hosts.ini playbooks/10-zabbix-agent.yml
```

After completion, the playbook prints registration data for each host.
Use this data to manually register each host in the Zabbix server web interface:
- Hosts > Create host
- Name: cnsm-web-01 (etc)
- IP from playbook output
- Group: cnsm2027-study (create if not exists)
- Templates: Linux by Zabbix agent
- Tags: study=cnsm2027, group=<group>

Repeat for all 12 hosts.

### 7. Run workload playbook (15 to 20 minutes)

```bash
ansible-playbook -i inventory/hosts.ini playbooks/20-workloads.yml
```

After this, each host runs its assigned workload. Verify:

```bash
ansible study_hosts -i inventory/hosts.ini -m systemd -a "name=cnsm-workload"
```

All hosts should show `state: started`.

### 8. Run fault injector playbook (5 to 10 minutes)

```bash
ansible-playbook -i inventory/hosts.ini playbooks/30-fault-injector.yml
```

This deploys the fault injection script and cron job. Faults will start
firing automatically at scheduled times.

### 9. Verify ground truth metric in Zabbix

For any host, query the user parameter:

```bash
zabbix_get -s <host_ip> -k cnsm.fault.active
```

Should return 0 normally, 1 during a fault injection. Verify by triggering
an unscheduled test fault:

```bash
ssh ubuntu@<host>
sudo /opt/cnsm-study/scripts/inject_fault.py --schedule /etc/cnsm/fault_schedule.csv --host $(hostname)
```

### 10. Begin data collection

At this point, the experiment is running. Verify in Zabbix Grafana that
all 12 hosts are sending metrics every 15 seconds, and that
`cnsm.fault.active` toggles correctly during scheduled injections.

## Operational notes

**Monitoring health daily for first 2 weeks**: open Grafana, verify all 12
hosts have continuous data. Any gap > 5 minutes warrants investigation.

**Voucher consumption check weekly**: as documented in
`docs/01_VPS_PROVISIONING.md` section "Voucher consumption monitoring".

**Backup of metrics**: configure Zabbix server to retain 90 days minimum,
plus configure nightly Parquet export to OVH Object Storage (separate
deliverable, not in this package).

**Re-running playbooks**: all playbooks are idempotent and safe to re-run.

## File structure

```
infra/
├── docs/
│   └── 01_VPS_PROVISIONING.md
├── ansible/
│   ├── inventory/
│   │   └── hosts.ini.template
│   ├── group_vars/
│   │   └── all.yml
│   ├── playbooks/
│   │   ├── 00-bootstrap.yml
│   │   ├── 10-zabbix-agent.yml
│   │   ├── 20-workloads.yml
│   │   └── 30-fault-injector.yml
│   └── roles/
│       ├── common/
│       ├── zabbix_agent/
│       ├── workload_web/
│       ├── workload_db/
│       ├── workload_memory/
│       ├── workload_io/
│       └── fault_injector/
└── scripts/
    ├── fault_schedule_gen.py
    └── inject_fault.py
```
