# Changelog

## 0.1.0 — 2026-09-23

- Extract native Linux UCI engine from Mistboard PikaJieQi.
- Remove app, bot, frontend, WebSocket, capture, database, and WASM scope.
- Apply four verified correctness fixes for Zobrist, StateInfo, dark-advisor checks, and dark-depth cutoff.
- Fix repetition draw expression.
- Make sigmoid win-probability chance aggregation the default.
- Preserve weighted role counts, unanimous mate scores, and the forced-loss guard.
- Add an opt-in compile flag for legacy linear aggregation.
- Add Linux build script, GitHub CI, unit tests, UCI smoke tests, determinism tests, sanitizers, and Valgrind target.
