import package::examples::compaction::predicate::selected;
import package::examples::parallel::scan::scan_workgroup;

@group(0) @binding(0) var<storage, read> values: array<u32>;
@group(0) @binding(1) var<storage, read_write> prefixes: array<u32>;
@group(0) @binding(2) var<storage, read_write> totals: array<u32>;

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
    let scan = scan_workgroup(value, lane);
    if (index.x < arrayLength(&values)) {
        prefixes[index.x] = scan.exclusive;
    }
    if (lane == 0u) {
        totals[group.x] = scan.total;
    }
}
