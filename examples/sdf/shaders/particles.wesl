import package::examples::sdf::camera::project;
import package::examples::sdf::parameters::parameters;
import package::examples::sdf::particle::Particle;

@group(0) @binding(1) var<storage, read> particles: array<Particle>;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) corner: vec2<f32>,
    @location(1) center: vec3<f32>,
    @location(2) radius: f32,
}

struct FragmentOutput {
    @location(0) color: vec4<f32>,
    @builtin(frag_depth) depth: f32,
}

@vertex
fn vertex_main(@builtin(vertex_index) index: u32, @builtin(instance_index) instance: u32) -> VertexOutput {
    let corners = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0), vec2<f32>(1.0, -1.0), vec2<f32>(-1.0, 1.0),
        vec2<f32>(-1.0, 1.0), vec2<f32>(1.0, -1.0), vec2<f32>(1.0, 1.0),
    );
    let particle = particles[instance];
    let corner = corners[index];
    var output: VertexOutput;
    output.position = project(particle.position.xyz + particle.velocity.w * (
        parameters.camera_right.xyz * corner.x + parameters.camera_up.xyz * corner.y
    ));
    output.corner = corner;
    output.center = particle.position.xyz;
    output.radius = particle.velocity.w;
    return output;
}

@fragment
fn fragment_main(input: VertexOutput) -> FragmentOutput {
    let radius_squared = dot(input.corner, input.corner);
    if (radius_squared > 1.0) { discard; }
    let surface_normal = parameters.camera_right.xyz * input.corner.x +
        parameters.camera_up.xyz * input.corner.y -
        parameters.camera_forward.xyz * sqrt(1.0 - radius_squared);
    let position = input.center + surface_normal * input.radius;
    let light = normalize(vec3<f32>(-3.0, 6.0, 4.0) - position);
    let diffuse = 0.35 + 0.65 * max(dot(surface_normal, light), 0.0);
    let projected = project(position);
    var output: FragmentOutput;
    output.color = vec4<f32>(vec3<f32>(1.0, 0.6, 0.12) * diffuse, 1.0);
    output.depth = projected.z / projected.w;
    return output;
}
