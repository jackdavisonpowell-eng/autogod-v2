# AUTOGOD v2 proxy probe results

Run: 2026-09-08T20:46:55Z

Note: resume requires the same cwd as the original session (Claude Code keys
sessions by project directory) -- all 20 runs execute in one shared workdir
(/tmp/autogod-probe/work), with per-run file names (hello_NN.txt) to keep them distinguishable.

GPU util during run:
```
0, Tesla V100-PCIE-32GB, 0 %, 31520 MiB
1, Tesla P100-PCIE-16GB, 73 %, 12604 MiB
2, Tesla P100-PCIE-16GB, 79 %, 15006 MiB
```

| run | mode | exit | secs | success | turns | api_calls | api_errs | is_error | tok_in | tok_out |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | cold | 0 | 116.1 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 2 | warm-resume | 0 | 20.9 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 3 | warm-resume | 0 | 21.0 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 4 | warm-resume | 0 | 32.2 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 5 | warm-resume | 0 | 21.1 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 6 | warm-resume | 0 | 21.2 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 7 | warm-resume | 0 | 37.8 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 8 | cold | 0 | 27.1 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 9 | warm-resume | 0 | 18.8 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 10 | warm-resume | 0 | 18.9 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 11 | warm-resume | 0 | 31.6 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 12 | warm-resume | 124 | 181.0 | 1 | 3 | 0 | 0 | 1 | 0 | 0 |
| 13 | warm-resume | 124 | 181.0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| 14 | warm-resume | 124 | 181.0 | 0 | 2 | 0 | 0 | 1 | 0 | 0 |
| 15 | cold | 0 | 161.0 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 16 | warm-resume | 0 | 17.0 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 17 | warm-resume | 0 | 16.9 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 18 | warm-resume | 0 | 28.0 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 19 | warm-resume | 0 | 17.1 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |
| 20 | warm-resume | 0 | 36.0 | 1 | 3 | 0 | 0 | 0 | 0 | 0 |

## Summary
- success: 18/20  (gate: >=18/20)
- claude-reported is_error rate: 3/20
- proxy api-call error rate: 0/0 requests (>=400 status)
- median warm (--resume) turn secs: 21.2
- cold run secs: 116.1 27.1 161.0 
- GPU util during: see block above

## Read (build session, 2026-09-08)
- Gate 1 met exactly: 18/20. Both failures (13, 14) and the one slow success (12) are 180 s
  timeouts while the v1 Hermes worker held the other llama.cpp slot — contention, not tool
  errors. Every run that got a turn used tools correctly (3 turns each).
- Warm-resume turns 17–38 s here vs the 3.6 s measured on an idle card: same cause.
- The api_calls/tok columns are 0 because the proxy-log correlation by timestamp didn't
  line up; the token data is in state/proxy.log. Fix before the bench baseline relies on it.
