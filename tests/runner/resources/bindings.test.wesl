import wgsl_test::{expectEq, expectNearVec4, expectUlp};

@group(0) @binding(0) var<uniform> increment: vec4u;
@group(2) @binding(0) var color: texture_2d<f32>;
@group(2) @binding(1) var unfilterable: texture_2d<f32>;
@group(2) @binding(2) var nearest: sampler;
@group(2) @binding(3) var<storage, read> stored: u32;

@test
fn bindings_across_groups() {
    expectEq(increment.x + stored, 10u);
    expectNearVec4(textureSampleLevel(color, nearest, vec2f(0.5), 0.0), vec4f(1.0, 0.0, 0.0, 1.0));
    expectUlp(textureSampleLevel(unfilterable, nearest, vec2f(0.5), 0.0).w, 1.0000009536743164, 0u);
}
