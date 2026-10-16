import wgsl_test::{expectWithinVec2, expectNearVec3, expectUlpVec4};

fn verify_vectors() {
    expectWithinVec2(vec2f(1.0, 2.0), vec2f(1.01, 2.0), 0.02, 0.0);
    expectNearVec3(vec3f(0.0), vec3f(0.0000001));
    expectUlpVec4(vec4f(-0.0, 1.0, -1.0, 0.0), vec4f(0.0, 1.0, -1.0, -0.0), 0u);
}
