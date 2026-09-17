import package::levels::adjust;
import wgsl_test::expectWithin;

@test
fn highlight_matches_reference() {
    expectWithin(adjust(0.75), 0.75, 0.0, 0.0001);
}
