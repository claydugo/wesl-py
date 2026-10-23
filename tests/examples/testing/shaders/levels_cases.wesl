import constants::{value, expected};
import super::levels::adjust;
import wgsl_test::expectNear;

@test fn adjusts_value() {
    expectNear(adjust(value), expected);
}
