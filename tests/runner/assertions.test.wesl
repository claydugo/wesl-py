import super::helpers::verify_vectors;
import wgsl_test::{expect, expectEq, expectNear as near, expectUlp, expectWithin};

@test
fn assertions_pass_in_every_scope() {
    verify_vectors();
    expect(true);
    expectEq(4294967295u, 4294967295u);
    expect(-2147483647i == -2147483647i);
    near(1.0, 1.0001);
    expectWithin(100.0, 101.0, 0.01, 0.0);
    expectUlp(1.0, 1.0000001, 1u);

    { expectEq(1u, 1u); }
    if false {} else if true { expectEq(2u, 2u); } else { expect(false); }
    for (expectEq(3u, 3u); false; expectEq(0u, 1u)) {}
    for (var index = 0u; index < 3u; expectEq(index, index)) { index++; }
    var count = 0u;
    while count < 2u { expectEq(count, count); count++; }
    loop {
        continuing { expectEq(count, 2u); break if true; }
    }
    switch count {
        case 2u: { expectEq(count, 2u); }
        default: { expect(false); }
    }
}
