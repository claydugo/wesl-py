import constants::{
    first_biases,
    first_weights,
    output_bias,
    output_weights,
    second_biases,
    second_weights,
    width,
};
import package::examples::optimizers::parameters::parameter;

struct Activations {
    first_input: array<f32, width>,
    first: array<f32, width>,
    second_input: array<f32, width>,
    second: array<f32, width>,
    logit: f32,
}

public fn activate(value: f32) -> f32 {
    return tanh(value);
}

public fn slope(value: f32) -> f32 {
    let activated = tanh(value);
    return 1.0 - activated * activated;
}

public fn first_weight(row: u32, column: u32) -> u32 {
    return first_weights + row * 2u + column;
}

public fn first_bias(row: u32) -> u32 {
    return first_biases + row;
}

public fn second_weight(row: u32, column: u32) -> u32 {
    return second_weights + row * width + column;
}

public fn second_bias(row: u32) -> u32 {
    return second_biases + row;
}

public fn output_weight(column: u32) -> u32 {
    return output_weights + column;
}

public fn evaluate(position: vec2f) -> Activations {
    var activations: Activations;
    for (var row = 0u; row < width; row++) {
        activations.first_input[row] = parameter(first_weight(row, 0u)) * position.x +
            parameter(first_weight(row, 1u)) * position.y +
            parameter(first_bias(row));
        activations.first[row] = activate(activations.first_input[row]);
    }
    for (var row = 0u; row < width; row++) {
        var sum = parameter(second_bias(row));
        for (var column = 0u; column < width; column++) {
            sum += parameter(second_weight(row, column)) * activations.first[column];
        }
        activations.second_input[row] = sum;
        activations.second[row] = activate(sum);
    }
    activations.logit = parameter(output_bias);
    for (var column = 0u; column < width; column++) {
        activations.logit += parameter(output_weight(column)) * activations.second[column];
    }
    return activations;
}

public fn probability(position: vec2f) -> f32 {
    return 1.0 / (1.0 + exp(-evaluate(position).logit));
}

public fn loss(logit: f32, label: f32) -> f32 {
    return max(logit, 0.0) - logit * label + log(1.0 + exp(-abs(logit)));
}
