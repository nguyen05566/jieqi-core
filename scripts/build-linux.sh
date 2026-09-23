#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${1:-$ROOT/bin/jieqi-core}"
MODE="${JIEQI_CORE_AGGREGATION:-sigmoid}"
JOBS="${JOBS:-$(nproc)}"

case "$MODE" in
  sigmoid) EXTRA="" ;;
  legacy)  EXTRA="-DJIEQI_LEGACY_CHANCE_AGGREGATION" ;;
  *) echo "unsupported JIEQI_CORE_AGGREGATION=$MODE (use sigmoid or legacy)" >&2; exit 2 ;;
esac

make -C "$ROOT/src" clean >/dev/null
make -C "$ROOT/src" -j"$JOBS" \
  ARCH=x86-64-sse41-popcnt \
  profile-build=no optimize=yes debug=no \
  EXTRACXXFLAGS="$EXTRA" build

mkdir -p "$(dirname "$OUTPUT")"
cp "$ROOT/src/jieqi-core" "$OUTPUT"
chmod +x "$OUTPUT"
if command -v strip >/dev/null 2>&1; then
  strip "$OUTPUT"
fi

echo "Built JieqiCore ($MODE) -> $OUTPUT"
sha256sum "$OUTPUT"
