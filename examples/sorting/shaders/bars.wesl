import package::examples::sorting::key::key;
import package::examples::sorting::order::ordered;

struct Display {
    size: vec2f,
    dots: u32,
}

@group(0) @binding(0) var<storage, read> values: array<u32>;
@group(0) @binding(1) var<storage, read> marks: array<u32>;
@group(0) @binding(2) var<uniform> display: Display;

struct VertexOutput {
    @builtin(position) position: vec4f,
    @location(0) color: vec3f,
    @location(1) below_top: f32,
    @location(2) @interpolate(flat) marked: u32,
}

@vertex
fn vertex_main(@builtin(vertex_index) vertex: u32, @builtin(instance_index) instance: u32) -> VertexOutput {
    let corners = array<vec2f, 6>(
        vec2f(0.0, 0.0), vec2f(1.0, 0.0), vec2f(0.0, 1.0),
        vec2f(0.0, 1.0), vec2f(1.0, 0.0), vec2f(1.0, 1.0),
    );
    let count = arrayLength(&values);
    let value = values[instance];
    let corner = corners[vertex];
    let height = f32(key(value) + 1u) / 1024.0;
    var width = 1.0 / f32(count);
    var bottom = 0.0;
    if (display.dots != 0u) {
        width = max(width, 3.0 / display.size.x);
        bottom = height - 3.0 / display.size.y;
    }
    let center = (f32(instance) + 0.5) / f32(count);
    var output: VertexOutput;
    output.position = vec4f(
        (center + (corner.x - 0.5) * width) * 2.0 - 1.0,
        mix(bottom, height, corner.y) * 2.0 - 1.0,
        0.0,
        1.0,
    );
    let in_order = (instance == 0u || ordered(values[instance - 1u], value)) &&
        (instance + 1u == count || ordered(value, values[instance + 1u]));
    let color = pow(unpack4x8unorm(value).rgb, vec3f(2.2));
    output.color = select(color * 0.25, color, in_order);
    output.below_top = (1.0 - corner.y) * (height - bottom) * display.size.y;
    output.marked = marks[instance];
    return output;
}

@fragment
fn fragment_main(input: VertexOutput) -> @location(0) vec4f {
    if (input.marked != 0u && input.below_top < 6.0) {
        return vec4f(1.0);
    }
    return vec4f(input.color, 1.0);
}
