import package::examples::sorting::key::key;
import package::examples::sorting::order::ordered;
import package::tests::examples::random::random;
import wgsl_test::expect;

fn color(seed: u32) -> u32 {
    return pack4x8unorm(vec4f(random(seed), random(seed + 1u), random(seed + 2u), 1.0));
}

@test @workgroup_size(64)
fn ten_bit_total_order(@builtin(local_invocation_index) lane: u32) {
    let corner = pack4x8unorm(vec4f(
        f32(lane & 1u),
        f32((lane >> 1u) & 1u),
        f32((lane >> 2u) & 1u),
        1.0,
    ));
    expect(key(corner) < 1024u);
    for (var round = 0u; round < 16u; round++) {
        let first = color(lane * 96u + round * 6u);
        let second = color(lane * 96u + round * 6u + 3u);
        expect(key(first) < 1024u);
        expect(ordered(first, first));
        expect(ordered(first, second) || ordered(second, first));
    }
}
