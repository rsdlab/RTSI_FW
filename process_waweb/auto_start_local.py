#!/usr/bin/env python3


from __future__ import annotations

import json
import re
import subprocess
from typing import List, Dict, Any


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


def start_local() -> Dict[str, Any]:
    """Run local start and return a summary dict.

    Returns: { 'returncode': int, 'new_pids': List[int], 'stdout': str }
    """
    proc = subprocess.run(
        ["bash", "-lc", "wasanbon-webframework start"],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout or ""
    new_pids = _parse_start_output_for_new_pids(out)
    return {"returncode": proc.returncode, "new_pids": new_pids, "stdout": out}


if __name__ == "__main__":
    res = start_local()
    print(json.dumps(res, ensure_ascii=False))

