#!/usr/bin/env python3


from __future__ import annotations
import re
import sys
import time
from typing import List

import pexpect


# Prompt shown by wasanbon-webframework when asking for local PID input
PROMPT_LOCAL_PID = r'Enter the Process ID which you want to terminate\. Press ctrl\+c to quit\.\.\.'
PROMPT_LOCAL_PID_EXACT = "Enter the Process ID which you want to terminate. Press ctrl+c to quit..."


def parse_pids_from_list(text: str) -> List[str]:
    """Extract PID strings from the printed process list text.

    Expected lines look like:
        PID       COMMAND
        16503     ['python3', '-m', 'uvicorn', ...]
    Returns list of PID strings.
    """
    pids: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("PID") or s.startswith("[Proccess List]") or s.startswith("------"):
            continue
        m = re.match(r"^(\d+)\s", s)
        if m:
            pids.append(m.group(1))
    return pids


def stop_all_local_with_pexpect(timeout: int = 30, verbose: bool = False) -> List[str]:
    """Run `wasanbon-webframework stop` and terminate all listed PIDs fast.

    Strategy for speed:
      - Wait once for the initial PID prompt (short timeout)
      - Parse all PIDs from that list
      - Send all PIDs in one burst, then Ctrl+C
      - Avoid waiting for repeated prompts/EOF

    Returns a list of PID strings that were attempted to be terminated.
    """
    cmd = r'''bash -lc "wasanbon-webframework stop"'''
    child = pexpect.spawn(cmd, encoding="utf-8", timeout=timeout)
    # Speed up interactions
    child.delaybeforesend = 0
    # Avoid post-close sleeps
    try:
        child.delayafterclose = 0  # type: ignore[attr-defined]
        child.delayafterterminate = 0  # type: ignore[attr-defined]
    except Exception:
        pass
    if verbose:
        child.logfile = sys.stdout

    attempted: List[str] = []

    try:
        # Wait for the initial prompt quickly
        try:
            child.expect_exact(PROMPT_LOCAL_PID_EXACT, timeout=min(timeout, 5))
        except pexpect.TIMEOUT:
            # Fallback to regex
            child.expect([PROMPT_LOCAL_PID, pexpect.EOF, pexpect.TIMEOUT], timeout=min(timeout, 5))

        # Parse PIDs from the buffer before the prompt
        buf = child.before or ""
        pids = parse_pids_from_list(buf)
        if not pids:
            # Nothing to do; exit cleanly
            child.sendcontrol('c')
            time.sleep(0.1)
            return attempted

        # Send all PIDs in a single burst
        payload = "\r".join(pids) + "\r"
        child.send(payload)
        attempted.extend(pids)

        # Give the tool a very short moment to process
        try:
            child.expect_exact(PROMPT_LOCAL_PID_EXACT, timeout=0.3)
        except (pexpect.TIMEOUT, pexpect.EOF):
            pass

        # Exit the loop quickly
        child.sendcontrol('c')
        time.sleep(0.1)

    finally:
        # Close without waiting on EOF to avoid extra delay
        try:
            child.close(force=True)
        except Exception:
            pass

    return attempted


def main() -> None:
    attempted = stop_all_local_with_pexpect(timeout=30, verbose=False)
    if attempted:
        print(f"Finished: attempted to terminate {len(attempted)} PID(s): {', '.join(attempted)}")
    else:
        print("No uvicorn PIDs found; nothing to terminate.")
    sys.exit(0)


if __name__ == "__main__":
    main()
