import super::parameters::parameters;
import super::primitives::{sphere, smooth_union};

fn distance_to_scene(position: vec3<f32>) -> f32 {
    let separation = parameters.shape.z;
    let width = parameters.shape.x;
    let left = sphere(position - vec3<f32>(-separation, 0.45, 0.0), 0.85);
    let right = sphere(position - vec3<f32>(separation, 0.45, 0.0), 0.85);
    let crown = sphere(position - vec3<f32>(0.0, 1.25, 0.0), 0.85);
    let base = sphere(position - vec3<f32>(0.0, -0.1, 0.0), 0.7);
    var sculpture = smooth_union(smooth_union(left, right, width), crown, width);
    sculpture = smooth_union(sculpture, base, width);
    @if(cutout) {
        let tunnel = length(position.xz) - parameters.shape.y;
        sculpture = max(sculpture, -tunnel);
    }
    return min(sculpture, position.y + 1.25);
}
