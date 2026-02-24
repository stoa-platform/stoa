7-day token cost analysis.

Data sources:
- `~/.claude/stats-cache.json` — current session stats
- `~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/metrics.log` — TOKEN-SPEND events

Steps:

1. Parse last 7 TOKEN-SPEND entries from metrics.log
2. Extract: date, tokens_total, cost_usd, model, sessions
3. Calculate: daily average, 7-day total, projected monthly cost
4. Compare against thresholds:
   - Green: < $30/day
   - Yellow: $30-50/day
   - Red: > $50/day

Output format:

```
Token Cost Report (last 7 days)
| Date | Tokens | Cost | Model | Sessions |
|------|--------|------|-------|----------|
...

Daily avg: $X.XX | 7-day total: $XX.XX | Projected monthly: $XXX
Budget status: Green/Yellow/Red
```

If metrics.log has fewer than 7 entries, report what's available.
