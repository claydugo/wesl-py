# Parallel primitives

[scan.wesl](scan.wesl) provides `scan_workgroup(value, lane)` for workgroups of
128 invocations. It returns the exclusive prefix of the value and the workgroup
total. Every invocation must call it at the same point in control flow.
The function ends with a barrier, so a caller can call it again in a loop.
It uses shared memory and logarithmic strides.
It prioritizes readable code over a tuned scan implementation.

The [compaction example](../compaction/README.md) scans its selection bits with it.
The [radix sort](../sorting/README.md) splits values by one key bit with it.
