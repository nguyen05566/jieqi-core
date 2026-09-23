#!/usr/bin/env python3
"""Focused UCI and zai-bot protocol smoke test for JieqiCore."""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ENGINE = Path(sys.argv[1] if len(sys.argv) > 1 else "src/jieqi-core").resolve()
if not ENGINE.is_file():
    raise SystemExit(f"engine not found: {ENGINE}")

proc = subprocess.Popen(
    [str(ENGINE)],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
    env={**os.environ, "ASAN_OPTIONS": os.environ.get("ASAN_OPTIONS", "detect_leaks=1:abort_on_error=1")},
)
assert proc.stdin and proc.stdout and proc.stderr

stdout_q: queue.Queue[str] = queue.Queue()
stderr_lines: list[str] = []
all_stdout: list[str] = []


def consume_stdout() -> None:
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        all_stdout.append(line)
        stdout_q.put(line)


def consume_stderr() -> None:
    for raw in proc.stderr:
        stderr_lines.append(raw.rstrip("\n"))


threading.Thread(target=consume_stdout, daemon=True).start()
threading.Thread(target=consume_stderr, daemon=True).start()


def send(command: str) -> None:
    if proc.poll() is not None:
        raise AssertionError(f"engine exited {proc.returncode}; stderr={stderr_lines[-30:]}")
    proc.stdin.write(command + "\n")
    proc.stdin.flush()


def expect(pattern: str, timeout: float = 15.0) -> str:
    regex = re.compile(pattern)
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(
                f"engine exited {proc.returncode} waiting for {pattern!r}; "
                f"stdout={all_stdout[-30:]}; stderr={stderr_lines[-30:]}"
            )
        try:
            line = stdout_q.get(timeout=min(0.1, max(0.0, deadline - time.monotonic())))
        except queue.Empty:
            continue
        seen.append(line)
        if regex.search(line):
            return line
    raise AssertionError(
        f"timeout waiting for {pattern!r}; seen={seen[-30:]}; stderr={stderr_lines[-30:]}"
    )


try:
    expect(r"^JieqiCore 0\.1\.0 ")
    send("uci")
    expect(r"^id name JieqiCore 0\.1\.0$")
    expect(r"^uciok$")

    send("setoption name Threads value 1")
    send("setoption name Hash value 16")
    send("isready")
    expect(r"^readyok$")

    # Exact move-suffix protocol used by the zai bot: a dark red piece reveals as R.
    send("ucinewgame")
    send("position startpos moves a3a4R")
    send("go nodes 3000")
    expect(r"^bestmove [a-i][0-9][a-i][0-9](?: ponder [a-i][0-9][a-i][0-9])?$")

    # Regression for the all-dark-evasion false-mate/assertion path.
    send("position startpos")
    send("bench 16 1 2 current depth")
    expect(r"^bestmove [a-i][0-9][a-i][0-9]", timeout=30.0)

    # The GitHub bot uses go infinite + stop rather than go movetime.
    send("position startpos")
    send("go infinite")
    time.sleep(0.20)
    send("stop")
    expect(r"^bestmove [a-i][0-9][a-i][0-9]", timeout=10.0)

    send("quit")
    proc.wait(timeout=10)
    if proc.returncode != 0:
        raise AssertionError(f"engine exit={proc.returncode}; stderr={stderr_lines[-30:]}")
finally:
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)

print("uci smoke tests passed")
