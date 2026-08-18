# Profiling databases

Profiling databases: the tools, and what to look for in their output. Read
this alongside reading-a-profile.md if you have not read a profile before.

The database is where most application latency actually is, and no CPU profiler
will show it to you.

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;   -- Postgres: real timings and I/O
```

Read the plan for:

- **Sequential scan on a large table** where you expected an index scan. Often a
  missing index, a type mismatch in the predicate, or a function applied to the
  column.
- **Rows estimated vs actual** far apart — stale statistics, and the planner is
  choosing badly as a result.
- **Nested loop over many rows** where a hash join would be right.
- **Sort or hash spilling to disk** — needs more `work_mem` or a smaller
  intermediate result.

Also: enable slow-query logging in production and read it weekly; count queries
per request (an N+1 is invisible in a plan because each individual query is
fast); and check index usage statistics to find indexes that cost writes and
serve no reads.
