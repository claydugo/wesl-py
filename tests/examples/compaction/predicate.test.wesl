import examples::compaction::predicate::selected;
import wgsl_test::expectEq;

@test
fn threshold_boundary() {
    @if(keep_below) {
        expectEq(u32(selected(499u)), 1u);
        expectEq(u32(selected(500u)), 0u);
        expectEq(u32(selected(501u)), 0u);
    }
    @else {
        expectEq(u32(selected(499u)), 0u);
        expectEq(u32(selected(500u)), 1u);
        expectEq(u32(selected(501u)), 1u);
    }
}
