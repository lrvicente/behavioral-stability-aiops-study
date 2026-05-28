# Operational Guide v2: From Zero to Cross-Environment Experiment Running

**Companion document to:** `EXPERIMENTAL_SETUP_v3.1_LOCKED.md`
**Status:** v2, 2026-05-07
**Scope:** complete operational instructions to execute Cycle 1 of the three-cycle research program

This document is your execution manual. You read it end-to-end before starting, then use as reference during execution. Each chapter is independent enough to be revisited.

If conflict arises between this document and the protocol, **the protocol wins** and this document must be updated.

## Table of contents

**Part I: Foundations and OVH setup**
1. Conceptual foundations before starting
2. Preparing your local workstation
3. Creating the public GitHub repository
4. Provisioning the 12 OVH VPS
5. Configuring SSH access
6. Understanding Ansible
7. Configuring the Ansible inventory
8. Running the bootstrap playbook
9. Installing Zabbix agents
10. Importing the Zabbix template and registering hosts

**Part II: Workloads and OVH ground truth**
11. Deploying workloads
12. Scientific pre-registration of fault schedules
13. Deploying the OVH fault injector

**Part III: Lambda and cross-environment**
14. Provisioning Lambda A10
15. Installing Zabbix Agent on Lambda with GPU metrics
16. Deploying the Lambda GPU-aware fault injector
17. Cross-environment evaluation pipeline

**Part IV: Operations and quality**
18. Data management, backup, and retention
19. Lab notebook discipline (mandatory from day 1)
20. Halt criteria
21. Go / No-Go checklist before data collection starts
22. Daily, weekly, and monthly operations
23. Troubleshooting common scenarios

---

## Chapter 1: Conceptual foundations before starting

Before touching any command, four concepts sustain the entire study. Skipping these means executing mechanically without understanding why.

### 1.1 Why 12 hosts and not 3 or 50?

CNSM and NOMS reviewers evaluate AIOps studies critically for the "n=1 problem", where authors test on too few machines and overgeneralize. Conversely, 50 hosts without heterogeneity is just a big number without experimental richness.

12 hosts is the sweet spot because:
- Covers 5 distinct workload profiles (web, postgres, redis, memory, IO)
- Each profile has minimum repetition (2 to 6 hosts per profile) for intra-group variance
- Cost manageable within OVH Startup Program voucher (303 EUR for 90 days)
- Operationally manageable by a single researcher

When a reviewer asks "why 12 hosts?", you answer with these four reasons.

### 1.2 Why this is genuinely a cross-environment study

Earlier reviewer feedback questioned whether a study with all hosts in OVH/SBG can claim "cross-environment". The answer is yes, because cross-environment in this study refers to two qualitatively different infrastructures, not two datacenters of the same kind:

- **Environment A**: 12 OVH VPS in SBG, CPU/IO/network bound workloads, x86 commodity virtualization
- **Environment B**: Lambda A10 GPU instance, GPU-accelerated ML workloads, fundamentally different hardware utilization patterns

The contrast that matters scientifically is not "OVH vs another cloud provider" but "CPU-bound infrastructure vs GPU-bound infrastructure". A model trained on OVH data has never seen what 95% sustained GPU utilization looks like, what GPU memory pressure looks like, or what data loader stalls look like. Whether it generalizes is the actual research question.

### 1.3 Why Ansible and not shell scripts or Docker?

Ansible does three fundamental things that shell scripts do poorly:

- **Idempotence**: running the same playbook 5 times leaves the system in the same state, not accumulating effects. Critical when adjusting configuration and re-applying.
- **Declarative inventory**: you define "these 12 hosts belong to this group, execute these tasks", instead of manually looping in shell.
- **Scientific reproducibility**: the playbook is the document that proves how the environment was configured. Reviewers can inspect.

Docker could work, but you want to monitor real VPS (bare-metal-like behavior), not containers. Containers hide hardware/kernel characteristics that matter for AIOps.

### 1.4 Why pre-registration?

In recent empirical science, there is a reproducibility crisis. Reviewers are suspicious when authors test multiple hypotheses and report only the ones that worked (p-hacking). Pre-registration means publishing your hypotheses, metrics, and protocols before collecting data.

In our case, pre-registration is concrete:
- You commit `EXPERIMENTAL_SETUP_v3.1_LOCKED.md` to public GitHub before collecting
- You commit `protocols/fault_schedule_cycle1.csv` (generated with fixed seed) before the first injection runs
- You commit `protocols/fault_schedule_lambda_cycle1.csv` before Lambda S2 starts
- Git timestamps prove when you committed to the protocol

This is your armor against the skeptical reviewer.

### 1.5 Why Zabbix and not Prometheus or Datadog?

Your central research thesis is "behavioral stability via Decision Governance on the Zabbix stack". Switching stacks breaks the coherence of your portfolio. TheMonitoring.AI runs Zabbix, your preprints cite Zabbix, paper P1 (cycle 1 conversion) uses Zabbix dataset. Keeping Zabbix is a strategic decision, not a technical one.

---

## Chapter 2: Preparing your local workstation

You need a "command machine" to operate everything. It can be your personal laptop or a dedicated VPS. I recommend the laptop if it's always the same one, because you'll have command history and locally versioned files.

### 2.1 Required packages

On your local Ubuntu, install:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git ansible openssh-client jq
```

Verify minimum versions:

```bash
ansible --version    # need >= 2.14
python3 --version    # need >= 3.10
git --version        # any recent version
```

If Ansible comes too old via apt (older Ubuntu LTS), install via pip:

```bash
python3 -m pip install --user ansible-core
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2.2 Generating SSH keys

You need two distinct SSH keys: one for OVH/Lambda, one for GitHub. Separating them is best practice.

```bash
ssh-keygen -t ed25519 -C "cnsm2027-study-ovh" -f ~/.ssh/cnsm2027_ed25519
ssh-keygen -t ed25519 -C "cnsm2027-github" -f ~/.ssh/github_ed25519
```

When passphrase is requested, decide:
- **Without passphrase**: simpler, but if someone gets the file, they have access. OK if your machine is secure.
- **With passphrase**: safer, but you have to type each time or use ssh-agent.

For starting, recommend without passphrase. You can rotate later.

The public keys (`.pub` files) are what you'll register at OVH and GitHub. Show them:

```bash
cat ~/.ssh/cnsm2027_ed25519.pub
cat ~/.ssh/github_ed25519.pub
```

Copy each entire content (a single line starting with `ssh-ed25519`) for use later.

### 2.3 Local folder structure

Create a working directory where everything study-related will live:

```bash
mkdir -p ~/work/themonitoring/cnsm2027
cd ~/work/themonitoring/cnsm2027
```

All command execution from now on assumes you're inside this directory unless indicated.

---

## Chapter 3: Creating the public GitHub repository

This is your first scientific action. The first commit timestamp begins documenting the study.

### 3.1 Configure SSH for GitHub

If you don't have a GitHub SSH key registered yet:

```bash
cat ~/.ssh/github_ed25519.pub
```

Copy output, go to https://github.com/settings/ssh/new, paste, save.

Edit `~/.ssh/config` to use this key automatically for GitHub:

```bash
cat >> ~/.ssh/config << 'EOF'

Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_ed25519
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

Test:

```bash
ssh -T git@github.com
# expected: "Hi your-username! You've successfully authenticated..."
```

### 3.2 Create the GitHub repo

1. Access https://github.com/new (logged in)
2. Repository name: `behavioral-stability-aiops-study`
3. Description: "Cross-environment behavioral stability study for AIOps decision governance, target venues NOMS 2027 and CNSM 2027"
4. **Public** (essential for open science credibility)
5. Initialize with README: do NOT check (we'll create locally)
6. Add .gitignore: do NOT check
7. License: Apache 2.0 (recommended for projects with commercial component)
8. Click "Create repository"

GitHub shows you the SSH URL. Copy it (`git@github.com:your-username/behavioral-stability-aiops-study.git`).

### 3.3 Clone locally and unpack the package

```bash
cd ~/work/themonitoring/cnsm2027
git clone git@github.com:your-username/behavioral-stability-aiops-study.git
cd behavioral-stability-aiops-study
```

Now unpack the provisioning package within this directory:

```bash
unzip ~/Downloads/cnsm2027_provisioning_pkg_v2.zip
```

Confirm the structure:

```bash
ls
# should show: infra/ protocols/ EXPERIMENTAL_SETUP.md THREE_CYCLE_PLAN.md
```

If the protocol file is named `EXPERIMENTAL_SETUP_v3.1_LOCKED.md` in your downloads, rename it to canonical name:

```bash
mv EXPERIMENTAL_SETUP_v3.1_LOCKED.md EXPERIMENTAL_SETUP.md
```

The canonical filename in the repo is `EXPERIMENTAL_SETUP.md`. The `_v3.1_LOCKED` suffix is for delivery clarity, not for the repo.

### 3.4 Add top-level README and license

Create the top-level README:

```bash
cat > README.md << 'EOF'
# Behavioral Stability for AIOps Decision Governance

Cross-environment study on behavioral stability modeling for AI Operations decision governance, conducted at TheMonitoring.AI.

## Status

In progress, cycle 1 data collection May to August 2026.

## Target venues

- Primary: NOMS 2027 full paper (subject to confirmed CFP timeline)
- Secondary: CNSM 2027 full paper

## Repository structure

- `EXPERIMENTAL_SETUP.md`: locked canonical scientific protocol
- `THREE_CYCLE_PLAN.md`: 18-month research program covering 3 cycles
- `OPERATIONAL_GUIDE.md`: step-by-step execution manual
- `infra/`: infrastructure as code (Ansible, scripts) for provisioning
- `protocols/`: pre-registered fault injection schedules
- `artifacts/`: technical artifacts (Zabbix template, Lambda fault injector, export scripts)
- `code/`: data analysis and modeling code (added during the study)
- `data/`: dataset descriptors (raw data hosted on OVH Object Storage)
- `paper/`: LaTeX source of the paper (added when drafting begins)
- `lab_notebook/`: research diary entries (one per intervention)

## Reproducibility

All experiments are pre-registered. Fault injection schedules were generated with fixed random seeds and committed to the repository before any data collection began. See git history for timestamp evidence.

## Author

Lucas Renan Vicente Bandeira, TheMonitoring.AI, Malaga, Spain.

## License

Apache License 2.0. See LICENSE file.
EOF
```

Create Apache 2.0 license:

```bash
curl -L https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
```

### 3.5 First commit (this is the initial pre-registration)

```bash
git add .
git status   # review what will be committed
git commit -m "Lock canonical scientific protocol v3.1 for cycle 1 cross-environment study"
git push origin main
```

Repo is now live. The push timestamp is the "T zero" of the study. Reviewers can verify.

---

## Chapter 4: Provisioning the 12 OVH VPS

Now the manual part. Since we decided manual VPS via OVH Manager (not API), you'll click "Order VPS" 12 times. Not elegant, but it's only once.

### 4.1 Register SSH key at OVH

Before requesting the first VPS, upload your public key to OVH Manager:

1. Login at https://www.ovhcloud.com/manager/
2. Top-right corner, click your username, then "My services" or similar
3. In sidebar menu, find "SSH keys" (may be under Public Cloud or under account)
4. "Add a key"
5. Name: `cnsm2027-key`
6. Public key: paste content of `~/.ssh/cnsm2027_ed25519.pub`
7. Save

### 4.2 Verify Startup Program voucher

Before provisioning:

1. In manager, go to "Order" (top-left) > "Payment methods"
2. Click "My Startup Program vouchers" tab
3. Confirm voucher shows balance approximately 10,000 EUR

If you don't see the voucher, you're likely on the wrong account. Confirm with your Startup Program Manager (you were assigned someone when joining).

### 4.3 Provisioning the first VPS

I'll guide you through the first one in detail. The other 11 are repetitions.

1. In manager, top menu, click "Web Cloud" > "VPS"
2. Button "Order a VPS" (or + icon)
3. "Range" screen: choose **VPS-1**
4. "Datacenter" screen: choose **Strasbourg (SBG)**. Important to keep the same datacenter for all 12 to reduce network variance.
5. "Operating system" screen: choose **Ubuntu 24.04 Server** (no GUI)
6. "Hostname" screen: type `cnsm-web-01`
7. "Backup" screen: leave default (1 day, automatic, included)
8. "Options" screen: usually nothing extra. **DO NOT check** paid anti-DDoS if it appears (already included in basic)
9. "Billing" screen: choose "1 month, no commitment"
10. "SSH key" screen: select `cnsm2027-key`
11. "Summary" screen: **review critically**. Total should show:
    - Subtotal: 5.52 EUR
    - Voucher applied (Digital LaunchPad): -5.52 EUR
    - Total: **0.00 EUR**
12. Accept terms, "Confirm order"

Provisioning takes 2 to 5 minutes. You receive email when ready, with the assigned hostname `vpsXXXXXX.vps.ovh.net`.

### 4.4 Provisioning the other 11

Repeat the process above, changing only the hostname and VPS type:

| Hostname | Range | Same DC (SBG) and OS (Ubuntu 24.04) |
|----------|-------|-------------------------------------|
| cnsm-web-02 | VPS-1 | yes |
| cnsm-web-03 | VPS-1 | yes |
| cnsm-web-04 | VPS-1 | yes |
| cnsm-web-05 | VPS-1 | yes |
| cnsm-web-06 | VPS-1 | yes |
| cnsm-db-01 | VPS-2 | yes |
| cnsm-db-02 | VPS-2 | yes |
| cnsm-db-03 | VPS-2 | yes |
| cnsm-db-04 | VPS-2 | yes |
| cnsm-mem-01 | VPS-3 | yes |
| cnsm-io-01 | VPS-3 | yes |

Tip: open 3 to 4 browser tabs in parallel to provision simultaneously, instead of waiting one to finish before starting the next. Total: 1 to 2 hours wall clock, but you only do active work for ~30 minutes.

### 4.5 Collecting assigned hostnames

When all are ON, go to "VPS" in menu. You see list of 12. Click each and note external hostname (format `vpsXXXXXX.vps.ovh.net`).

Also note public IP (shown on VPS page). You'll need both shortly.

Create a temporary local file to save this association:

```bash
cd ~/work/themonitoring/cnsm2027/behavioral-stability-aiops-study
mkdir -p .local
cat > .local/hosts_mapping.txt << 'EOF'
# Local file, NOT committed to git
# Format: study_name | OVH hostname | OVH IP
cnsm-web-01 | vps-XXXXXXXX.vps.ovh.net | 51.X.X.X
cnsm-web-02 | ... | ...
EOF
```

Note: `mkdir -p .local` is executed BEFORE writing into it. This was a bug in v1 of this guide.

Add `.local/` to root `.gitignore`:

```bash
echo ".local/" >> .gitignore
git add .gitignore
git commit -m "Ignore local-only files"
```

---

## Chapter 5: Configuring SSH access to VPS

Now we'll validate that your SSH key works on all 12, and configure the SSH client to ease access.

### 5.1 Manual SSH test on one host

Replace hostname with the real one:

```bash
ssh -i ~/.ssh/cnsm2027_ed25519 ubuntu@vps-XXXXXXXX.vps.ovh.net
```

Expected:
- First connection asks about fingerprint, answer `yes`
- Connects without asking password (your key already authorized)
- You see Ubuntu prompt

Exit with `exit`.

If it asks for password: SSH key wasn't properly attached during provisioning. In manager, on VPS page, "Reinstall my VPS" selecting Ubuntu 24.04 and SSH key. Wait reinstallation (10 minutes).

### 5.2 Configure SSH client for all hosts

Edit `~/.ssh/config` and add a block per host:

```bash
cat >> ~/.ssh/config << 'EOF'

# CNSM 2027 study hosts
Host cnsm-web-01
    HostName vps-XXXXXXXX.vps.ovh.net
    User ubuntu
    IdentityFile ~/.ssh/cnsm2027_ed25519
    IdentitiesOnly yes

Host cnsm-web-02
    HostName vps-YYYYYYYY.vps.ovh.net
    User ubuntu
    IdentityFile ~/.ssh/cnsm2027_ed25519
    IdentitiesOnly yes

# ... repeat for the other 10
EOF
```

Replace with real hostnames. Then you can connect simply with:

```bash
ssh cnsm-web-01
```

### 5.3 Accept fingerprints in bulk

To avoid Ansible breaking on first connection, accept fingerprints preemptively:

```bash
for h in cnsm-web-{01..06} cnsm-db-{01..04} cnsm-mem-01 cnsm-io-01; do
  ssh -o StrictHostKeyChecking=accept-new "$h" "echo $h ok"
done
```

Expected 12 lines of "cnsm-XXX-NN ok". If any fails, check SSH config.

---

## Chapter 6: Understanding Ansible

Before executing any playbook, you need the mental model.

### 6.1 The 5 fundamental concepts

**Inventory (`hosts.ini`)**: list of machines Ansible will manage, organized in groups. In our case, 12 hosts in 5 groups (web, db_postgres, db_redis, memory, io). Each host has connection data (IP, user, SSH key).

**Playbook (`*.yml`)**: YAML file describing a sequence of operations ("plays") applied to a host set. It is declarative: you describe the desired state, not commands step by step.

**Task**: an atomic operation. Examples: "install nginx package", "ensure service Z is running", "copy file X to path Y". Each task uses an Ansible "module" (e.g., `apt`, `systemd`, `template`).

**Role**: reusable grouping of tasks, templates, and handlers, organized in standard folder structure. Our package has 7 roles. Think of role as "everything needed to make a server ready for a specific role".

**Handler**: special task that only runs if it was notified by another task that changed something. Example: "Restart nginx" only fires if the config file changed. Avoids unnecessary restarts.

### 6.2 How Ansible executes

Ansible runs on your local machine (called "control node"). It connects via SSH on each target host, transfers small Python files, executes, collects result, deletes the files. No need to install anything on hosts.

Each task is executed on all hosts of the target group, **in parallel** by default (up to `forks=12` in our `ansible.cfg`).

### 6.3 Idempotence in practice

Idempotence is the most important property. It means: running the playbook 1 time or 5 times produces the same final state.

Example: "install nginx" task doesn't fail if already installed. It only acts if necessary. Ansible output shows:
- `changed`: state changed in this execution
- `ok`: already in desired state, didn't do anything
- `failed`: error

When you run a playbook the first time, expect many `changed`. The second time, expect almost everything `ok`. This is sign it's working correctly.

### 6.4 Anatomy of a playbook we'll execute

Look at `playbooks/00-bootstrap.yml`:

```yaml
- name: Baseline configuration of all study hosts
  hosts: study_hosts          # which group
  become: true                # execute as root via sudo
  gather_facts: true          # collect info from hosts (CPU, RAM, etc)
  
  pre_tasks:
    - name: Wait for SSH to be reachable
      ...
  
  roles:
    - common                  # apply role "common"
  
  post_tasks:
    - name: Confirm bootstrap complete
      ...
```

Read as: "for all hosts in group `study_hosts`, connect via SSH as `ubuntu`, elevate to root via sudo, wait SSH ready, apply all tasks of role `common`, then print confirmation".

---

## Chapter 7: Configuring the Ansible inventory

Here you tell Ansible which machines exist and where they are.

### 7.1 Copy template to real file

```bash
cd ~/work/themonitoring/cnsm2027/behavioral-stability-aiops-study/infra/ansible
cp inventory/hosts.ini.template inventory/hosts.ini
```

Template is in git, real `hosts.ini` is not (included in `.gitignore`), because you may have sensitive data.

### 7.2 Edit with real hostnames

Open `inventory/hosts.ini` in editor:

```bash
nano inventory/hosts.ini
```

Replace each `REPLACE_WITH_OVH_HOSTNAME` with real collected hostname. Example:

```ini
[web]
cnsm-web-01 ansible_host=vps-12345678.vps.ovh.net ansible_user=ubuntu
cnsm-web-02 ansible_host=vps-23456789.vps.ovh.net ansible_user=ubuntu
...
```

Add an extra line with SSH key (important because Ansible doesn't automatically read `~/.ssh/config`):

```ini
[all:vars]
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new'
ansible_ssh_private_key_file=~/.ssh/cnsm2027_ed25519
```

The last line (`ansible_ssh_private_key_file`) is critical: points Ansible to the correct key.

### 7.3 Configure Zabbix server

Edit `group_vars/all.yml`:

```bash
nano group_vars/all.yml
```

Replace placeholder with real FQDN of your Zabbix server:

```yaml
zabbix_server: zabbix-real.themonitoring.ai
zabbix_server_active: zabbix-real.themonitoring.ai
```

### 7.4 Connectivity test

Most important command to validate inventory:

```bash
cd ~/work/themonitoring/cnsm2027/behavioral-stability-aiops-study/infra/ansible
ansible all -i inventory/hosts.ini -m ping
```

Expected output (12 times, one per host):

```
cnsm-web-01 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

If any host fails:
- "UNREACHABLE": SSH problem, validate config
- "AUTHENTICATION FAILED": wrong key
- "Permission denied": correct key but wrong user, must be `ubuntu`

Don't proceed until 12 return SUCCESS.

---

## Chapter 8: Running the bootstrap playbook

First real playbook. It puts all hosts in standardized base state.

### 8.1 What this playbook does

Reading `roles/common/tasks/main.yml`:

1. Waits for unattended-upgrades to finish
2. Updates apt cache
3. Installs baseline packages: curl, wget, jq, htop, sysstat, stress-ng, etc
4. Ensures chrony running (NTP, important for consistent timestamps)
5. Ensures cron running
6. Creates standardized directories: `/opt/cnsm-study/`, `/var/log/cnsm-faults/`, `/var/log/cnsm-workloads/`
7. Configures sysstat to collect metrics every 1 minute (local backup, complementary to Zabbix)
8. Disables auto-updates (you control patch windows)
9. Creates `/etc/cnsm-study-metadata` identifying host as part of study

### 8.2 Command

```bash
ansible-playbook -i inventory/hosts.ini playbooks/00-bootstrap.yml
```

### 8.3 Expected output

You'll see a stream of tasks executing. For 12 hosts × ~12 tasks = ~144 lines of output.

End summary "PLAY RECAP":

```
PLAY RECAP ***********************************************
cnsm-web-01 : ok=10  changed=8  unreachable=0  failed=0
cnsm-web-02 : ok=10  changed=8  unreachable=0  failed=0
...
```

**failed=0 on all 12** is the success criterion.

### 8.4 Expected time

First execution: 10 to 15 minutes. Re-running (idempotence): 1 to 2 minutes.

### 8.5 Manual validation

On any host:

```bash
ssh cnsm-web-01
ls /opt/cnsm-study/
cat /etc/cnsm-study-metadata
systemctl is-active chrony
stress-ng --version
exit
```

---

## Chapter 9: Installing Zabbix agents

Second playbook. Installs Zabbix Agent 2 on the 12 hosts and configures to point to your existing server.

### 9.1 What this playbook does

Reading `roles/zabbix_agent/tasks/main.yml`:

1. Downloads package from official Zabbix repository (version 7.0)
2. Installs `zabbix-agent2` and plugins
3. Generates `/etc/zabbix/zabbix_agent2.conf` from template, with your real server
4. Generates user parameters file specific to study (`cnsm.fault.active`, etc)
5. Enables and starts service `zabbix-agent2`
6. Opens port 10050 in ufw firewall if active

### 9.2 Command

```bash
ansible-playbook -i inventory/hosts.ini playbooks/10-zabbix-agent.yml | tee zabbix-registration-data.txt
```

The `| tee` saves the output to file while showing on screen.

### 9.3 Validation

On any host:

```bash
ssh cnsm-web-01
sudo systemctl is-active zabbix-agent2
sudo systemctl status zabbix-agent2 | head -15
sudo tail /var/log/zabbix/zabbix_agent2.log
exit
```

Should show agent connecting to server, no DNS or auth errors.

If agent doesn't connect:
- Wrong server DNS in `group_vars/all.yml`
- Server firewall blocking VPS IP
- Server doesn't permit connections from this IP

---

## Chapter 10: Importing the Zabbix template and registering hosts

This chapter changed significantly from v1. Instead of creating items manually for 12 hosts (error-prone, scientifically weak), you import a template once and apply to all.

### 10.1 Why a template

Reviewers expect reproducible measurement infrastructure. Manual item creation across 12 hosts produces inconsistencies (typos, missed items, version drift). A version-controlled XML template eliminates this risk.

The template `artifacts/zabbix_template_cnsm2027.xml` defines:
- All custom items (cnsm.fault.active, cnsm.fault.class, TCP states, PSI pressure, etc)
- Triggers (e.g., agent unreachable for 5 minutes)
- Item-level retention policy (90 days minimum for study)
- Linked Linux base template inheritance

### 10.2 Importing the template

In Zabbix frontend:

1. Configuration > Templates > Import
2. Choose file `artifacts/zabbix_template_cnsm2027.xml`
3. Verify all options checked: Items, Triggers, Graphs, Templates, Discovery rules
4. Click Import
5. Verify success message

The template appears as `Template CNSM2027 Study Host` (or similar name, defined in XML).

### 10.3 Create the host group

1. Configuration > Host groups > Create host group
2. Name: `cnsm2027-study`
3. Click Add

### 10.4 Register each of the 12 hosts

For each host, repeat:

1. Configuration > Hosts > Create host
2. Tab "Host":
   - Host name: `cnsm-web-01` (technical, must match agent hostname)
   - Visible name: `cnsm-web-01`
   - Groups: `cnsm2027-study`
   - Interfaces: Agent, IP from playbook output, port 10050, "Connect to" = IP
3. Tab "Templates":
   - Link: `Template CNSM2027 Study Host` (the one you imported)
   - Additional for postgres: `PostgreSQL by Zabbix agent 2`
   - Additional for redis: `Redis by Zabbix agent 2`
4. Tab "Tags":
   - Add: `study` = `cnsm2027`
   - Add: `group` = `web` (or db, memory, io as the host)
5. Click Add

Repeat for the 12 hosts.

### 10.5 Validation

In Zabbix:
- Configuration > Hosts: filter by host group `cnsm2027-study`
- Expected to see 12 hosts, all with ZBX in green (agent connected)

If any appears red/yellow:
- Red: agent doesn't respond. Check firewall, restart agent.
- Yellow: agent responds but didn't pass Zabbix server check. Usually template issue.

Spot check: Monitoring > Latest data, filter by one host. You should see metrics flowing every 15 seconds, including study-specific items like `cnsm.fault.active` (returning 0 normally).

---

## Chapter 11: Deploying workloads

Third playbook. Installs and activates load generators.

### 11.1 What this playbook does

For each host group, applies specific role:
- `web` (6 hosts): nginx + ApacheBench, deploys load generator with daily/weekly pattern
- `db_postgres` (2 hosts): postgres + pgbench, init test database
- `db_redis` (2 hosts): redis + redis-tools, deploys generator
- `memory` (1 host): stress-ng vm generator
- `io` (1 host): fio + stress-ng disk

Each generator runs as systemd service `cnsm-workload`, with automatic restart.

### 11.2 Command

```bash
ansible-playbook -i inventory/hosts.ini playbooks/20-workloads.yml
```

### 11.3 Expected time

15 to 20 minutes. Postgres setup dominates (pgbench init).

### 11.4 Validation

```bash
ansible study_hosts -i inventory/hosts.ini -m systemd -a "name=cnsm-workload" | grep -E "(SUCCESS|active)"
```

Expected 12 outputs indicating active.

On individual host:

```bash
ssh cnsm-web-01
sudo systemctl status cnsm-workload
sudo tail /var/log/cnsm-workloads/web.log
exit
```

In Zabbix: open `cnsm-web-01`, Latest data. CPU usage should rise as workload runs. Same for the others.

---

## Chapter 12: Scientific pre-registration of fault schedules

Critical step. Here you commit the fault schedules BEFORE the first injection runs.

### 12.1 Why this matters

If you generate the schedule after collecting data, reviewers may suspect you adjusted the schedule based on what you saw. Pre-registration eliminates that suspicion.

The fixed seed (42 for cycle 1) is also part of the proof: any reviewer can run the same generator with the same seed and get the SAME file. Total reproducibility.

### 12.2 Verify schedules already generated

The provisioning package already includes pre-generated schedules for all three cycles:

```bash
cd ~/work/themonitoring/cnsm2027/behavioral-stability-aiops-study
ls -la protocols/
# expected:
# fault_schedule_cycle1.csv  (1008 events, seed 42, density 1.0)
# fault_schedule_cycle2.csv  (1728 events, seed 43, density 1.5)
# fault_schedule_cycle3.csv  (2016 events, seed 44, density 2.0)
```

If any is missing, regenerate:

```bash
python3 infra/scripts/fault_schedule_gen.py \
    --start 2026-05-15 --days 90 --seed 42 --density 1.0 \
    --output protocols/fault_schedule_cycle1.csv
```

### 12.3 Atomic commit of pre-registration

Critical: protocol + schedules in same commit window. Reviewers will check git timestamps.

```bash
cd ~/work/themonitoring/cnsm2027/behavioral-stability-aiops-study
git add EXPERIMENTAL_SETUP.md THREE_CYCLE_PLAN.md protocols/
git commit -m "Pre-register cycle 1 protocol + fault schedules (cycles 1-3)

- EXPERIMENTAL_SETUP.md v3.1 LOCKED
- THREE_CYCLE_PLAN.md
- protocols/fault_schedule_cycle1.csv (seed 42, density 1.0, 1008 events)
- protocols/fault_schedule_cycle2.csv (seed 43, density 1.5, 1728 events)
- protocols/fault_schedule_cycle3.csv (seed 44, density 2.0, 2016 events)

This commit serves as pre-registration evidence."
git push origin main
```

Note the commit hash:

```bash
git log -1 --format="%H %ci"
```

Add this hash to your `EXPERIMENTAL_SETUP.md`, section "Pre-registration":

```bash
# at end of section 10, add:
# OVH cycle 1 pre-registration: commit <HASH> on <DATE>
git commit -am "Document pre-registration commit hash in protocol"
git push
```

### 12.4 Bonus: independent registration on OSF

To strengthen further:

1. Create account at https://osf.io (free)
2. Create new project: "Behavioral Stability AIOps Study"
3. Upload `EXPERIMENTAL_SETUP.md`, `THREE_CYCLE_PLAN.md`, `protocols/fault_schedule_cycle1.csv`
4. In "Registrations", create new registration using "OSF Preregistration" template
5. Submit

OSF generates permanent DOI for the registration. Add this DOI to GitHub README. Reviewers from CNSM/NOMS are instructed to check pre-registrations on OSF.

The Lambda fault schedule (`fault_schedule_lambda_cycle1.csv`) will be generated and committed separately, before Lambda S2 starts (Chapter 16).

---

## Chapter 13: Deploying the OVH fault injector

Fourth playbook. Distributes the injection script and schedule to the 12 hosts.

### 13.1 What this playbook does

1. Verifies that `protocols/fault_schedule_cycle1.csv` exists (protection against forgetting)
2. On each host:
   - Installs iproute2 (necessary for `tc` in network latency fault)
   - Creates `/etc/cnsm/`
   - Copies `inject_fault.py` to `/opt/cnsm-study/scripts/`
   - Copies `fault_schedule_cycle1.csv` to `/etc/cnsm/fault_schedule.csv`
   - Installs cron job that runs `inject_fault.py` every minute

### 13.2 Command

```bash
ansible-playbook -i inventory/hosts.ini playbooks/30-fault-injector.yml
```

For cycle 2 or 3 later, override the cycle variable:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/30-fault-injector.yml -e "cycle=cycle2"
```

### 13.3 Validation

On any host:

```bash
ssh cnsm-web-01
sudo crontab -l | grep CNSM
ls /opt/cnsm-study/scripts/inject_fault.py
ls /etc/cnsm/fault_schedule.csv

# manually test (force out-of-schedule injection)
sudo /opt/cnsm-study/scripts/inject_fault.py \
    --schedule /etc/cnsm/fault_schedule.csv \
    --host cnsm-web-01 \
    --window-seconds 999999

# during execution, in another terminal:
ssh cnsm-web-01 "cat /var/run/cnsm-fault-active 2>/dev/null"
# should return 1 while fault running

sudo cat /var/log/cnsm-faults/executions.log
exit
```

### 13.4 Ground truth verification in Zabbix

This is the crucial piece. Zabbix needs to capture ground truth.

In any host, simulate a fault and verify in parallel if Zabbix captured:

Terminal 1:
```bash
ssh cnsm-web-01
sudo bash -c 'echo 1 > /var/run/cnsm-fault-active && echo "test_class" > /var/run/cnsm-fault-class && sleep 60 && rm /var/run/cnsm-fault-active /var/run/cnsm-fault-class'
```

Terminal 2:
```bash
zabbix_get -s vps-XXXXXXXX.vps.ovh.net -k cnsm.fault.active
# during the 60s, should return 1, then 0
```

If value correctly returns 0/1, ground truth is armed. From now on, any real fault injected via cron will appear in Zabbix synchronized with metrics.

---

## Chapter 14: Provisioning Lambda A10

Now Part III: Lambda. This chapter and the next three set up Environment B.

Note: per the protocol, Lambda use is sprint-based. You don't need to provision now if you're at week 0 of the cycle. Lambda S1 starts at week 5. But it's useful to test provisioning now to identify problems early.

### 14.1 Account setup

If you don't yet have a Lambda Cloud account:

1. Visit https://cloud.lambdalabs.com/
2. Sign up
3. Add the 7,500 USD credit voucher you have available
4. Add your SSH public key (`~/.ssh/cnsm2027_ed25519.pub`) under Account > SSH keys

### 14.2 Launching the A10 instance

1. In Lambda Cloud dashboard, click "Launch instance"
2. Instance type: **1x A10 (24 GB PCIe)**, $1.29/hr
3. Region: pick the closest available (usually US-East or US-West for Lambda; EU may not be available)
4. Filesystem: leave default (1.4 TiB SSD)
5. SSH key: select the `cnsm2027` key
6. Click Launch

Provisioning takes 1 to 3 minutes. Lambda dashboard shows instance with public IP when ready.

### 14.3 First connection

```bash
ssh -i ~/.ssh/cnsm2027_ed25519 ubuntu@<lambda-ip>
```

Verify GPU available:

```bash
nvidia-smi
# expected: detailed information about A10 24GB
```

### 14.4 Add to local SSH config

```bash
cat >> ~/.ssh/config << 'EOF'

Host cnsm-lambda-01
    HostName <lambda-ip>
    User ubuntu
    IdentityFile ~/.ssh/cnsm2027_ed25519
    IdentitiesOnly yes
EOF
```

### 14.5 Snapshot strategy

After full configuration in chapters 15 and 16, you'll take a filesystem snapshot via Lambda dashboard. From that snapshot, future Lambda boots already come fully configured. This minimizes Lambda runtime cost.

**Important**: keep the instance running only during sprint windows. While idle, terminate (not stop) to avoid billing. The snapshot preserves state.

---

## Chapter 15: Installing Zabbix Agent on Lambda with GPU metrics

The Lambda host needs to be a regular Zabbix monitored host, but with extra GPU metrics.

### 15.1 Manual installation of Zabbix agent on Lambda

Since this is one host (not 12), Ansible is overkill. Simple manual steps:

```bash
ssh cnsm-lambda-01

# install Zabbix repository
wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_7.0-1+ubuntu24.04_all.deb
sudo dpkg -i zabbix-release_7.0-1+ubuntu24.04_all.deb
sudo apt update

# install agent 2
sudo apt install -y zabbix-agent2 zabbix-agent2-plugin-*

# create study directories
sudo mkdir -p /opt/cnsm-study/{scripts,workloads} /var/log/cnsm-faults /var/log/cnsm-workloads

# minimal config
sudo tee /etc/zabbix/zabbix_agent2.conf > /dev/null << 'EOF'
PidFile=/var/run/zabbix/zabbix_agent2.pid
LogFile=/var/log/zabbix/zabbix_agent2.log
LogFileSize=10
DebugLevel=3

# Replace with your real server FQDN
Server=zabbix.themonitoring.ai
ServerActive=zabbix.themonitoring.ai
Hostname=cnsm-lambda-01
HostMetadata=study=cnsm2027,group=lambda

RefreshActiveChecks=60
BufferSend=5
BufferSize=100

AllowKey=system.run[*]
Include=/etc/zabbix/zabbix_agent2.d/*.conf
EOF
```

### 15.2 GPU-specific user parameters

Create file with GPU metrics via nvidia-smi:

```bash
sudo tee /etc/zabbix/zabbix_agent2.d/userparameter_gpu.conf > /dev/null << 'EOF'
# GPU utilization (percentage)
UserParameter=cnsm.gpu.utilization,nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -1

# GPU memory used (MB)
UserParameter=cnsm.gpu.memory.used,nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1

# GPU memory total (MB)
UserParameter=cnsm.gpu.memory.total,nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1

# GPU memory percentage
UserParameter=cnsm.gpu.memory.percent,nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | head -1 | awk -F, '{printf "%.1f", $1*100/$2}'

# GPU temperature (Celsius)
UserParameter=cnsm.gpu.temperature,nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1

# GPU power draw (Watts)
UserParameter=cnsm.gpu.power.draw,nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits | head -1

# GPU SM clock (MHz)
UserParameter=cnsm.gpu.clock.sm,nvidia-smi --query-gpu=clocks.current.sm --format=csv,noheader,nounits | head -1

# GPU memory clock (MHz)
UserParameter=cnsm.gpu.clock.memory,nvidia-smi --query-gpu=clocks.current.memory --format=csv,noheader,nounits | head -1

# Number of compute processes on GPU
UserParameter=cnsm.gpu.processes.count,nvidia-smi --query-compute-apps=pid --format=csv,noheader | wc -l
EOF
```

### 15.3 Standard study user parameters (same as OVH)

```bash
sudo tee /etc/zabbix/zabbix_agent2.d/userparameter_study.conf > /dev/null << 'EOF'
UserParameter=cnsm.fault.active,test -f /var/run/cnsm-fault-active && echo 1 || echo 0
UserParameter=cnsm.fault.class,cat /var/run/cnsm-fault-class 2>/dev/null || echo "none"
UserParameter=cnsm.workload.heartbeat,systemctl is-active cnsm-workload >/dev/null 2>&1 && echo 1 || echo 0
EOF
```

### 15.4 Start agent

```bash
sudo systemctl enable --now zabbix-agent2
sudo systemctl status zabbix-agent2
# verify active and no errors

# manual test of the GPU parameter
zabbix_agent2 -t cnsm.gpu.utilization
# expected: returns numeric value
```

### 15.5 Register Lambda host in Zabbix

In Zabbix frontend, similar to OVH hosts:

1. Configuration > Hosts > Create host
2. Host name: `cnsm-lambda-01`
3. Group: `cnsm2027-study`
4. Interface: Agent, Lambda public IP, port 10050
5. Templates: link `Template CNSM2027 Study Host` (same as OVH) + create new `Template CNSM2027 GPU Host` containing the GPU items, OR add the GPU items directly via the host's items tab
6. Tags: `study=cnsm2027`, `group=lambda`
7. Save

Verify ZBX green within 1 to 2 minutes. Latest data should show GPU metrics.

---

## Chapter 16: Deploying the Lambda GPU-aware fault injector

This chapter deploys the Lambda equivalent of the OVH fault injector, but with GPU-specific fault classes per the locked protocol.

### 16.1 Generate Lambda fault schedule

This artifact (`artifacts/lambda_fault_injector.py` and the corresponding schedule generator) is delivered separately. After generating, you commit the resulting schedule.

Once delivered, generate:

```bash
cd ~/work/themonitoring/cnsm2027/behavioral-stability-aiops-study
python3 artifacts/lambda_fault_schedule_gen.py \
    --start 2026-07-15 --days 28 --seed 42 \
    --output protocols/fault_schedule_lambda_cycle1.csv
```

The 2026-07-15 start date corresponds to the start of Sprint S2 (week 9 of cycle 1). Adjust to your actual S2 start.

### 16.2 Pre-register the Lambda schedule

Same discipline as OVH:

```bash
git add protocols/fault_schedule_lambda_cycle1.csv
git commit -m "Pre-register Lambda S2 GPU-aware fault schedule (seed 42, 28 days)"
git push
```

This commit must happen BEFORE Sprint S2 begins.

### 16.3 Install and run the Lambda fault injector

The deployment is also manual since Lambda is one host:

```bash
scp artifacts/lambda_fault_injector.py cnsm-lambda-01:/tmp/
scp protocols/fault_schedule_lambda_cycle1.csv cnsm-lambda-01:/tmp/

ssh cnsm-lambda-01
sudo mkdir -p /etc/cnsm
sudo cp /tmp/fault_schedule_lambda_cycle1.csv /etc/cnsm/fault_schedule.csv
sudo cp /tmp/lambda_fault_injector.py /opt/cnsm-study/scripts/
sudo chmod +x /opt/cnsm-study/scripts/lambda_fault_injector.py

# install dependencies for GPU fault injection
sudo apt install -y stress-ng iproute2
pip install --user pynvml torch  # if not already there from base image

# install cron job
echo "* * * * * root /opt/cnsm-study/scripts/lambda_fault_injector.py --schedule /etc/cnsm/fault_schedule.csv --host cnsm-lambda-01 >> /var/log/cnsm-faults/cron.log 2>&1" | sudo tee /etc/cron.d/cnsm-fault-lambda

sudo systemctl restart cron
exit
```

### 16.4 Validation of GPU-aware ground truth

Test forced injection of a GPU fault:

```bash
ssh cnsm-lambda-01
sudo /opt/cnsm-study/scripts/lambda_fault_injector.py \
    --schedule /etc/cnsm/fault_schedule.csv \
    --host cnsm-lambda-01 \
    --window-seconds 999999

# in parallel, in another terminal:
ssh cnsm-lambda-01 "cat /var/run/cnsm-fault-active; cat /var/run/cnsm-fault-class"
# should show 1 and the active class name (e.g., gpu_utilization_spike)

# check that GPU metrics in Zabbix reflect the fault
# in Zabbix Latest data: cnsm.gpu.utilization should spike during the injection

exit
```

If GPU utilization in Zabbix correlates with `cnsm.fault.active` going to 1, your ground truth is armed for cross-environment evaluation.

---

## Chapter 17: Cross-environment evaluation pipeline

This chapter describes the data analysis pipeline that consumes data from both environments and produces the cross-environment metrics for the paper. It is conceptual, not executable yet (the analysis code is delivered later, after data is collected).

### 17.1 Data flow

```
[OVH 12 hosts] -- Zabbix --> [Zabbix server] -- nightly export --> [OVH Object Storage Parquet]
[Lambda A10]  -- Zabbix --> [Zabbix server] -- nightly export --> [OVH Object Storage Parquet]
                                                                            |
                                                                            v
                                                              [analysis notebook on Lambda S3]
                                                                            |
                                                                            v
                                                         [results / figures / paper]
```

### 17.2 Cross-environment matching via ontology

For RQ2 and RQ3, you need to match events between OVH and Lambda. The protocol section 5.2.1 defines the mapping table:

| OVH class | Lambda class | Ontology concept |
|-----------|--------------|------------------|
| cpu_spike | gpu_utilization_spike | compute_saturation |
| memory_pressure | gpu_memory_pressure | memory_pressure |
| disk_io | disk_io_contention | io_bottleneck |
| network_latency | data_loader_bottleneck | network_degradation |
| process_leak | batch_inference_overload | process_instability |

The pipeline:
1. Loads all OVH fault events with class label
2. Loads all Lambda fault events with class label
3. Maps both to ontology concepts via the table
4. Computes F1, MTTD, false alarm rate per ontology concept (5 paired comparisons)
5. Computes SHAP attributions in ontology-mapped feature space
6. Computes cosine similarity per ontology concept

The Lambda-only class `cpu_contention_during_training` is excluded from paired analysis (per locked protocol section 5.2.1) but reported in within-Lambda metrics.

### 17.3 Detection window enforcement

Per protocol section 8.2:
- Alert in `[fault_start, fault_end]` = TP
- Alert in `[fault_start - 60s, fault_start)` = early warning, separate analysis
- Alert outside any fault window = FP
- Alert during natural workload spike (not in fault schedule) = FP

The pipeline reads both schedules (OVH and Lambda) and enforces these rules when computing metrics. Code delivered separately.

### 17.4 Statistical analysis

Per protocol section 8.3:
- 5 runs per configuration with different random seeds
- Bootstrap 95% CI (n=1000)
- Wilcoxon signed-rank for pairwise comparison
- Bonferroni correction for multiple comparisons
- Cohen's d / rank-biserial for effect size

This requires running training and evaluation 5 times. Plan Lambda S3 sprint accordingly.

---

## Chapter 18: Data management, backup, and retention

The earlier reviewer identified this as a missing piece. Now formalized.

### 18.1 Storage layers

**Layer 1: Zabbix database (live)**
- 90 days history retention for study items
- Used for live monitoring and quick analysis
- Bottleneck: query performance degrades for large date ranges

**Layer 2: Object Storage Parquet (archive)**
- Nightly export from Zabbix to OVH Object Storage
- Format: Parquet partitioned by date and host
- Retention: indefinite (cheap, ~2 EUR/month for cycle 1 dataset)
- Used for analysis, reproducibility, paper figures

**Layer 3: GitHub release (publication snapshot)**
- Subset of Layer 2 corresponding to the paper
- Released with paper acceptance, archived via Zenodo
- Has its own DOI
- Used by reviewers and replicators

### 18.2 Schema for Parquet files

Each daily export produces files with schema:

| Column | Type | Description |
|--------|------|-------------|
| timestamp | int64 (Unix seconds) | Metric collection time |
| host | string | e.g., cnsm-web-01 |
| metric_key | string | e.g., system.cpu.util |
| value | double | Numeric value |
| value_str | string (nullable) | For text metrics |

Plus a separate `events.parquet` containing fault injection records:

| Column | Type | Description |
|--------|------|-------------|
| host | string | |
| fault_class | string | |
| start_ts | int64 | Unix seconds |
| end_ts | int64 | Unix seconds |
| parameters | string | Original injection parameters |
| ontology_concept | string | Mapped via table 5.2.1 |

### 18.3 Backup policy

- Nightly export protects against Zabbix database loss
- Monthly snapshot of OVH Object Storage bucket (versioned)
- Quarterly download of full dataset to local NAS or alternate cloud (defense against credential compromise)

### 18.4 Anonymization

Since this is synthetic workload on dedicated study hosts, no real user data is collected, hence no anonymization is required. This is documented in the paper to address ethics concerns proactively.

### 18.5 Cost estimate

OVH Object Storage:
- ~15 GB compressed per cycle, 45 GB total for 3 cycles
- Pricing: approximately 0.01 EUR/GB/month
- Total: 0.45 EUR/month, negligible

The actual export script (`artifacts/nightly_export.py`) is delivered separately.

---

## Chapter 19: Lab notebook discipline (mandatory from day 1)

The earlier guide treated lab notebook as monthly. Reviewer feedback (correctly) elevated this to mandatory daily-or-on-event.

### 19.1 Why daily-or-on-event

The lab notebook is one of the strongest pieces of evidence for the doctoral portfolio. Reviewers and examiners value seeing how decisions were made, not just the polished final result. A monthly summary reconstructs decisions in retrospect, which is weaker than recording them as they happen.

### 19.2 Format

In the repository:

```
lab_notebook/
├── 2026-05.md   # one file per month, entries chronologically inside
├── 2026-06.md
└── ...
```

Each entry has:

```markdown
## 2026-05-14 14:30 UTC

**Context**: brief situation
**Decision or observation**: what happened
**Justification**: why this decision was made
**Impact on protocol**: any change required to EXPERIMENTAL_SETUP.md
**Follow-up needed**: any open action
```

### 19.3 What requires an entry

**Always**:
- Any change to running configuration of any host
- Any host going offline or coming back online
- Any deviation from the protocol (even small)
- Any unexpected metric pattern observed
- Any decision about the analysis approach
- Any external event affecting the study (OVH outage, Zabbix server change, voucher issue)

**Daily during data collection**:
- Brief health check note even if everything is normal: "All 12 hosts ZBX green, no anomalies, no interventions today"

**Optional**:
- Reading or paper review notes that influence the study
- Conversations with collaborators or advisors

### 19.4 Commit cadence

Push lab notebook to public repo at least weekly. Daily is better. The git timestamps strengthen the credibility of the diary.

---

## Chapter 20: Halt criteria

Objective conditions under which you pause the experiment to investigate. Pre-defining these prevents you from rationalizing in real time.

### 20.1 Critical halt conditions (stop immediately)

Stop and investigate before continuing:

- More than 2 of 12 OVH hosts offline simultaneously for more than 6 hours
- Zabbix server unable to receive metrics for more than 2 hours
- Detection of data corruption in any export Parquet file
- Voucher consumption exceeds 200% of projected (signals billing issue)
- Detection that fault injection is not actually firing (cron job broken)
- Any indication of unauthorized access to study hosts

### 20.2 Warning conditions (investigate within 24 hours)

Continue running but investigate:

- 1 of 12 OVH hosts offline for more than 1 hour
- Zabbix metric ingestion delay above 5 minutes
- Voucher consumption 130% to 200% of projected
- Fault injection rate observed to be more than 20% off from schedule
- Workload generator failed restart on any host

### 20.3 Halt procedure

If any critical condition triggers:

1. Note timestamp and condition in lab notebook immediately
2. Stop data collection if necessary (`systemctl stop cnsm-workload` cluster-wide via Ansible)
3. Investigate root cause without making changes that erase evidence
4. Document findings
5. Decide: resume from current state, or rollback to a known-good snapshot, or continue with caveat documented in protocol amendment
6. If protocol amendment is needed, version the protocol (v3.2) and commit explanation in lab notebook
7. Push everything to public repo before resuming

### 20.4 Reporting in the paper

Any halt event is reported transparently in the paper's "Threats to validity" or methodology section. Hiding halts is dishonest and reviewers can sometimes detect inconsistencies.

---

## Chapter 21: Go / No-Go checklist before data collection starts

Run this checklist on the day before May 15, 2026 (or whatever your real start date is). Every item must be ✅ to proceed.

### 21.1 Required artifacts in repo

- [ ] `EXPERIMENTAL_SETUP.md` v3.1 LOCKED committed
- [ ] `THREE_CYCLE_PLAN.md` committed
- [ ] `OPERATIONAL_GUIDE.md` v2 committed
- [ ] `protocols/fault_schedule_cycle1.csv` committed (1008 events, seed 42)
- [ ] `protocols/fault_schedule_cycle2.csv` committed
- [ ] `protocols/fault_schedule_cycle3.csv` committed
- [ ] `infra/` directory fully version-controlled
- [ ] `artifacts/zabbix_template_cnsm2027.xml` committed
- [ ] `artifacts/lambda_fault_injector.py` committed (even though Lambda starts week 5)
- [ ] `artifacts/nightly_export.py` committed
- [ ] `LICENSE` (Apache 2.0) committed
- [ ] `README.md` committed with study status, target venues, repository structure

### 21.2 OSF pre-registration

- [ ] OSF project created
- [ ] Protocol uploaded
- [ ] Schedules uploaded
- [ ] Registration submitted (DOI in hand)
- [ ] OSF DOI added to repository README

### 21.3 OVH infrastructure

- [ ] 12 VPS provisioned in SBG, all reachable via SSH
- [ ] Voucher balance confirmed (>=10000 EUR or partial as expected)
- [ ] Local SSH config has all 12 hosts
- [ ] Local Ansible inventory `hosts.ini` populated with real OVH hostnames
- [ ] `ansible all -i inventory/hosts.ini -m ping` returns 12 SUCCESS
- [ ] Bootstrap playbook completed successfully on all 12
- [ ] Zabbix agent installed on all 12
- [ ] Zabbix template imported in server
- [ ] All 12 hosts registered in Zabbix and showing ZBX green
- [ ] Custom items (cnsm.fault.active, etc) returning values for all 12
- [ ] Workload services active on all 12
- [ ] Fault injector cron deployed on all 12
- [ ] Manual fault injection test successful (ground truth verified in Zabbix)

### 21.4 Lambda preparation (does not need to be running yet)

- [ ] Lambda Cloud account active with credit voucher applied
- [ ] SSH key registered on Lambda
- [ ] A10 instance type confirmed available in chosen region
- [ ] Lambda snapshot strategy understood and documented

### 21.5 Operational readiness

- [ ] Lab notebook directory `lab_notebook/` exists in repo
- [ ] First lab notebook entry committed (today's date, "Cycle 1 starts")
- [ ] Calendar reminders set: weekly voucher check, monthly summary, sprint S1/S2/S3 dates
- [ ] Halt criteria reviewed and understood

### 21.6 Backup and disaster recovery

- [ ] OVH Object Storage bucket created for nightly exports
- [ ] Test export of one day's data successful
- [ ] Local backup destination identified (NAS or alternate cloud)

If all items are ✅, you are GO. Push the lab notebook entry "Cycle 1 GO at YYYY-MM-DD HH:MM UTC" and start.

If any item is ❌, you are NO-GO. Resolve the blocker before starting. Do not start with caveats.

---

## Chapter 22: Daily, weekly, and monthly operations

Once collection is running, your job is mostly observation with intervention only when needed.

### 22.1 Daily (5 minutes)

- Open Zabbix frontend, verify 12 hosts still ZBX green
- Latest data spot-check on 1 or 2 hosts: metrics still flowing every 15s
- `cnsm.fault.active` toggling correctly (sometimes 1, sometimes 0, never stuck)
- Lab notebook entry: at minimum "All 12 hosts healthy, no intervention. Voucher balance approximately X EUR."
- If any host is down, investigate immediately and document

### 22.2 Weekly (15 minutes)

- Verify OVH voucher consumption (Payment methods > vouchers)
- Run Ansible health check:
  ```bash
  ansible all -i inventory/hosts.ini -m shell -a "df -h / | tail -1"
  ```
  If any disk above 80%, plan cleanup (old logs, snapshots, etc)
- Check `/var/log/cnsm-faults/executions.log` on a sampled host: faults executing as scheduled
- Verify nightly Parquet export succeeded for the week (check OVH Object Storage)
- Push lab notebook updates to public repo

### 22.3 Monthly (1 hour)

- Backup nominal: snapshot of OVH Object Storage bucket
- Update monthly summary at top of `lab_notebook/YYYY-MM.md`
- Review halt criteria: anything getting close to a warning threshold?
- Push to public repo with clear monthly tag if convenient

### 22.4 Sprint windows (per Lambda schedule)

- Week 5: launch Lambda S1, run training scripts, take snapshot at end, terminate instance
- Week 9: launch Lambda S2 from snapshot, deploy fault injector, monitor for 4 weeks, terminate
- Week 13: launch Lambda S3 from snapshot for ablations, terminate

Each sprint launch and termination gets a dedicated lab notebook entry.

---

## Chapter 23: Troubleshooting common scenarios

### 23.1 A VPS dies / does not respond

Symptom: ZBX red, SSH fails.

Response:
1. Check VPS status in OVH Manager
2. If "stopped", restart via Manager
3. If "running" but inaccessible, reboot via Manager
4. If persists, open ticket OVH Startup Program (not regular support, always via Startup)
5. Document the gap in lab notebook
6. In paper: report uptime honestly, do not hide

### 23.2 Workload hangs or consumes excessively

Symptom: insane load average, sustained 100% CPU on a host that should not.

Response:
1. SSH to host
2. `sudo systemctl stop cnsm-workload` to stop
3. Investigate: `journalctl -u cnsm-workload --since "1 hour ago"`
4. Adjust script if necessary (commit fix to repo, document in lab notebook)
5. `sudo systemctl start cnsm-workload`
6. If repeated, may need to reduce workload intensity or revisit design

### 23.3 Fault injection does not fire

Symptom: `executions.log` without new lines.

Response:
1. SSH to host
2. `sudo crontab -l` confirm cron job
3. `sudo /opt/cnsm-study/scripts/inject_fault.py --schedule /etc/cnsm/fault_schedule.csv --host $(hostname) --window-seconds 999999` force execution
4. If error, read Python traceback and fix
5. If OK, problem is cron daemon: `sudo systemctl restart cron`

### 23.4 Zabbix server overloaded

Symptom: Zabbix queue growing, data arriving late.

Response:
1. Increase `StartPollers` in Zabbix server config
2. Consider increasing server resources (CPU/RAM)
3. Consider reducing polling to 30s instead of 15s (second choice, prefer the first)
4. Document the change in lab notebook with timestamp: this is a methodological change

### 23.5 OVH voucher running out before expected

Symptom: balance falling faster than projected.

Response:
1. Check transaction history to identify drift
2. Contact your Startup Program Manager (Jonathan B. Clarke for Southern Europe)
3. Can request extension if justified by published peer-reviewed track record
4. If extension not granted, plan to scale down to 6 hosts after cycle 1, document in protocol amendment

### 23.6 Lambda instance unavailable in region

Symptom: A10 out of capacity when launching.

Response:
1. Try alternative regions in Lambda dashboard
2. If unavailable globally, postpone sprint by a few days
3. If persistent, consider alternative GPU providers (Vast.ai, RunPod) and document the change as protocol amendment

### 23.7 GPU fault injection causes Lambda instance crash

Symptom: stress-ng or CUDA experiment causes the Lambda instance to become unresponsive.

Response:
1. Reboot via Lambda dashboard
2. Reduce intensity of the offending fault class (fewer threads, smaller allocations)
3. Update `lambda_fault_injector.py` and re-deploy
4. Document the adjustment in lab notebook and as protocol amendment

---

## Closing note

This guide takes you from zero to first experiment running. When you complete chapters 1 through 21, you will have:

- Public GitHub repo with full pre-registration
- 12 OVH VPS running heterogeneous workloads for 90 days
- Lambda A10 ready for sprints
- Zabbix collecting at 15s granularity in both environments
- Automated fault injection with synchronized ground truth (OVH + GPU-aware on Lambda)
- Cross-environment evaluation pipeline understood, ready for analysis
- Data management, backup, halt criteria, and lab notebook discipline in place
- Defensible scientific basis for NOMS 2027, CNSM 2027, and the doctoral portfolio

Once Cycle 1 collection is complete, you re-use the same infrastructure for Cycles 2 and 3 by simply changing the active fault schedule (cycle2, cycle3) and varying one experimental dimension per cycle, per `THREE_CYCLE_PLAN.md`.

The next deliverables (Zabbix template XML, Lambda fault injector, nightly export script) will complete the artifact set. Until they are delivered and committed, the study is in NO-GO state per Chapter 21.
