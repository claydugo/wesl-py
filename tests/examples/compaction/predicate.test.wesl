import package::examples::compaction::predicate::selected_at;
import wgsl_test::{expect, expectEq};

const threshold: u32 = constants::threshold;

fn selected(value: u32) -> bool {
    return selected_at(value, threshold);
}

var<workgroup> changes: array<u32, 64>;

@test @workgroup_size(64)
fn single_partition_boundary(@builtin(local_invocation_index) lane: u32) {
    let start = threshold - 32u;
    changes[lane] = select(0u, 1u, selected(start + lane) != selected(start + lane + 1u));
    workgroupBarrier();
    var transitions = 0u;
    var boundary = 0u;
    for (var index = 0u; index < 64u; index++) {
        transitions += changes[index];
        boundary += changes[index] * (start + index + 1u);
    }
    expectEq(transitions, 1u);
    expectEq(boundary, threshold);
    @if(keep_below) expect(selected(threshold - 1u) && !selected(threshold));
    @else expect(!selected(threshold - 1u) && selected(threshold));
}
