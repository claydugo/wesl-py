import package::sdf::parameters::parameters;
import package::sdf::particle::Particle;
import package::sdf::scene::distance_to_scene;
import package::sdf::surface::normal;

@group(0) @binding(1) var<storage, read_write> particles: array<Particle>;

fn random(seed: u32) -> f32 {
    var value = seed;
    value ^= value >> 16u;
    value *= 0x7feb352du;
    value ^= value >> 15u;
    value *= 0x846ca68bu;
    value ^= value >> 16u;
    return f32(value) / 4294967296.0;
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) invocation: vec3<u32>) {
    let index = invocation.x;
    if (index >= arrayLength(&particles)) { return; }
    var particle = particles[index];
    if (particle.position.w <= 0.0 || parameters.simulation.z > 0.0) {
        let seed = index * 17u + u32(parameters.viewport.z * 1000.0);
        particle.position = vec4<f32>(
            (random(seed) - 0.5) * 0.6,
            2.8 + random(seed + 1u) * 2.0,
            (random(seed + 2u) - 0.5) * 0.6,
            4.0 + random(seed + 3u) * 4.0,
        );
        particle.velocity = vec4<f32>(0.0, -0.3, 0.0, 0.035);
    }
    let delta = parameters.viewport.w / 4.0;
    for (var step = 0u; step < 4u; step += 1u) {
        particle.velocity.y -= parameters.simulation.y * delta;
        particle.position = vec4<f32>(
            particle.position.xyz + particle.velocity.xyz * delta,
            particle.position.w - delta,
        );
        let distance = distance_to_scene(particle.position.xyz) - particle.velocity.w;
        if (distance < 0.0) {
            let direction = normal(particle.position.xyz);
            particle.position = vec4<f32>(
                particle.position.xyz - direction * distance, particle.position.w,
            );
            let speed = dot(particle.velocity.xyz, direction);
            if (speed < 0.0) {
                particle.velocity = vec4<f32>(
                    particle.velocity.xyz -
                        (1.0 + parameters.simulation.x) * speed * direction,
                    particle.velocity.w,
                );
            }
        }
    }
    if (abs(particle.position.x) > 5.0 || abs(particle.position.z) > 5.0) {
        particle.position.w = 0.0;
    }
    particles[index] = particle;
}
