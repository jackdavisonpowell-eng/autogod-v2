# Task: dedupe a JSONL file

Write `run.sh` that reads `data.jsonl` in this directory (one JSON object
per line) and writes `deduped.jsonl`. Two lines are duplicates if they
parse to equal JSON objects (same keys/values, regardless of key order).
Keep only the first occurrence of each, preserving original order. Run the
conversion once when `run.sh` runs.
