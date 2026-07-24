from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_SAFE = re.compile(r"^[A-Z0-9.-]+$")


def write_immutable_bar_chunk(
    root: str | Path,
    *,
    symbol: str,
    period: str,
    bars: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    """Write one deterministic gzip JSONL chunk; never overwrite different bytes."""
    symbol = symbol.upper()
    if not _SAFE.fullmatch(symbol) or not _SAFE.fullmatch(period.upper()):
        raise ValueError("unsafe raw-cache symbol or period")
    ordered = sorted(bars, key=lambda row: str(row["timestamp"]))
    header = {"artifact": "alpaca-minute-bars-v1", "source": source, "symbol": symbol, "period": period}
    lines = [json.dumps({"metadata": header}, sort_keys=True, separators=(",", ":"))]
    lines.extend(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) for row in ordered)
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    compressed = gzip.compress(raw, mtime=0)
    digest = hashlib.sha256(compressed).hexdigest()
    path = Path(root) / symbol / f"{period}.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing != digest:
            raise RuntimeError(f"immutable raw cache conflict: {path}")
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(compressed)
        temporary.replace(path)
    return {
        "path": str(path),
        "sha256": digest,
        "bar_count": len(ordered),
        "start": str(ordered[0]["timestamp"]) if ordered else None,
        "end": str(ordered[-1]["timestamp"]) if ordered else None,
        "symbol": symbol,
        "period": period,
        "source": source,
    }


def read_bar_chunk(path: str | Path, *, expected_sha256: str | None = None) -> list[dict[str, Any]]:
    if expected_sha256 and hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_sha256:
        raise RuntimeError(f"raw cache hash mismatch: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return [row for row in rows if "metadata" not in row]


def verify_raw_manifest(manifest: dict[str, Any], *, verify_files: bool = False) -> None:
    if not manifest.get("ok") or manifest.get("errors"):
        raise RuntimeError("incomplete raw manifest cannot be used as evidence")
    chunks = manifest.get("chunks") or []
    coverage = manifest.get("coverage") or {}
    paths = [str(chunk.get("path") or "") for chunk in chunks]
    if not chunks or any(not path for path in paths) or len(paths) != len(set(paths)):
        raise RuntimeError("raw manifest has missing or duplicate chunks")

    actual_counts: list[int] = []
    starts: list[str] = []
    ends: list[str] = []
    symbols: set[str] = set()
    for chunk in chunks:
        count = int(chunk.get("bar_count") or 0)
        start = chunk.get("start")
        end = chunk.get("end")
        symbol = str(chunk.get("symbol") or "").upper()
        if verify_files:
            rows = read_bar_chunk(chunk["path"], expected_sha256=str(chunk.get("sha256") or ""))
            count = len(rows)
            row_symbols = {str(row.get("symbol") or "").upper() for row in rows}
            if rows and row_symbols != {symbol}:
                raise RuntimeError(f"raw manifest symbol mismatch: {chunk['path']}")
            timestamps = [str(row["timestamp"]) for row in rows]
            start = min(timestamps) if timestamps else None
            end = max(timestamps) if timestamps else None
            if count != int(chunk.get("bar_count") or 0) or start != chunk.get("start") or end != chunk.get("end"):
                raise RuntimeError(f"raw manifest chunk coverage mismatch: {chunk['path']}")
        actual_counts.append(count)
        if count:
            symbols.add(symbol)
            if start:
                starts.append(str(start))
            if end:
                ends.append(str(end))

    expected = {
        "chunks": len(chunks),
        "bar_count": sum(actual_counts),
        "nonempty_chunks": sum(count > 0 for count in actual_counts),
        "start": min(starts) if starts else None,
        "end": max(ends) if ends else None,
        "symbols_with_data": sorted(symbols),
    }
    if any(coverage.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"raw manifest coverage mismatch: expected {expected}")
