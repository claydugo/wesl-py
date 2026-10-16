public fn update(gradient: f32, learning_rate: f32, moment: ptr<function, vec4f>) -> f32 {
    return learning_rate * gradient;
}
