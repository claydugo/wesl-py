import package::examples::rmsnorm::input::load;
import package::examples::rmsnorm::normalization::scale_row;
import wgsl_test::expectNear;

const width: u32 = constants::width;
const epsilon: f32 = constants::epsilon;

fn scale(square_sum: f32) -> f32 {
    return scale_row(square_sum, width, epsilon);
}

@group(0) @binding(2) var<storage, read> combined: array<f32>;
var<workgroup> squares: array<f32, 64>;
var<workgroup> normalized_squares: array<f32, 64>;

@test @workgroup_size(64)
fn root_mean_square(@builtin(local_invocation_index) lane: u32) {
    let value = load(lane);
    expectNear(value, combined[lane]);
    squares[lane] = value * value;
    workgroupBarrier();
    var square_sum = 0.0;
    for (var index = 0u; index < width; index++) {
        square_sum += squares[index];
    }
    let normalized = value * scale(square_sum);
    expectNear(scale(4.0 * square_sum + 3.0 * f32(width) * epsilon), 0.5 * scale(square_sum));
    normalized_squares[lane] = normalized * normalized;
    workgroupBarrier();
    var mean_square = 0.0;
    for (var index = 0u; index < width; index++) {
        mean_square += normalized_squares[index] / f32(width);
    }
    let mean = square_sum / f32(width);
    expectNear(mean_square, mean / (mean + epsilon));
}
