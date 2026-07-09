# Real-hardware e2e (T3) — runner & robot setup

The T3 tier runs the airlab commands from an **operator** (Machine A, a self-hosted
GitHub Actions runner) against a **sacrificial robot** (Machine B) over the LAN.
Both are currently NVIDIA Jetson AGX Orin (**arm64/aarch64**) — but everything is
configurable, so physical machines and VMs are interchangeable.

The e2e job runs **nightly + on-demand only** (`schedule` + `workflow_dispatch`),
**never on `pull_request`**, so PR/fork code never runs on the self-hosted runner.

## Machine A — operator / self-hosted runner
As an **admin user** (has sudo):
```bash
sudo adduser --disabled-password --gecos "" airlab-ci   # unprivileged; NO sudo
sudo usermod -aG docker airlab-ci                        # docker access via group, not sudo
sudo apt-get update && sudo apt-get install -y \
    git python3 python3-venv python3-pip rsync openssh-client sshpass tmux curl jq
command -v docker || curl -fsSL https://get.docker.com | sudo sh   # skip if JetPack already ships docker
```
As **airlab-ci** (no sudo):
```bash
python3 -m pip install --user vcstool tmuxp
ssh-keygen -t ed25519 -N "" -C "airlab-ci@A" -f ~/.ssh/id_ed25519   # authorize the .pub on B
# GitHub Actions runner — ARM64 asset (Jetson is aarch64):
mkdir -p ~/actions-runner && cd ~/actions-runner
RUNNER_VER=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
curl -O -L "https://github.com/actions/runner/releases/download/v${RUNNER_VER}/actions-runner-linux-arm64-${RUNNER_VER}.tar.gz"
tar xzf "actions-runner-linux-arm64-${RUNNER_VER}.tar.gz"
./config.sh --url https://github.com/strapsai/airlab --token <RUNNER_TOKEN> \
    --labels self-hosted,linux,arm64,airlab-operator --unattended --replace
#   runner group: Default    work folder: _work    (accept defaults)
```
As **admin** — install as a service that runs *as* airlab-ci:
```bash
cd ~airlab-ci/actions-runner
sudo ./bin/installdependencies.sh    # only if config/run complains about libicu etc.
sudo ./svc.sh install airlab-ci && sudo ./svc.sh start
```
Verify: repo → Settings → Actions → Runners shows the Jetson **Idle** with the labels above; and as airlab-ci `docker ps` works without sudo (re-login if the group isn't active yet).

## Machine B — sacrificial robot
```bash
sudo apt-get update && sudo apt-get install -y openssh-server rsync python3 tmux
command -v docker || curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker <ROBOT_USER>
python3 -m pip install --user tmuxp
# authorize A's key:
echo "<A_PUBLIC_KEY>" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
# password auth ON (for auth/robot-setup password-fallback tests):
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart ssh
sudo passwd <ROBOT_USER>
```
B is **sacrificial**: the suite `rm -rf`s test scopes, prunes docker, edits `/etc/hosts`,
and may reboot it. There is no VM snapshot on bare metal — the suite instead
**resets B to a known state** (Option 1) at setup/teardown; take one full-disk image
(`dd` / Jetson SDK Manager) as disaster-recovery only.

Verify A→B (as airlab-ci): `ssh <ROBOT_USER>@<B_IP> 'hostname && docker version'` (passwordless).

## Configure the robot in CI (repo → Settings → Secrets and variables → Actions)
- **Variables**: `AIRLAB_TEST_ROBOT_ADDR`, `AIRLAB_TEST_ROBOT_USER`, `AIRLAB_TEST_ROBOT_PORT`
  (and optionally `AIRLAB_TEST_ROBOT_NAME`).
- **Secret**: `AIRLAB_TEST_ROBOT_PASSWORD` (never commit this).

The e2e job sets `AIRLAB_TEST_ROBOT_AVAILABLE=1` and passes these through; if they're
absent the e2e tests **skip** cleanly.

## Run e2e manually
- CI: Actions → **tests** → **Run workflow** (`workflow_dispatch`), or wait for the nightly schedule.
- On Machine A directly:
  ```bash
  cd test && python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
  AIRLAB_TEST_ROBOT_AVAILABLE=1 AIRLAB_TEST_ROBOT_ADDR=<ip> AIRLAB_TEST_ROBOT_USER=<user> \
    .venv/bin/python -m pytest e2e -m e2e -ra
  ```
