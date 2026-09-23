var<workgroup> sums: array<vec4<f32>, 256>;

fn sum_workgroup(value: vec4<f32>, local_index: u32) -> vec4<f32> {
    sums[local_index] = value;
    workgroupBarrier();
    for (var stride = 128u; stride > 0u; stride /= 2u) {
        if (local_index < stride) { sums[local_index] += sums[local_index + stride]; }
        workgroupBarrier();
    }
    let total = sums[0];
    workgroupBarrier();
    return total;
}
