ARCH ?= x86-64-sse41-popcnt
JOBS ?= 2
ENGINE_ARGS = ARCH=$(ARCH) profile-build=no

.PHONY: build legacy clean unit smoke determinism test sanitize valgrind

build:
	$(MAKE) -C src -j$(JOBS) $(ENGINE_ARGS) optimize=yes debug=no build

legacy: clean
	$(MAKE) -C src -j$(JOBS) $(ENGINE_ARGS) optimize=yes debug=no \
		EXTRACXXFLAGS=-DJIEQI_LEGACY_CHANCE_AGGREGATION build

clean:
	$(MAKE) -C src clean
	rm -rf .test-bin bin

unit:
	mkdir -p .test-bin
	$(CXX) -std=c++17 -O2 -Isrc tests/scorecalc_test.cpp -o .test-bin/scorecalc-sigmoid
	.test-bin/scorecalc-sigmoid
	$(CXX) -std=c++17 -O2 -DJIEQI_LEGACY_CHANCE_AGGREGATION -Isrc \
		tests/scorecalc_test.cpp -o .test-bin/scorecalc-legacy
	.test-bin/scorecalc-legacy

smoke: build
	python3 tests/uci_smoke.py src/jieqi-core

determinism: build
	python3 tests/determinism.py src/jieqi-core 4

test: unit smoke determinism

sanitize:
	$(MAKE) clean
	$(MAKE) unit
	$(MAKE) -C src -j$(JOBS) $(ENGINE_ARGS) optimize=yes debug=yes \
		sanitize='address undefined' build
	ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 \
	UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
		python3 tests/uci_smoke.py src/jieqi-core

valgrind:
	command -v valgrind >/dev/null
	$(MAKE) clean
	$(MAKE) unit
	$(MAKE) -C src -j$(JOBS) $(ENGINE_ARGS) optimize=no debug=yes build
	printf 'bench 16 1 3 current depth\nquit\n' | \
		valgrind --tool=memcheck --track-origins=yes --error-exitcode=99 \
		--leak-check=full src/jieqi-core >/dev/null
