# Reading a profile

Reading a profile: the tools, and what to look for in their output. Read this
alongside reading-a-profile.md if you have not read a profile before.

Two numbers appear in every profiler under different names:

- **Inclusive / cumulative / total**: time in this function *and everything it
  called*. Use it to find which subsystem is responsible.
- **Exclusive / self / flat**: time in this function's own code. Use it to find
  the hot function to actually change.

A function with high inclusive and near-zero exclusive time is a router — the
cost is below it. Follow the chain down until exclusive time appears; that is
where the work happens.

**Flame graphs** show the call stack as stacked bars, width proportional to
time. Read them for *width*, never for height: a wide bar is expensive, a tall
stack is merely deep. Look for wide plateaus — those are where the time is.

Before trusting any profile, check that the workload is representative. A
profile of a 100-row run tells you about startup costs, not about the quadratic
loop that appears at 100,000 rows.
