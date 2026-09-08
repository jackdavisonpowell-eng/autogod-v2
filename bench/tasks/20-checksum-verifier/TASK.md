# Task: checksum verifier

Write `run.sh` that reads `checksums.txt` in this directory (format:
`<sha256hex>  <filename>`, one per line) and, for each line, computes the
real SHA-256 of the named file and prints `filename: OK` if it matches the
recorded hash or `filename: MISMATCH` if it doesn't, one line per input
line, in file order, to stdout.
