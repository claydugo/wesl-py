import package::sdf::scene::distance_to_scene;

fn normal(position: vec3<f32>) -> vec3<f32> {
    return normalize(vec3<f32>(
        distance_to_scene(position + vec3<f32>(0.001, 0.0, 0.0)) -
            distance_to_scene(position - vec3<f32>(0.001, 0.0, 0.0)),
        distance_to_scene(position + vec3<f32>(0.0, 0.001, 0.0)) -
            distance_to_scene(position - vec3<f32>(0.0, 0.001, 0.0)),
        distance_to_scene(position + vec3<f32>(0.0, 0.0, 0.001)) -
            distance_to_scene(position - vec3<f32>(0.0, 0.0, 0.001)),
    ));
}
