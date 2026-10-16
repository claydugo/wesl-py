import package::examples::imaging::reduction::sum_workgroup;
import wgsl_test::expectUlpVec4;

@test @workgroup_size(256)
fn workgroup_sum(@builtin(local_invocation_index) lane: u32) {
    let index = f32(lane);
    let moments = sum_workgroup(vec4f(1.0, index, index * index, -index), lane);
    expectUlpVec4(moments, vec4f(256.0, 32640.0, 5559680.0, -32640.0), 0u);
    let last = select(0.0, 1.0, lane == 255u);
    let reused = sum_workgroup(vec4f(last, 0.0, last * index, index), lane);
    expectUlpVec4(reused, vec4f(1.0, 0.0, 255.0, 32640.0), 0u);
}
