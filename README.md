# RT System Integration Framework (RTSI-FW)

**English** | [日本語](README.ja.md)

## Overview
- A robot system operation and management framework compliant with RoIS 2.0.
- Supports the collection and building of required modules and scenario-based service execution.
- Consists of `Systemoperate.py`, which collectively manages module downloads and system startup; robot configuration files, which define robot-specific information required for operation; and scenario files, which define tasks and their parameters.

## Versions
| Version | Branch | Description |
| --- | --- | --- |
| v1.0 | `main` | Added ROS 2 support, unified HRI components, and made other improvements. |
| v0.8 | [`v0.8`](https://github.com/rsdlab/RTSI_FW/tree/v0.8) | Initial version supporting ROS 1 and RTM. |

## Development Environment
- Programming language: Python
- OS: Ubuntu 20.04 / 22.04
- ROS: ROS 1 Noetic / ROS 2 Humble
- RT Middleware: OpenRTM-aist 2.0

## Frameworks Used
- [wasanbon](https://github.com/rsdlab/wasanbon/tree/ros1-ros2)
- [Wasanbon Web Framework](https://github.com/rsdlab/wasanbon_webframework/tree/main)

## Additional Required Packages
| File / Directory | Description |
| --- | --- |
| [rois_env](https://github.com/rsdlab/rois_env) | Package containing the Service Application. |
| [common_hri_ros1](https://github.com/rsdlab/common_hri/tree/main/common_hri_ros1) | Package providing HRI functions for ROS 1. |
| [common_hri_ros2](https://github.com/rsdlab/common_hri/tree/main/common_hri_ros2) | Package providing HRI functions for ROS 2. |

## Repository Contents
| File / Directory | Description |
| --- | --- |
| `Systemoperate.py` | Command-line interface for package collection, building, communication configuration, and startup. |
| `ROBOT.yaml` | Robot-specific software, startup, and communication settings. |
| `scenario.yaml` | File defining the tasks to execute and their arguments. |
| `process_waweb/` | Utility scripts for starting and stopping Wasanbon Web. |
| `setup/` | Utilities for checking the completion of initialization procedures. |

## System Architecture
```text
  Systemoperate.py (System Operation and Management)
          ↓
  HRI Components [common_hri_ros1 / common_hri_ros2]
          ↓
  Execution Nodes [airec_hri_action / hsr_hri_action, etc.]
          ↓
  Physical Robots / Simulators
```

## Documentation
Manual: [English](docs/manual.md) | [日本語](docs/manual.ja.md)
