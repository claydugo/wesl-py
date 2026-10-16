@id(0) override decay: f32 = 0.9;

public fn update(gradient: f32, learning_rate: f32, moment: ptr<function, vec4f>) -> f32 {
    (*moment).x = decay * (*moment).x + gradient;
    return learning_rate * (*moment).x;
}
