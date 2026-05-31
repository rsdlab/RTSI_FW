#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import sys
import subprocess
from typing import Tuple


def parse_args(raw_args) -> Tuple[str, str, str, float, str]:
    # Accept comma-separated single argument or spaced arguments
    if len(raw_args) == 1 and ',' in raw_args[0]:
        parts = [p.strip() for p in raw_args[0].split(',') if p.strip()]
    else:
        parts = [p.strip() for p in raw_args]

    # Expected: middleware, timeout, topic, execution_name, [check_text]
    if len(parts) == 3:  # middleware omitted -> default ros
        middleware = 'ros'
        timeout_s, communication_data, execution_name = parts
        check_text = ''
    elif len(parts) >= 4:
        middleware, timeout_s, communication_data, execution_name = parts[:4]
        check_text = parts[4] if len(parts) >= 5 else ''
    else:
        raise ValueError("Usage: <middleware> <timeout> <communication_data> <execution_name>")

    try:
        timeout_val = float(timeout_s)
    except ValueError:
        raise ValueError(f"Invalid timeout: {timeout_s}")

    return middleware.lower(), communication_data, execution_name, timeout_val, check_text


def ros_check(topic: str, execution_name: str, timeout_s: float, check_text: str) -> bool:
    cmd = ["rostopic", "echo", "-n", "1", topic]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        print("rostopic not found", file=sys.stderr)
        return False

    output = (result.stdout or '').strip()
    # print(output)
    if not output:
        return False

    if execution_name.lower() == 'any':
        return True

    if execution_name.lower() == 'check':
        if not check_text:
            return False
        return check_text in output

    return execution_name in output


def rtm_check(*_args) -> bool:
    # RTM handling is not specified; return False for now.
    return False


def main():
    try:
        middleware, communication_data, execution_name, timeout_s, check_text = parse_args(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        print("false")
        sys.exit(1)

    if middleware == 'ros':
        ok = ros_check(communication_data, execution_name, timeout_s, check_text)
    elif middleware == 'rtm':
        ok = rtm_check(communication_data, execution_name, timeout_s)
    else:
        print(f"Unsupported middleware: {middleware}", file=sys.stderr)
        ok = False

    print("true" if ok else "false")


if __name__ == "__main__":
    main()
