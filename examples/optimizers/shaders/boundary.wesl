import package::examples::optimizers::network::probability;
import package::examples::optimizers::plane::extent;

struct VertexOutput {
    @builtin(position) position: vec4f,
    @location(0) coordinate: vec2f,
}

@vertex
fn vertex_main(@builtin(vertex_index) index: u32) -> VertexOutput {
    let corner = vec2f(f32((index << 1u) & 2u), f32(index & 2u)) * 2.0 - 1.0;
    var output: VertexOutput;
    output.position = vec4f(corner, 0.0, 1.0);
    output.coordinate = corner * extent;
    return output;
}

@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let value = probability(input.coordinate);
    let confidence = abs(value * 2.0 - 1.0);
    let color = mix(vec3f(0.12, 0.35, 0.9), vec3f(0.95, 0.4, 0.08), value) * (0.04 + 0.1 * confidence);
    let edge = 1.0 - smoothstep(0.5, 1.5, abs(value - 0.5) / max(fwidth(value), 1e-6));
    return vec4f(mix(color, vec3f(0.8), edge), 1.0);
}
