# Sync 

## Overview
The `airlab sync` command facilitates file synchronization between local and remote robot systems using rsync, with support for selective syncing, dry runs, and time synchronization.

## Syntax
```bash
airlab sync <robot_name> [options]
```

## Arguments
- `<robot_name>`: Name of the target robot (must be defined in robots.yaml)

## Options
- `--dry-run`: Preview synchronization without making changes
- `--delete`: Remove files on remote that don't exist locally
- `--path=<relative_path>`: Sync specific directory relative to workspace
- `--exclude=<pattern>`: Skip files/directories matching pattern
- `--time`: Synchronize system time between local and remote
- `--progress`: Show progress during the sync operation (useful for large transfers; may slow down the sync)
- `--password`: Skip key-based SSH authentication and prompt for a password directly
- `--help`: Display usage information

## Configuration Files

### Robot Registry (`robots.yaml`)
- Location: `$AIRLAB_PATH/robot/robots.yaml`
- Each robot is a system with one or more named network addresses (a `default`
  plus optional ones like `internet`/`vpn`); `airlab sync` resolves the target's
  SSH address from it. Use `--address <name>` to pick a non-default address.

### Robot Information (`robot_info.yaml`)
- Location: `$AIRLAB_PATH/robot/robot_info.yaml`
- Contains workspace paths for remote systems
- Format:
  ```yaml
  robot_name:
    ws_path: /path/to/workspace
  ```

## Default Exclusions
The following patterns are automatically excluded from synchronization:
- `.git/`: Version control files
- `build/`: Build directories
- `devel/`: Development directories
- `log/`: Log files
- `install/`: Installation files
- `*.pyc`: Python bytecode
- `__pycache__`: Python cache directories
- `*.env`: Environment files — **except** the launch tree's per-block arch env files
  (`<block>/x86.env`, `<block>/jetpack.env`), which are re-admitted because they are
  tracked, shared and required: `launch/` cannot render a single compose file without
  them. What stays local is the per-machine root `airlab.env` and the `storage_tools_ws`
  `config*.env` files.

  The two `--include` rules sit **before** the `*.env` exclude — rsync applies the first
  matching rule, so reordering them would silently stop delivering the arch envs. They
  are also matched at any depth, so `--path=launch` (which moves the transfer root)
  keeps working.

## Features

### File Synchronization
1. Basic sync:
   ```bash
   airlab sync mt001
   ```

2. Selective sync:
   ```bash
   airlab sync mt001 --path=src/controllers
   ```

3. Preview changes:
   ```bash
   airlab sync mt001 --dry-run
   ```

### Time Synchronization
- Automatically syncs system time when `--time` flag is used
- Falls back to hardware clock if date command fails
- Reports time difference after synchronization

### Security Features
- Password-protected SSH authentication
- Connection timeout handling
- Verification of remote paths
- Error handling for failed operations

## Examples

### Basic Usage
```bash
# Simple sync
airlab sync mt001

# Sync with preview
airlab sync mt001 --dry-run

# Sync and remove extra files
airlab sync mt001 --delete
```

### Advanced Usage
```bash
# Sync specific directory
airlab sync mt001 --path=src/config

# Exclude specific files
airlab sync mt001 --exclude='*.log'

# Multiple excludes
airlab sync mt001 --exclude='temp/' --exclude='*.bak'

# Combine options
airlab sync mt001 --path=src/config --exclude='*.log' --dry-run
```

## Dependencies
Required software:
- rsync
- ssh
- sshpass
- date
- python3 with PyYAML (for config parsing)

## Error Handling
The script includes comprehensive error checking for:
- Missing dependencies
- Invalid configuration files
- SSH connection failures
- Remote path verification
- Synchronization failures
- Time synchronization issues

## Best Practices

### Synchronization
1. Always use `--dry-run` first for important syncs
2. Be cautious with `--delete` option
3. Use specific paths when possible
4. Verify remote workspace paths

### Configuration
1. Keep robots.yaml up to date
2. Verify workspace paths in robot_info.yaml
3. Use meaningful robot names
4. Document custom exclude patterns

## Troubleshooting

### Common Issues
1. "SSH connection failed":
   - Check network connectivity
   - Verify robots.yaml entries
   - Check SSH credentials

2. "Workspace path not found":
   - Verify robot_info.yaml entries
   - Check remote directory permissions
   - Ensure paths exist on remote system

3. "Sync failed":
   - Check disk space
   - Verify file permissions
   - Review rsync error messages

4. "Time sync failed":
   - Check sudo permissions
   - Verify system clock access
   - Check NTP settings

### Debug Steps
1. Use `--dry-run` to verify sync targets
2. Check SSH connection:
   ```bash
   ssh <robot_ssh_address>
   ```
3. Verify remote paths:
   ```bash
   ssh <robot_ssh_address> "ls -la <workspace_path>"
   ```
4. Test rsync manually:
   ```bash
   rsync -avz --dry-run <source> <destination>
   ```