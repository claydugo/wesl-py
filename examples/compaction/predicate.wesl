@id(0) override threshold: u32 = 500;

fn selected(value: u32) -> bool {
    @if(keep_below) return value < threshold;
    @else return value >= threshold;
}
