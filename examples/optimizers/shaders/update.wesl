import package::examples::optimizers::layout::parameter_count;
import package::examples::optimizers::rule::update;

@group(0) @binding(0) var<storage, read_write> parameters: array<f32>;
@group(0) @binding(1) var<storage, read> gradients: array<f32>;
@group(0) @binding(2) var<storage, read_write> moments: array<vec4f>;
@group(0) @binding(3) var<uniform> learning_rate: f32;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) index: vec3u) {
    if (index.x >= parameter_count) {
        return;
    }
    let sample_count = arrayLength(&gradients) / parameter_count;
    var gradient = 0.0;
    for (var sample = 0u; sample < sample_count; sample++) {
        gradient += gradients[sample * parameter_count + index.x];
    }
    var moment = moments[index.x];
    parameters[index.x] -= update(gradient / f32(sample_count), learning_rate, &moment);
    moments[index.x] = moment;
}
