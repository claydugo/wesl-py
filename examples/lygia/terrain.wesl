import lygia::generative::snoise::snoise3;

fn elevation(position: vec2f, time: f32, seed: i32, roughness: f32) -> f32 {
    var hash = vec2u(bitcast<u32>(seed), bitcast<u32>(seed) + 0x9e3779b9u);
    hash ^= hash >> vec2u(16u);
    hash *= 0x7feb352du;
    hash ^= hash >> vec2u(15u);
    hash *= 0x846ca68bu;
    hash ^= hash >> vec2u(16u);
    let offset = 80.0 * vec2f(hash >> vec2u(8u)) / 16777216.0;
    let warp = vec2f(
        snoise3(vec3f(position * 0.7 + offset, time * 0.15)),
        snoise3(vec3f(position * 0.7 + offset + vec2f(17.0, 29.0), time * 0.15)),
    );
    var sample = vec3f(position + offset + 0.35 * warp, time * 0.12);
    var amplitude = 1.0;
    var total = 0.0;
    var weight = 0.0;
    for (var octave = 0u; octave < 5u; octave++) {
        total += amplitude * snoise3(sample);
        weight += amplitude;
        sample = sample * 2.03 + vec3f(13.7, 9.2, 5.4);
        amplitude *= roughness;
    }
    return clamp(0.5 + 0.75 * total / weight, 0.0, 1.0);
}
