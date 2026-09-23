# Provenance

JieqiCore is a GPL-3.0-or-later derivative of:

1. Stockfish/Glaurung lineage;
2. official Pikafish `jieqi_old`, upstream base `23b9466c`;
3. `brianhliou/pikafish-jieqi-wasm`, branch `jieqi_old-mistboard`, source revision `6398d4c`;
4. Mistboard's forced-loss aggregation and qsearch stop/time fixes.

The initial JieqiCore extraction intentionally keeps only the native C++ UCI engine and the files required to compile/test it. The Mistboard application, frontend, database, server integration, WebSocket code, capture artifacts, and WebAssembly build are not included.

JieqiCore 0.1.0 adds the following local engine changes:

- `psqDark` bounds fix;
- complete `ADVISOR_B` check-square state;
- resolved-dark `capturedPiece` propagation;
- static-evaluation fallback at the dark enumeration depth cap;
- repetition draw assignment fix;
- sigmoid chance aggregation with weighted role multiplicity and Mistboard's forced-loss guard;
- native-only entry point and JieqiCore UCI branding;
- focused unit, UCI, determinism, sanitizer, and Valgrind tests.

No upstream authorship is removed. See `AUTHORS` and each source file's copyright header.
