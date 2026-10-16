import package::examples::optimizers::network::probability;
import package::examples::optimizers::plane::extent;

@group(0) @binding(1) var<storage, read> samples: array<vec4f>;

struct VertexOutput {
    @builtin(position) position: vec4f,
    @location(0) corner: vec2f,
    @location(1) @interpolate(flat) color: vec3f,
    @location(2) @interpolate(flat) outline: vec3f,
}

@vertex
fn vertex_main(@builtin(vertex_index) vertex: u32, @builtin(instance_index) instance: u32) -> VertexOutput {
    let corners = array<vec2f, 6>(
        vec2f(-1.0, -1.0), vec2f(1.0, -1.0), vec2f(-1.0, 1.0),
        vec2f(-1.0, 1.0), vec2f(1.0, -1.0), vec2f(1.0, 1.0),
    );
    let sample = samples[instance];
    let corner = corners[vertex];
    let positive = sample.z > 0.5;
    var output: VertexOutput;
    output.position = vec4f(sample.xy / extent + corner * 0.016, 0.0, 1.0);
    output.corner = corner;
    output.color = select(vec3f(0.12, 0.35, 0.9), vec3f(0.95, 0.4, 0.08), positive);
    output.outline = select(vec3f(1.0), vec3f(0.0), (probability(sample.xy) > 0.5) == positive);
    return output;
}

@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    let radius = length(input.corner);
    if (radius > 1.0) {
        discard;
    }
    return vec4f(select(input.color, input.outline, radius > 0.65), 1.0);
}
