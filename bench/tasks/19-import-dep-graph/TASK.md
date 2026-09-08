# Task: import dependency graph

Write `run.sh` that scans every `.py` file in this directory for
`import X` / `from X import ...` lines. For each file, list which OTHER
`.py` files in this directory it depends on (a dependency exists when `X`
equals another file's basename without `.py`; ignore imports of anything
else, like `os`, `sys`, `json`). Print one line per file, sorted by
filename, format `filename.py: dep1.py,dep2.py` (deps comma-separated,
sorted, nothing after the colon if none).
