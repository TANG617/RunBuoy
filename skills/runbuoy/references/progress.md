# Progress selection

Choose in this order:

1. `structured` only when the program already reports through RunBuoy, or code changes were
   explicitly requested.
2. `regex` only for a stable record whose first two capture groups are numeric current/total.
3. `lines` only when a finite real total exists and one matching record equals one completed unit.
4. Otherwise use `indeterminate`; use phase/message for honest unknown-total work.

Examples:

```sh
runbuoy run --progress regex \
  --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' -- command

runbuoy run --progress lines --total 100 --match '^DONE$' -- command
```

Regex and match expressions are compiled, and regex capture groups are checked, before target
startup. Matching records can be remotely visible as sanitized messages; review the privacy
reference first.

For Python, report only finite, monotonic, real work units with `reporter.progress`. For unknown
or changing totals, use `reporter.phase` and `reporter.message`. A single coordinator must
aggregate concurrent tasks so updates do not race or regress.

Never infer current/total or ETA from elapsed time, log volume, CPU use, subjective phases, or a
running PID.
