import package::compaction::predicate::selected;

@group(0) @binding(0) var<storage, read> values: array<u32>;
@group(0) @binding(1) var<storage, read_write> prefixes: array<u32>;
@group(0) @binding(2) var<storage, read_write> totals: array<u32>;
var<workgroup> partial: array<u32, 128>;

@compute @workgroup_size(128)
fn main(
    @builtin(global_invocation_id) index: vec3u,
    @builtin(local_invocation_index) lane: u32,
    @builtin(workgroup_id) group: vec3u,
) {
    var value = 0u;
    if (index.x < arrayLength(&values)) {
        @if(select_values) value = select(0u, 1u, selected(values[index.x]));
        @else value = values[index.x];
    }
    partial[lane] = value;
    workgroupBarrier();
    for (var stride = 1u; stride < 128u; stride *= 2u) {
        var preceding = 0u;
        if (lane >= stride) {
            preceding = partial[lane - stride];
        }
        workgroupBarrier();
        partial[lane] += preceding;
        workgroupBarrier();
    }
    if (index.x < arrayLength(&values)) {
        prefixes[index.x] = partial[lane] - value;
    }
    if (lane == 127u) {
        totals[group.x] = partial[lane];
    }
}
