import package::examples::optimizers::backward::backward;
import constants::parameter_count;
import package::examples::optimizers::network::loss;

@group(0) @binding(1) var<storage, read> samples: array<vec4f>;
@group(0) @binding(3) var<storage, read_write> scores: array<vec2f>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) index: vec3u) {
    if (index.x >= arrayLength(&samples)) {
        return;
    }
    let sample = samples[index.x];
    let logit = backward(sample, index.x * parameter_count);
    scores[index.x] = vec2f(
        loss(logit, sample.z),
        select(0.0, 1.0, (logit > 0.0) == (sample.z > 0.5)),
    );
}
