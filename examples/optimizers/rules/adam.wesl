@id(0) override mean_decay: f32 = 0.9;
@id(1) override variance_decay: f32 = 0.999;

public fn update(gradient: f32, learning_rate: f32, moment: ptr<function, vec4f>) -> f32 {
    (*moment).x = mean_decay * (*moment).x + (1.0 - mean_decay) * gradient;
    (*moment).y = variance_decay * (*moment).y + (1.0 - variance_decay) * gradient * gradient;
    (*moment).z += 1.0;
    let mean = (*moment).x / (1.0 - pow(mean_decay, (*moment).z));
    let variance = (*moment).y / (1.0 - pow(variance_decay, (*moment).z));
    return learning_rate * mean / (sqrt(variance) + 1e-8);
}
