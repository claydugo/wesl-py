import examples::lygia::colorize::colorize;
import wgsl_test::expectNearVec4;

@test
fn display_range() {
    expectNearVec4(colorize(2.0, 2.0, 6.0), vec4f(0.0, 0.0, 0.91, 1.0));
    expectNearVec4(colorize(4.0, 2.0, 6.0), vec4f(0.4375, 0.9919, 0.4375, 1.0));
    expectNearVec4(colorize(6.0, 2.0, 6.0), vec4f(0.91, 0.0784, 0.0, 1.0));
    expectNearVec4(colorize(-1.0, 2.0, 6.0), colorize(2.0, 2.0, 6.0));
    expectNearVec4(colorize(8.0, 2.0, 6.0), colorize(6.0, 2.0, 6.0));
}
