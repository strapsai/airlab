# Setup

This script facilitates the setup of the Airlab environment for both local and remote systems, providing robust management of configuration, installation, and deployment.

## Features

- **Local Environment Setup**: Configure and initialize the environment on your local machine.
- **Remote Environment Setup**: Set up the environment on a remote robot system using SSH.
- **Configuration Management**: Save and load environment configurations.
- **Customizable Paths**: Specify custom installation paths with options for overwriting. Users can define custom paths via the `--path` option during setup. If no custom path is specified, the script defaults to `~/airlab_ws`. For clarity, always ensure the desired paths are accessible and provide examples when possible.
- **Error Handling**: Logs warnings and errors for better debugging.
- **YAML Configuration**: Updates and manages robot-specific YAML configuration files.

## Usage

Run the script with the desired mode and options. The primary modes are `setup_local` and `setup_remote`.

### Local Setup

To configure the environment locally:

```bash
airlab setup local --path=/desired/installation/path
```

#### Options:
- `--path` : Specify the custom installation path. If not provided, defaults to ~/airlab_ws
- `--force`: Overwrite existing installations.
- `--password`: Skip key-based SSH authentication and prompt for a password directly (remote setup only).

When running airlab setup local, the command:
- Creates the Airlab directory structure
- Copies initial configuration files
- Sets up the environment variables(airlab.env)
- Updates the user's .bashrc file
- Creates an initial airlab.env file

---

### Remote Setup

To configure the environment on a remote robot system, add your robot to the `robots.yaml` registry in the `robot` folder of your workspace — as a system with an `os_user` and at least one network address. For example:
```yaml
systems:
  - system: robot1
    os_user: airlab
    type: robot
    network_addresses:
      - address_name: default
        ip: 192.45.34.1
        default: true
```

After that you can run the command:
```bash
airlab setup robot1 --path=/desired/installation/path
airlab setup robot1 --path=/desired/installation/path --force
```

#### Options:
- `--path` : Specify the custom installation path. If not provided, defaults to ~/airlab_ws.
- `--force`: Overwrite existing installations.
- `--password`: Skip key-based SSH authentication and prompt for a password directly.
- `--airlab-src=<dir>`: Install the airlab **tool** from a LOCAL source tree instead of downloading
  it from GitHub. Works online too; **required** with `--offline`.
- `--offline`: No-network remote install (for **in-field re-provisioning** of robots with no
  Internet). Uses `--airlab-src` for the tool, rsyncs the **airlab_ws repository content** from the
  local working tree (no `git clone`, and **never** the `*_ws` ROS workspace folders — those are
  delivered separately by `airlab sync`), and runs the robot's `install.sh --offline` (skips
  apt/pip, reuses the existing venv). Implies `--keep-env`. Assumes the robot already went through
  an online initial setup (apt deps + venv in place).
- `-y`, `--non-interactive`: Answer all prompts non-interactively (proceed / yes). Use for
  automation (e.g. the Ansible robot plays).
- `--keep-env`: Preserve the robot's existing `airlab.env` **and** the operator's local
  `robot/robot_info.yaml` (no regeneration, no clobber). Implied by `--offline`.
- `--no-reboot`: Never prompt for or perform the post-setup reboot.

##### In-field offline example
```bash
sudo airlab setup robot1 --offline --airlab-src=/home/dtc/Documents/yaoyu/airlab \
    --force -y --keep-env --no-reboot
```

When running airlab setup <system_name>, the command:
- Validates the robot configuration
- Connects to the remote system via SSH
- Sets up the remote environment
- Copies initial files
- Installs or updates the Airlab package
- Configures the remote environment(airlab.env file)
- Updates the remote .bashrc file

> **Note:** To update `/etc/hosts` with robot hostname mappings, use `airlab hosts set local` (for the local machine) or `airlab hosts set <robot_name>` (for a remote robot). See the [hosts documentation](/usr/local/bin/docs/hosts.md) for details.

## Error Handling

The script provides color-coded output for different types of messages:
- Green: Information messages (`[INFO]`)
- Yellow: Warning messages (`[WARN]`)
- Red: Error messages (`[ERROR]`)

## Configuration Files

### airlab.env
Contains environment variables for the Airlab workspace:
```bash
AIRLAB_PATH=/path/to/workspace
AIRLAB_SYSTEM=local|<robot_name>
ROBOT_NAME=local|<robot_name>
USER_NAME= <user_name>
USER= <user_name>
GROUP_NAME= <group_name>
GROUP_ID= <group id>
USER_ID= <user id>
DOCKER_BUILD_PATH= <path/to/docker/compose>
DOCKER_UP_PATH=<path/to/docker/compose>
LAUNCH_FILE_PATH=<path/to/launch/file>
```

### robots.yaml
The robot registry: each system lists its `os_user`, `type`, and one or more named
`network_addresses` (a `default`, plus optional ones like `internet`/`vpn`), each
with an `ip` and/or `hostname`. `airlab` resolves a robot's SSH address from here
(see `robot/robots.yaml` in your workspace for the full schema).

### Robot Information YAML
Located at `$AIRLAB_PATH/robot/robot_info.yaml`, stores robot-specific information.
System names are at the **top level** — there is no `robots:` root key:
```yaml
  robot_name:
    robot_ssh: "username@ip_address"
    ws_path: "/path/to/workspace"
    last_updated: "YYYY-MM-DD HH:MM:SS"
```

`robot_ssh`, `ws_path` and `last_updated` are **bookkeeping**, not environment
variables: the tool uses them to reach the machine and to date the entry, and
excludes them when regenerating that machine's `airlab.env`. Every other field is
an environment variable.

Example:
```yaml
  robot-1:
    LAUNCH_FILE_PATH: "/home/airlab/airlab_ws/launch/sample.yaml"
    DOCKER_UP_PATH: "/home/airlab/airlab_ws/docker/docker-compose.yml"
    DOCKER_BUILD_PATH: "/home/airlab/airlab_ws/docker/docker-compose.yml"
    ROBOT_NAME: "robot-1"
    AIRLAB_SYSTEM: "robot-1"
    USER_ID: "1000"
    GROUP_ID: "1000"
    GROUP_NAME: "airlab"
    USER_NAME: "airlab"
    ws_path: "/home/airlab/airlab_ws"
    robot_ssh: "airlab@10.3.1.130"
    last_updated: "2025-01-04 14:00:08"

```

## Best Practices

1. Always backup existing configurations before using the `--force` option
2. Use absolute paths or `~` notation when specifying custom paths
3. Verify robot configurations in `robots.yaml` before attempting remote setup
4. Test SSH connectivity before initiating remote setup
5. Review host file modifications after setup completion

## Notes

- Run `source ~/.bashrc` after setup to apply environment changes
- Remote setup may require system restart for all changes to take effect
- Host file modifications require sudo privileges
- Keep robots.yaml entries up to date with correct SSH addresses