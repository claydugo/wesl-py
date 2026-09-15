import package::sdf::parameters::parameters;

fn project(position: vec3<f32>) -> vec4<f32> {
    let relative = position - parameters.camera_position.xyz;
    let depth = dot(relative, parameters.camera_forward.xyz);
    let aspect = parameters.viewport.x / parameters.viewport.y;
    return vec4<f32>(
        dot(relative, parameters.camera_right.xyz) / (0.57735027 * aspect),
        dot(relative, parameters.camera_up.xyz) / 0.57735027,
        (100.0 * depth - 10.0) / 99.9,
        depth,
    );
}
