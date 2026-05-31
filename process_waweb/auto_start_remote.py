#!/usr/bin/env python3


from __future__ import annotations

import io
import json
import re
from typing import List, Dict, Any

import pexpect


BEFORE_MARK = "------------- Before server_launch.sh execution--------------"
AFTER_MARK = "------------- After server_launch.sh execution --------------"
UVICORN_HEADER = "------ uvicorn process list ------"
PID_HEADER = "PID"


def _parse_uvicorn_pids(block: str) -> List[int]:
    pids: List[int] = []
    in_table = False
    for line in block.splitlines():
        line = line.rstrip("\n")
        if not in_table:
            if line.strip().startswith(PID_HEADER):
                in_table = True
            continue
        if not line.strip():
            break
        m = re.match(r"\s*(\d+)\s+\[", line)
        if m:
            pids.append(int(m.group(1)))
    return pids


def _parse_start_output_for_new_pids(output: str) -> List[int]:
    def extract_block(text: str, mark: str) -> str:
        i = text.find(mark)
        if i == -1:
            return ""
        sub = text[i:]
        j = sub.find(UVICORN_HEADER)
        if j == -1:
            return ""
        return sub[j + len(UVICORN_HEADER):]

    before_block = extract_block(output, BEFORE_MARK)
    after_block = extract_block(output, AFTER_MARK)

    before_pids = _parse_uvicorn_pids(before_block)
    after_pids = _parse_uvicorn_pids(after_block)

    if not after_pids and UVICORN_HEADER in output and PID_HEADER in output:
        after_pids = _parse_uvicorn_pids(output.split(UVICORN_HEADER, 1)[1])

    return sorted(set(after_pids) - set(before_pids)) if after_pids else []


def start_remote(host: str, user: str, password: str, *, timeout: int = 10, verbose: bool = False) -> Dict[str, Any]:
    """Run remote start for a single host via builtin `--other_hosts` flow.

    Returns: { 'returncode': int, 'new_pids': List[int], 'stdout': str }
    """
    buf = io.StringIO()
    child = pexpect.spawn(
        "bash",
        ["-lc", "wasanbon-webframework start --other_hosts"],
        encoding="utf-8",
        timeout=timeout,
    )
    child.delaybeforesend = 0
    # Capture output in buffer; enable verbose if needed
    child.logfile = buf

    prompt_continue = "Press Enter to continue. Press q to quit:"
    prompt_host = "host: "
    prompt_user = "user: "
    prompt_pass = "pswd: "

    try:
        # One host only
        child.expect_exact(prompt_continue)
        child.sendline("")

        child.expect_exact(prompt_host)
        child.sendline(host)

        child.expect_exact(prompt_user)
        child.sendline(user)

        child.expect_exact(prompt_pass)
        child.sendline(password)

        # Quit the loop after first host
        child.expect_exact(prompt_continue)
        child.sendline("q")

        child.expect(pexpect.EOF)
    
    except pexpect.TIMEOUT:
        # Continue to parse whatever output we captured
        pass
    finally:
        try:
            child.close()
        except Exception:
            pass

    # out = buf.getvalue()
    # rc = child.exitstatus if child.exitstatus is not None else 0
    # new_pids = _parse_start_output_for_new_pids(out)
    # return {"returncode": rc, "new_pids": new_pids, "stdout": out}

    # out = buf.getvalue()
    rc = child.exitstatus if child.exitstatus is not None else 0
    # new_pids = _parse_start_output_for_new_pids(out)
    return {"returncode": rc}


if __name__ == "__main__":
    # No CLI args; optional simple interactive use
    try:
        h = input("host: ")
        u = input("user: ")
        p = input("pswd: ")
        res = start_remote(h, u, p)
        print(json.dumps(res, ensure_ascii=False))
    except KeyboardInterrupt:
        print("\nCancelled")

