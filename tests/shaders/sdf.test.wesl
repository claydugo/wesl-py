import package::examples::sdf::primitives::{sphere, smooth_union};
import wgsl_test::expectNear;

@test
fn sphere_distances() {
   expectNear(sphere(vec3f(0.0), 2.0), -2.0);
    expectNear(sphere(vec3f(3.0, 0.0, 0.0), 2.0), 1.0);
    expectNear(sphere(vec3f(3.0, 4.0, 0.0), 2.0), 3.0);
}

@test
fn smooth_union_blends_surfaces() {
    expectNear(smooth_union(0.0, 0.0, 0.4), -0.1);
    expectNear(smooth_union(0.0, 0.2, 0.4), -0.025);
    expectNear(smooth_union(0.0, 1.0, 0.4), 0.0);
}
