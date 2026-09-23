import examples::lygia::terrain::elevation;
import examples::lygia::palette::color;
import wgsl_test::{expect, expectNearVec3};

@test
fn terrain_bounds_and_continuity() {
    for (var index = 0u; index < 32u; index++) {
        let position = vec2f(f32(index) * 0.37, f32(index) * -0.21);
        let height = elevation(position, 0.0, 17, 0.38);
        expect(height >= 0.0 && height <= 1.0);
        let adjacent = elevation(position + vec2f(0.00001), 0.0, 17, 0.38);
        expect(abs(height - adjacent) < 0.01);
    }
}

@test
fn seed_and_time_change_the_field() {
    let original = elevation(vec2f(0.2, 0.7), 0.0, 17, 0.38);
    expect(abs(original - elevation(vec2f(0.2, 0.7), 0.0, 42, 0.38)) > 0.001);
    expect(abs(original - elevation(vec2f(0.2, 0.7), 2.0, 17, 0.38)) > 0.001);
}

@test
fn palette_bounds() {
    expectNearVec3(color(0.0, 0.52, 0u), vec3f(0.018, 0.045, 0.075));
    for (var palette = 0u; palette < 3u; palette++) {
        for (var index = 0u; index <= 16u; index++) {
            let shaded = color(f32(index) / 16.0, 0.52, palette);
            expect(all(shaded >= vec3f(0.0)) && all(shaded <= vec3f(1.0)));
        }
    }
}
