import package::rmsnorm::input::load;
import package::rmsnorm::normalization::{width, scale};

@group(0) @binding(2) var<storage, read> weights: array<f32>;
@group(0) @binding(3) var<storage, read_write> output: array<f32>;
var<workgroup> squares: array<f32, 64>;

@compute @workgroup_size(64)
fn main(
    @builtin(workgroup_id) group: vec3u,
    @builtin(local_invocation_index) lane: u32,
) {
    let start = group.x * width;
    var square_sum = 0.0;
    for (var column = lane; column < width; column += 64u) {
        let value = load(start + column);
        square_sum += value * value;
    }
    squares[lane] = square_sum;
    workgroupBarrier();
    for (var stride = 32u; stride > 0u; stride /= 2u) {
        if (lane < stride) {
            squares[lane] += squares[lane + stride];
        }
        workgroupBarrier();
    }
    let multiplier = scale(squares[0]);
    for (var column = lane; column < width; column += 64u) {
        output[start + column] = load(start + column) * multiplier * weights[column];
    }
}
