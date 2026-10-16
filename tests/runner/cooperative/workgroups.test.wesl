import wgsl_test::{expect, expectEq};

alias Count = u32;
const initial = 1u;
override lanes = initial;
@id(5) override limit: Count;
override enabled: bool = false;
override offset: u32 = 0u;
const width = 2u;
var<workgroup> values: array<u32, 32>;
var<workgroup> arrivals: atomic<u32>;

@test @workgroup_size(2, 3, 4)
fn invocation_builtins(
    @builtin(local_invocation_id) position: vec3u,
    @builtin(local_invocation_index) invocation: u32,
    @builtin(global_invocation_id) global_position: vec3u,
    @builtin(workgroup_id) workgroup: vec3u,
    @builtin(num_workgroups) workgroups: vec3u,
) {
    expect(all(position == global_position));
    expect(all(workgroup == vec3u(0u)));
    expect(all(workgroups == vec3u(1u)));
    expectEq(position.x + 2u * position.y + 6u * position.z, invocation);
    if invocation == 0u {
        atomicStore(&arrivals, 0u);
    }
    workgroupBarrier();
    atomicAdd(&arrivals, 1u);
    workgroupBarrier();
    expectEq(atomicLoad(&arrivals), 24u);
}

@test @workgroup_size(super::layout::columns * width)
fn shadowed_names(
    @builtin(local_invocation_index) shadowed_names: super::layout::Index,
    @builtin(local_invocation_id) width: vec3u,
) {
    expectEq(shadowed_names, width.x);
    expect(width.x < 4u);
    if shadowed_names == 0u {
        atomicStore(&arrivals, 0u);
    }
    workgroupBarrier();
    atomicAdd(&arrivals, 1u);
    workgroupBarrier();
    expectEq(atomicLoad(&arrivals), 4u);
}

@if(qualified)
@test @workgroup_size(package::tests::runner::cooperative::layout::columns)
fn qualified_workgroup_size(
    @builtin(local_invocation_index) invocation: package::tests::runner::cooperative::layout::Index,
) {
    if invocation == 0u {
        atomicStore(&arrivals, 0u);
    }
    workgroupBarrier();
    atomicAdd(&arrivals, 1u);
    workgroupBarrier();
    expectEq(atomicLoad(&arrivals), 2u);
}

@test @workgroup_size(lanes)
fn pipeline_overrides(@builtin(local_invocation_index) lane: u32) {
    expectEq(lanes, 32u);
    expectEq(limit, 4294967295u);
    expect(enabled);
    expectEq(offset, 7u);
    expectEq(super::library::read(), 19u);
    values[lane] = lane + offset;
    workgroupBarrier();
    expectEq(values[(lane + 1u) % lanes], (lane + 1u) % lanes + 7u);
}
