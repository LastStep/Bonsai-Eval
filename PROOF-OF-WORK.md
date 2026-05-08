# Proof of Work — Bonsai Effectiveness

> **Status:** SKELETON. Numbers are `<PENDING>` until the analysis notebook is
> executed against real data, which cannot happen until Plan 38 is in
> `Plans/Archive/` (Risk #7 — pre-registration leak).

This document records the pre-registered claims for Bonsai's effectiveness,
the formulas used to compute them, and the headline numbers + caveats once
data is ingested. Any metric not specified below is exploratory appendix
material, not part of the pre-registration commitment.

**Cut-over commit:** `4dfd3f4` (2026-04-14) — `station/` adopted Bonsai.
Pre = baseline; post = treatment.

**Control project:** `~/.claude/projects/-home-rohan-ZenGarden-Bonsai/`
(Bonsai parent dir, no scaffold). Same user, same stack family.

---

## Methodology — Locked Metric Formulas

The following formulas are **frozen** as of plan-merge. Any data we collect
must report these exact metrics whether the result is flattering or not.

### C1 — Cache reuse

```
cache_hit_rate(p, d) = cache_read_tokens / (cache_read_tokens + input_tokens)
                       per project p per day d
memory_reads_per_session = count(tool=Read AND path matches
                            {CLAUDE.md, memory.md, identity.md, protocols/*})
                          / sessions
```

Report: pre/post-cutover delta for `station/`, and `station/` vs control.
14-day rolling median.

### C3 — Rework reduction

```
rework_ratio = (commits matching /^fix\(([^)]+)\):/
                where same scope had /^feat\(\1\)/ in prior 24h)
              / feat_commits
revert_ratio = reverts / total_commits
```

Report: pre/post-cutover, 14-day rolling, with bootstrap 95% CI.

### C6 — Throughput

```
plans_shipped_per_week = count(files moved Plans/Active/ → Plans/Archive/)
                         per 7d window
pr_merge_latency_p50 = median(merged_at - created_at)
                       per 7d window
```

Report: weekly timeseries with vertical rule at 2026-04-14.

---

## Headline numbers

> All values pending real-data run (Risk #7).

| Claim | Pre-cutover | Post-cutover | Delta | 95% CI | Charts |
|-------|------------:|-------------:|------:|:------:|:-------|
| **C1** cache_hit_rate (station) | `<PENDING>` | `<PENDING>` | `<PENDING>` | `<PENDING>` | [charts/c1-cache.png](charts/c1-cache.png) |
| **C1** memory_reads_per_session | `<PENDING>` | `<PENDING>` | `<PENDING>` | `<PENDING>` | [charts/c1-memory.png](charts/c1-memory.png) |
| **C3** rework_ratio | `<PENDING>` | `<PENDING>` | `<PENDING>` | `<PENDING>` | [charts/c3-rework.png](charts/c3-rework.png) |
| **C3** revert_ratio | `<PENDING>` | `<PENDING>` | `<PENDING>` | `<PENDING>` | [charts/c3-revert.png](charts/c3-revert.png) |
| **C6** plans_shipped_per_week | `<PENDING>` | `<PENDING>` | `<PENDING>` | `<PENDING>` | [charts/c6-plans.png](charts/c6-plans.png) |
| **C6** pr_merge_latency_p50 | `<PENDING>` | `<PENDING>` | `<PENDING>` | `<PENDING>` | [charts/c6-latency.png](charts/c6-latency.png) |

---

## Caveats — Mandatory Guardrails

Every chart MUST satisfy these guardrails (Plan 38 §"Pre-Registration"):

- **Model-mix chart adjacent.** Opus 4.6 → 4.7 transition happened
  post-cutover; reader must see we accounted for it.
- **Medians, not means.** Session cost distribution is heavy-tailed; means
  are misleading.
- **Control line on every headline chart.** Same-user no-scaffold project
  controls for non-Bonsai changes (model upgrades, user habit shifts).
- **Bootstrap 95% CIs on pre/post comparisons.** Single-point deltas
  without intervals overstate confidence.

Additional caveats (per `RESEARCH-proof-of-bonsai-effectiveness.md` §7):
- Sample size — pre-cutover window is short; CIs will be wide.
- Task-mix differences pre/post — Bonsai may have shifted what work the
  agent gets asked to do.
- Self-selection — the user adopting Bonsai is also the one measuring it.
- Reward-hacking risk — none of the metrics directly observe agent
  behaviour; they're proxies on git + transcripts.

---

## Methodology validation

> Filled in at the close of P2 (Bonsai-behavioral scenarios validation pass).

`<PENDING — P2>`

---

## Raw data + scripts

- **Telemetry pipeline:** [bonsai_eval/telemetry/](bonsai_eval/telemetry/)
- **Data schemas:** [data/SCHEMA.md](data/SCHEMA.md)
- **Analysis notebook:** [notebooks/proof_of_work.ipynb](notebooks/proof_of_work.ipynb)
- **Pre-registration plan:** Bonsai repo `station/Playbook/Plans/Active/38-bonsai-eval-bootstrap.md`
  (or `Archive/` once shipped)
