struct Parameters {
    viewport: vec4<f32>,
    shape: vec4<f32>,
    camera_position: vec4<f32>,
    camera_right: vec4<f32>,
    camera_up: vec4<f32>,
    camera_forward: vec4<f32>,
    simulation: vec4<f32>,
}

@group(0) @binding(0) var<uniform> parameters: Parameters;
