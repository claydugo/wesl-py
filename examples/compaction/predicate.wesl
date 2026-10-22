@id(0) override threshold: u32 = 500;

public fn selected(value: u32) -> bool {
    return selected_at(value, threshold);
}

public fn selected_at(value: u32, limit: u32) -> bool {
    @if(keep_below) return value < limit;
    @else return value >= limit;
}
