import constants::{output_bias, width};
import package::examples::optimizers::network::{
    evaluate,
    first_bias,
    first_weight,
    output_weight,
    second_bias,
    second_weight,
    slope,
};
import package::examples::optimizers::parameters::parameter;

@group(0) @binding(2) var<storage, read_write> gradients: array<f32>;

public fn backward(sample: vec4f, offset: u32) -> f32 {
    let activations = evaluate(sample.xy);
    let output_error = 1.0 / (1.0 + exp(-activations.logit)) - sample.z;
    gradients[offset + output_bias] = output_error;
    var second_errors: array<f32, width>;
    for (var row = 0u; row < width; row++) {
        gradients[offset + output_weight(row)] = output_error * activations.second[row];
        second_errors[row] = output_error * parameter(output_weight(row)) *
            slope(activations.second_input[row]);
        gradients[offset + second_bias(row)] = second_errors[row];
        for (var column = 0u; column < width; column++) {
            gradients[offset + second_weight(row, column)] =
                second_errors[row] * activations.first[column];
        }
    }
    for (var column = 0u; column < width; column++) {
        var sum = 0.0;
        for (var row = 0u; row < width; row++) {
            sum += parameter(second_weight(row, column)) * second_errors[row];
        }
        let first_error = sum * slope(activations.first_input[column]);
        gradients[offset + first_bias(column)] = first_error;
        gradients[offset + first_weight(column, 0u)] = first_error * sample.x;
        gradients[offset + first_weight(column, 1u)] = first_error * sample.y;
    }
    return activations.logit;
}
