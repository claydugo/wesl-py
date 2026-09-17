@group(0) @binding(0) var<storage, read> values: array<f32>;
@if(residual)
@group(0) @binding(1) var<storage, read> residuals: array<f32>;

fn load(index: u32) -> f32 {
    @if(residual) return values[index] + residuals[index];
    @else return values[index];
}
