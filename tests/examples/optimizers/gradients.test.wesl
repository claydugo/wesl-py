import package::examples::optimizers::backward::{backward, gradients};
import constants::parameter_count;
import package::examples::optimizers::network::{evaluate, loss};
import package::examples::optimizers::parameters::{perturbation, perturbed_index};
import wgsl_test::expectWithin;

@test @workgroup_size(64)
fn finite_differences(@builtin(local_invocation_index) lane: u32) {
    let samples = array<vec4f, 4>(
        vec4f(0.3, -0.2, 1.0, 0.0),
        vec4f(-0.7, 0.4, 0.0, 0.0),
        vec4f(0.05, 0.9, 1.0, 0.0),
        vec4f(-0.5, -0.8, 0.0, 0.0),
    );
    perturbation = 0.0;
    for (var index = 0u; index < 4u; index++) {
        let sample = samples[index];
        if (lane == 0u) {
            _ = backward(sample, 0u);
        }
        storageBarrier();
        for (var parameter = lane; parameter < parameter_count; parameter += 64u) {
            perturbed_index = parameter;
            perturbation = 0.01;
            let above = loss(evaluate(sample.xy).logit, sample.z);
            perturbation = -0.01;
            let below = loss(evaluate(sample.xy).logit, sample.z);
            perturbation = 0.0;
            expectWithin(gradients[parameter], (above - below) / 0.02, 0.01, 0.0001);
        }
        storageBarrier();
    }
}
