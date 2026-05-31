#!/usr/bin/env python3
import re
import sys
import time
from typing import List, Dict, Any

import pexpect

# Prompts used by wasanbon-webframework
PROMPT_LOCAL_PID = r'Enter the Process ID which you want to terminate\. Press ctrl\+c to quit\.\.\.'
PROMPT_SSH_CONTINUE = r'Press Enter to continue\. Press q to quit:'
PROMPT_HOST = r'host:\s*'
PROMPT_USER = r'user:\s*'
PROMPT_PSWD = r'pswd:\s*'


def parse_pids_from_list(text: str) -> List[str]:
    pids: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("PID") or s.startswith("[Proccess List]") or s.startswith("------"):
            continue
        m = re.match(r'^(\d+)\s', s)
        if m:
            pids.append(m.group(1))
    return pids


def stop_remote_all(host: str, user: str, password: str, *, timeout: int = 3, verbose: bool = False) -> Dict[str, Any]:
    """Stop remote uvicorn processes via builtin `--other_hosts` flow.

    - Skips local stop with Ctrl+C if prompted first
    - Enters host/user/password when prompted
    - Repeats remote PID prompt: parses list and kills all until none remain

    Returns a dict: { 'attempted_pids': [...], 'ok': bool, 'message': str }
    """
    cmd = r'''bash -lc "wasanbon-webframework stop --other_hosts"'''
    child = pexpect.spawn(cmd, encoding="utf-8", timeout=timeout)
    child.delaybeforesend = 0
    attempted: List[str] = []

    if verbose:
        child.logfile = sys.stdout

    # Step 1: handle initial local PID prompt (Ctrl+C to skip local)
    try:
        idx = child.expect([PROMPT_LOCAL_PID, PROMPT_SSH_CONTINUE, pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        if idx == 0:
            child.sendcontrol('c')
            # After Ctrl+C, tool prints "Done." then proceeds to SSH prompt
            child.expect([PROMPT_SSH_CONTINUE, pexpect.TIMEOUT, pexpect.EOF], timeout=timeout)
        elif idx == 1:
            pass  # already at SSH continue prompt
        elif idx == 2:
            return {"attempted_pids": attempted, "ok": False, "message": "Unexpected EOF before SSH prompt"}
        else:
            return {"attempted_pids": attempted, "ok": False, "message": "Timeout waiting for SSH prompt"}
    except Exception as e:
        return {"attempted_pids": attempted, "ok": False, "message": f"Error before SSH prompt: {e}"}

    # Step 2: fill SSH connection info
    child.sendline("")  # Press Enter to continue
    child.expect(PROMPT_HOST, timeout=timeout)
    child.sendline(host)
    child.expect(PROMPT_USER, timeout=timeout)
    child.sendline(user)
    child.expect(PROMPT_PSWD, timeout=timeout)
    child.sendline(password)

    # Step 3: remote list -> kill-all loop
    ok = False
    while True:
        idx = child.expect([PROMPT_LOCAL_PID, pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        if idx == 1:
            return {"attempted_pids": attempted, "ok": ok, "message": "Remote session ended (EOF)"}
        elif idx == 2:
            buffer = child.before or ""
            if "[SUCCESS]" in buffer or "Done." in buffer or attempted:
                # Treat as success when remote output confirms kill or we've already attempted
                ok = True
                child.sendcontrol('c')
                try:
                    child.expect(r'Done\.', timeout=5)
                except Exception:
                    pass
                break
            return {"attempted_pids": attempted, "ok": ok, "message": "Timeout waiting for remote PID prompt"}

        # Parse pids from the buffer printed before the prompt
        buf = child.before or ""
        pids = parse_pids_from_list(buf)
        if not pids:
            # Nothing remains; send Ctrl+C to follow CLI behavior
            child.sendcontrol('c')
            try:
                child.expect(r'Done\.', timeout=5)
            except Exception:
                pass
            ok = True
            break

        for pid in pids:
            child.sendline(pid)
            attempted.append(pid)
            # Wait briefly for re-prompt; small timeout for speed
            child.expect([PROMPT_LOCAL_PID, pexpect.TIMEOUT], timeout=3)

    # After loop, handle the final "Press Enter to continue. Press q to quit:" prompt if present
    try:
        idx2 = child.expect([PROMPT_SSH_CONTINUE, pexpect.EOF, pexpect.TIMEOUT], timeout=5)
        if idx2 == 0:
            child.sendline("q")
            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
    except Exception:
        pass

    # Best-effort close
    try:
        child.close(force=True)
    except Exception:
        pass

    return {"attempted_pids": attempted, "ok": ok, "message": "Finished"}


if __name__ == "__main__":
    # No CLI arguments; optional interactive usage for convenience
    try:
        host = input("host: ")
        user = input("user: ")
        password = input("pswd: ")
        result = stop_remote_all(host, user, password)
        print(result)
    except KeyboardInterrupt:
        print("\nCancelled.")
