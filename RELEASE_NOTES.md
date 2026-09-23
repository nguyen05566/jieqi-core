# JieqiCore 0.1.0 — local build report

## Artifact

- Path: `bin/jieqi-core`
- Target: Linux x86-64, SSE4.1 + POPCNT
- Size: approximately 360 KiB, stripped
- SHA-256: `8b32f3d89368ee94b7a6348196714b4d78666dc9997b54ffddda42bb3e6ae625`
- UCI identity: `JieqiCore 0.1.0`
- Default aggregation: sigmoid win-probability expectation

## Verification completed

- Sigmoid `ScoreCalc` unit tests: PASS.
- Legacy `ScoreCalc` unit tests: PASS.
- UCI handshake and options: PASS.
- `position startpos moves a3a4R`: PASS.
- `go infinite` followed by `stop`: PASS.
- All-dark-evasion depth-cap regression: PASS.
- Default release determinism with ASLR enabled: 12/12 identical semantic bench outputs, signature `2491046` nodes.
- Legacy release build and smoke test: PASS; deterministic signature `2385856` nodes in the tested build.
- ASan + UBSan smoke/regression suite: PASS.
- Valgrind Memcheck depth 3: `ERROR SUMMARY: 0 errors`, no leaks; `115708` nodes.

Node signatures differ because sigmoid changes search values and tree shape. They are regression signatures, not evidence of playing strength.

## Not yet claimed

No Elo or win-rate improvement is claimed. Before making sigmoid the competition bot, run paired games against the legacy build with fixed nodes, one thread, equal Hash, paired hidden-deal seeds, and color swaps.
