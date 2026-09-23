#!/usr/bin/env python3
"""Compare semantic bench output across independent ASLR-enabled processes."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ENGINE = Path(sys.argv[1] if len(sys.argv) > 1 else "src/jieqi-core").resolve()
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 4


def signature() -> tuple[tuple[str, ...], tuple[str, ...], int]:
    result = subprocess.run(
        [str(ENGINE)],
        input="bench\nquit\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=90,
    )
    depth13: list[str] = []
    bestmoves: list[str] = []
    total_nodes = -1
    for line in result.stdout.splitlines():
        if line.startswith("info depth 13 "):
            score = re.search(r" score (?:cp|mate) -?\d+", line)
            nodes = re.search(r" nodes \d+", line)
            pv = line.split(" pv ", 1)[1] if " pv " in line else ""
            assert score and nodes
            depth13.append(f"{score.group(0)}{nodes.group(0)} pv {pv}")
        elif line.startswith("bestmove "):
            bestmoves.append(line)
    for line in result.stderr.splitlines():
        match = re.search(r"Nodes searched\s*:\s*(\d+)", line)
        if match:
            total_nodes = int(match.group(1))
    assert depth13 and bestmoves and total_nodes >= 0, (result.stdout[-2000:], result.stderr[-2000:])
    return tuple(depth13), tuple(bestmoves), total_nodes


reference = signature()
for run in range(2, RUNS + 1):
    current = signature()
    if current != reference:
        raise AssertionError(f"nondeterministic run {run}\nreference={reference}\ncurrent={current}")

print(f"determinism passed: {RUNS}/{RUNS} runs, nodes={reference[2]}")
