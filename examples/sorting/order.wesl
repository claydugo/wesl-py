import package::examples::sorting::key::key;

public fn ordered(first: u32, second: u32) -> bool {
    return key(first) <= key(second);
}
