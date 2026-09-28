import super::activation::activate;
import super::convolution_input::{load, load_pixel, input_height, input_width, input_channels,
    output_channels, kernel_size, stride, padding, activation};
enable f16;

@group(0) @binding(0) var<storage, read_write> output: array<f16>;
@group(0) @binding(5) var<storage, read> weights: array<f16>;
@group(0) @binding(6) var<storage, read> biases: array<f16>;

const reduction_tile = 16u;
@id(11) override wide_products: bool = false;
var<workgroup> input_tile: array<vec4<f16>, reduction_tile * 8u>;
var<workgroup> weight_tile: array<f16, reduction_tile * 16u>;

@compute @workgroup_size(8, 8)
fn tiled(@builtin(workgroup_id) group: vec3u, @builtin(local_invocation_id) local: vec3u) {
    let output_width = (input_width + 2u * padding - kernel_size) / stride + 1u;
    let output_height = (input_height + 2u * padding - kernel_size) / stride + 1u;
    let output_pixels = output_height * output_width;
    let reduction_count = input_channels * kernel_size * kernel_size;
    let lane = local.y * 8u + local.x;
    let position = group.x * 32u + local.x * 4u;
    let channel = group.y * 16u + local.y * 2u;
    var first_sum = vec4f(0.0);
    var second_sum = vec4f(0.0);
    for (var reduction_start = 0u; reduction_start < reduction_count; reduction_start += reduction_tile) {
        for (var index = lane; index < reduction_tile * 8u; index += 64u) {
            let tile_position = group.x * 32u + index % 8u * 4u;
            let reduction = reduction_start + index / 8u;
            input_tile[index] = vec4<f16>(
                load(tile_position, reduction), load(tile_position + 1u, reduction),
                load(tile_position + 2u, reduction), load(tile_position + 3u, reduction));
        }
        for (var index = lane; index < reduction_tile * 16u; index += 64u) {
            let weight_channel = group.y * 16u + index / reduction_tile;
            let reduction = reduction_start + index % reduction_tile;
            var value = 0.0h;
            if (weight_channel < output_channels && reduction < reduction_count) {
                value = weights[weight_channel * reduction_count + reduction];
            }
            weight_tile[index] = value;
        }
        workgroupBarrier();
        for (var reduction = 0u; reduction < reduction_tile; reduction++) {
            let values = input_tile[reduction * 8u + local.x];
            if (wide_products) {
                first_sum += vec4f(values) * f32(weight_tile[local.y * 2u * reduction_tile + reduction]);
                second_sum += vec4f(values) * f32(weight_tile[(local.y * 2u + 1u) * reduction_tile + reduction]);
            } else {
                first_sum += vec4f(values * weight_tile[local.y * 2u * reduction_tile + reduction]);
                second_sum += vec4f(values * weight_tile[(local.y * 2u + 1u) * reduction_tile + reduction]);
            }
        }
        workgroupBarrier();
    }
    store(channel, position, first_sum, 4u);
    store(channel + 1u, position, second_sum, 4u);
}

struct Sums {
    first: vec3f,
    second: vec3f,
    third: vec3f,
    fourth: vec3f,
}

@compute @workgroup_size(128)
fn direct(@builtin(workgroup_id) group: vec3u, @builtin(local_invocation_index) lane: u32) {
    let output_width = (input_width + 2u * padding - 3u) / stride + 1u;
    let output_height = (input_height + 2u * padding - 3u) / stride + 1u;
    let triplets = (output_width + 2u) / 3u;
    let output_y = (group.x * 128u + lane) / triplets;
    let output_x = (group.x * 128u + lane) % triplets * 3u;
    if (output_y >= output_height) {
        return;
    }
    let position = output_y * output_width + output_x;
    let channel = group.y * 4u;
    var sums: Sums;
    for (var input_channel = 0u; input_channel < input_channels; input_channel++) {
        accumulate(output_y, output_x, channel, input_channel, 0u, 0u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 0u, 1u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 0u, 2u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 1u, 0u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 1u, 1u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 1u, 2u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 2u, 0u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 2u, 1u, &sums);
        accumulate(output_y, output_x, channel, input_channel, 2u, 2u, &sums);
    }
    let pixel_count = min(3u, output_width - output_x);
    store(channel, position, vec4f(sums.first, 0.0), pixel_count);
    store(channel + 1u, position, vec4f(sums.second, 0.0), pixel_count);
    store(channel + 2u, position, vec4f(sums.third, 0.0), pixel_count);
    store(channel + 3u, position, vec4f(sums.fourth, 0.0), pixel_count);
}

fn accumulate(output_y: u32, output_x: u32, channel: u32, input_channel: u32,
    kernel_y: u32, kernel_x: u32, sums: ptr<function, Sums>) {
    if (input_channel >= input_channels) {
        return;
    }
    let input_y = i32(output_y * stride + kernel_y) - i32(padding);
    let input_x = i32(output_x * stride + kernel_x) - i32(padding);
    let values = vec3<f16>(
        load_pixel(input_channel, input_y, input_x),
        load_pixel(input_channel, input_y, input_x + i32(stride)),
        load_pixel(input_channel, input_y, input_x + i32(2u * stride)));
    let reduction_count = input_channels * kernel_size * kernel_size;
    let reduction = input_channel * kernel_size * kernel_size + kernel_y * kernel_size + kernel_x;
    if (channel < output_channels) {
        if (wide_products) {
            (*sums).first += vec3f(values) * f32(weights[channel * reduction_count + reduction]);
        } else {
            (*sums).first += vec3f(values * weights[channel * reduction_count + reduction]);
        }
    }
    if (channel + 1u < output_channels) {
        if (wide_products) {
            (*sums).second += vec3f(values) * f32(weights[(channel + 1u) * reduction_count + reduction]);
        } else {
            (*sums).second += vec3f(values * weights[(channel + 1u) * reduction_count + reduction]);
        }
    }
    if (channel + 2u < output_channels) {
        if (wide_products) {
            (*sums).third += vec3f(values) * f32(weights[(channel + 2u) * reduction_count + reduction]);
        } else {
            (*sums).third += vec3f(values * weights[(channel + 2u) * reduction_count + reduction]);
        }
    }
    if (channel + 3u < output_channels) {
        if (wide_products) {
            (*sums).fourth += vec3f(values) * f32(weights[(channel + 3u) * reduction_count + reduction]);
        } else {
            (*sums).fourth += vec3f(values * weights[(channel + 3u) * reduction_count + reduction]);
        }
    }
}

fn store(channel: u32, position: u32, values: vec4f, pixel_count: u32) {
    let output_width = (input_width + 2u * padding - kernel_size) / stride + 1u;
    let output_height = (input_height + 2u * padding - kernel_size) / stride + 1u;
    let output_pixels = output_height * output_width;
    for (var pixel = 0u; pixel < pixel_count; pixel++) {
        if (position + pixel < output_pixels && channel < output_channels) {
            var index = channel * output_pixels + position + pixel;
            if (activation == 2u) {
                index = (channel / 6u * output_pixels + position + pixel) * 6u + channel % 6u;
            }
            output[index] = activate(values[pixel], biases[channel], activation);
        }
    }
}

@compute @workgroup_size(128)
fn pointwise(@builtin(workgroup_id) group: vec3u, @builtin(local_invocation_index) lane: u32) {
    let position = (group.x * 128u + lane) * 4u;
    let channel = group.y * 4u;
    var sums: array<vec4f, 4>;
    for (var reduction = 0u; reduction < input_channels; reduction++) {
        let values = vec4<f16>(load(position, reduction), load(position + 1u, reduction),
            load(position + 2u, reduction), load(position + 3u, reduction));
        for (var offset = 0u; offset < 4u; offset++) {
            if (channel + offset < output_channels) {
                let weight = weights[(channel + offset) * input_channels + reduction];
                if (wide_products) {
                    sums[offset] += vec4f(values) * f32(weight);
                } else {
                    sums[offset] += vec4f(values * weight);
                }
            }
        }
    }
    for (var offset = 0u; offset < 4u; offset++) {
        store(channel + offset, position, sums[offset], 4u);
    }
}
