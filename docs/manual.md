# RT System Integration Framework (RTSI-FW) User Manual

[日本語マニュアル](manual.ja.md) | [English README](../README.md)

> Applies to: v1.0 (`main`)

## 1. Overview
RTSI-FW is a robot system operation and management framework compliant with RoIS 2.0. It reads robot configuration files and scenario files to automate the collection and building of required packages, network configuration, module startup, and execution of the Service Application.

```text
Systemoperate.py
  ├─ Robot configuration file (ROBOT.yaml)
  ├─ Scenario file (scenario.yaml)
  ├─ Wasanbon / Wasanbon Web Framework
  └─ Service Application (ROS1 / ROS2)
       └─ common_hri_ros1 / common_hri_ros2
            └─ Robot-specific Action nodes
                 └─ Physical robots / simulators
```

## 2. Development Environment
- Programming language: Python
- OS: Ubuntu 20.04 / 22.04
- ROS: ROS 1 Noetic / ROS 2 Humble
- RT middleware: OpenRTM-aist 2.0

## 3. Prerequisites
The PCs used to run the framework must have the required middleware, including ROS and RTM, as well as [Wasanbon](https://github.com/rsdlab/wasanbon) and the [Wasanbon Web Framework](https://github.com/rsdlab/wasanbon_webframework), installed.

### 3.1 Clone the Repository
Obtain the required repository:

```bash
cd ~
git clone https://github.com/rsdlab/RTSI_FW.git
cd RTSI_FW
```

**Note:** In the current implementation, robot configuration files and scenario files are loaded from `$HOME/RTSI_FW/`. Therefore, the repository must be placed directly under the home directory.

### 3.2 Set Environment Variables
`Systemoperate.py` references `ROS_WS` and `RTM_WS` at startup. Set both variables according to your environment.

```bash
# Example for ROS 2 (adjust the workspace paths for your environment)
export ROS_WS="$HOME/colcon_ws"
export RTM_WS="$HOME/rtm_ws"
source /opt/ros/humble/setup.bash
# If already built: source "$ROS_WS/install/setup.bash"
```

## 4. Robot Configuration File
The robot configuration file contains robot-specific settings and is referenced when `Systemoperate.py` runs.

| Field | Description |
| --- | --- |
| `collect` | Packages and dependencies to obtain, including `rtm`, `engine`, `apt`, `pip`, and `git` |
| `setup` | Initialization operations (`actions`) and completion checks (`checks`) |
| `run` | `system` and `module` commands to start on each PC |
| `network` | PC identifiers, connection information, and local-PC designation |
| `ros.version` | `1`: ROS 1; `2`: ROS 2 |
| `ros2.domain_id` | ROS 2 Domain ID (required only when using ROS 2) |

### 4.1 `collect`
Specify the HRI package name in `engine` and the repository source in `git`. If there are no items to obtain, specify an empty list (`[]`) or a list containing `null`.

### 4.2 `setup`
The `setup` section defines operations that must be completed in advance, such as enabling the servos. Each step can specify a `name`, `package`, startup `actions`, and completion `checks`.

| Field | Description |
| --- | --- |
| `name` | Name of the operation |
| `package` | Name of the package used for the operation |
| `actions` | `controller`: ID of the PC on which to perform the operation<br>Specify one of `cmd`, `system`, or `module`, depending on the startup command |
| `checks` | `controller`: ID of the PC on which to run the check<br>`cmd`: command to execute<br>`arg`: command arguments |

**Note:** A check script verifies whether an operation in `actions` has completed successfully. It must output only `True` or `False` (for example, `data_monitor.py`).

### 4.3 `run`
Specify the modules to start:

```yaml
run:
  pc1:
    system: []
    module:
      - hsr_hri_action Move_action
      - hsr_hri_action Approach_action
```

The `system` field specifies files that start multiple components (such as ROS launch files or RTM rtsp files), while `module` specifies individual executables (such as nodes or RTCs). Write each entry as `package_name file_name`, separated by a single space and without a file extension.

### 4.4 `network`

```yaml
network:
  - id: pc1
    local: true
    host: "YOUR_IP_HERE"
    user: "YOUR_USERNAME_HERE"
    pswd: "YOUR_PASSWORD_HERE"
```

This section maps PC IDs used in `run` and `setup` (for example, `pc1` and `pc2`) to their connection information. Enter the information for the local PC (where `Systemoperate.py` and the engine run) under `pc1`.

| Field | Description |
| --- | --- |
| `id` | Arbitrary identifier for the PC |
| `local` | `true` for the local PC; `false` otherwise |
| `host` | IP address |
| `user` | Username |
| `pswd` | Password for the specified user |

### 4.5 `ros` / `ros2`
Specify the ROS version and, when using ROS 2, the Domain ID:

```yaml
ros:
  version: 2
ros2:
  domain_id: 1
```

## 5. Scenario File
The scenario file specifies the tasks to execute and their parameters.
The current Service Application assumes the filename `scenario.yaml`.

## 6. Running the Framework
### 6.1 Command Format

```bash
python3 Systemoperate.py <robot_name> <scenario_name> <operation> <master_ip>

# Example
python3 Systemoperate.py HSR scenario run 192.168.50.111
```

**Note:** In the verified Service Application (`service_app`) implementation, the scenario is loaded from the fixed path `$HOME/RTSI_FW/scenario.yaml`. Therefore, the scenario specified by the second command-line argument is not necessarily the one executed by the Service Application.

### 6.2 Available Operations

| Operation | Main function |
| --- | --- |
| `collect` | Collect required packages based on the robot configuration and scenario |
| `build` | Build ROS/RTM packages and perform builds via the Wasanbon Web API |
| `set` | Configure the ROS 1/ROS 2 communication environment and network |
| `run` | Start servers, perform setup, launch modules, and start the Service Application |
| `setrun` | Perform `set` followed by `run` |

### 6.3 Internal Execution Flow
When `run` or `setrun` is executed, the following operations are performed:

1. Read the robot configuration and scenario files, and determine the ROS version.
2. Place the robot-specific `robot.yaml` and `hri.xml` files in `common_hri_ros1` or `common_hri_ros2`.
3. Configure communication settings if necessary (`setrun`).
4. Check startup of servers such as Wasanbon Web, and perform setup operations.
5. Start modules through the Web API according to the robot-specific `run` settings.
6. Generate and execute the startup configuration for the HRI functions required by the scenario.
7. Start the Service Application.

In the current implementation, requests to Wasanbon Web use `http://<host>:8000/`.

## 7. References

- [RTSI-FW Japanese README](../README.ja.md)
- [RTSI-FW English README](../README.md)
- [Previous version (v0.8)](https://github.com/rsdlab/RTSI_FW/tree/v0.8)
