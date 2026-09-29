# Multiscale fluorescence

Run from the repository root:

```bash
pixi run -e examples python -m examples.multiscale
```

The viewer enhances GFP and RFP structures at an adjustable spatial scale.
Brightfield stays unchanged.
The [sample image](../imaging/README.md#sample-image) shows a bacterial colony
in brightfield and two fluorescence channels.

![Original composite and enhanced fluorescence](preview.png)

Enhanced fluorescence applies this filter to GFP and RFP:

```text
fine = Gaussian(image, sigma)
coarse = Gaussian(image, 2 * sigma)
enhanced = clip(image + strength * (fine - coarse), 0, 1)
```

The reusable WESL modules live in [imaging](../imaging/README.md#shared-operations).
The compute entry points live in [shaders](shaders).
The passes for perimeter distance share the [perimeter](shaders/perimeter) directory.

Follow these modules to see how the library builds up:

1. [indexing.wesl](../imaging/indexing.wesl) maps image coordinates to buffer indices.
   [sampling.wesl](../imaging/sampling.wesl) adds clamping and channel access.
2. [gaussian.wesl](../imaging/gaussian.wesl) imports indexing and clamping to
   implement convolution.
   It also defines the weights and radius that kernels can import separately.
3. [filter.wesl](shaders/filter.wesl) imports convolution and provides a compute
   entry point.
   [correlation.wesl](shaders/correlation.wesl) combines Gaussian weights with
   shared statistics.
4. [compute.py](compute.py) uploads coefficients and schedules the GPU passes.
   Enhancement uses the same filter in two directions and at two scales.

The viewer in [viewer.py](viewer.py) connects that computation to the controls
and display.
`enhance()` and `composite()` use pygfx's shared GPU device for their resources.

The scale slider sets `sigma` in source pixels.
Each Gaussian uses a radius of `ceil(3 * sigma)`.
The filters repeat the nearest pixel at the image boundary.
Scale and strength changes update the result while you drag.
Channel gains and visibility update the display separately.

Python calculates Gaussian coefficients and uploads them to a storage buffer.
[gaussian.wesl](../imaging/gaussian.wesl) defines the weights and a pipeline constant
for the radius. Filtering and correlation import this interface.
The radius uses override ID zero so Python can set it after WESL renames imports.

The WESL `horizontal` feature selects the filter direction.
The same source serves both directions and both scales.
The compiler strips the unused implementation.

Disable brightfield and one fluorescence channel to inspect the remaining signal.
Set its gain to one, zoom into the branches, and change the scale.
The strength controls how much of that spatial detail returns to the original.

## Analysis views

Use the Analysis selector to change the right panel.
The left panel keeps the original composite.
The analyses use each channel before enhancement.
Display gains and channel visibility do not change the measurements.

The metadata identifies GFP and RFP, but does not specify what they label.
These views describe fluorescence patterns, not cell counts or population fractions.

### Channel correlation

Compare how GFP and RFP vary together within fine branches or broader regions.
The shader computes local Pearson correlation over foreground pixels.
Blue shows negative correlation, white shows zero, and red shows positive correlation.
Scale sets the neighborhood size.

Max brightfield sets an upper cutoff for the brightfield channel.
Pixels at or below this cutoff contribute to the statistics.
The colony is dark against a bright background in this sample.
The shader excludes brighter pixels before computing the statistics.

The mask does not use GFP or RFP values.
Selecting pixels by their summed fluorescence can induce negative correlation
between independent channels.
Background pixels have no overlay.
The shader also masks either channel when its local variance is at most `1e-6`.

Two Gaussian passes accumulate means, variances, covariance, and foreground weights.
Each pass updates a running mean and measures deviations from that mean.
It stores the mean as an offset from a contributing sample.
The vertical pass combines statistics from the horizontal pass.
This avoids subtracting raw intensity squares to recover small variances.

Correlation describes how intensities vary together within a neighborhood.
It does not measure a fraction of mixed cells.

### Perimeter distance

Compare fluorescence near the edge with fluorescence in the interior.
Distance from the perimeter provides a spatial coordinate for an irregular colony.

The shader smooths GFP and RFP at the selected scale.
Min signal defines an occupied region from their summed intensity.
This region estimates the fluorescence footprint.
Occupied pixels beside background become perimeter seeds.
The image border counts as background.
Holes in the footprint also contribute boundary seeds.

Jump flooding propagates nearby seeds through alternating buffers.
The output gives approximate Euclidean distance to the nearest seed pixel.
Yellow shows nearby pixels and blue shows distant pixels.
Contours sets the spacing of white lines in source pixels.
Unoccupied regions and images without seeds have no overlay.
Channel balance and the threshold affect the estimated boundary.

The profiles show mean GFP and RFP intensity against distance from the perimeter.
They use original intensities from occupied pixels.
The GPU groups pixels into at most 64 intervals of equal width.
The plots omit empty intervals at the end and show the distance range in pixels.
Contour spacing affects the overlay, not the profiles.

### Polar view

The default center is `(916, 976)` and the default radius is `880` pixels.

Unwrap the colony to inspect sector widths and branching across radius.
Center X and Center Y set the origin.
Radius sets the outer extent.
The guide on the original image marks both.
The center coordinates use source pixels, with the origin at the top left.

The horizontal axis runs clockwise from the right, from 0 to just below 360 degrees.
The vertical axis runs from the center to the selected radius.

The shader samples all three channels with bilinear interpolation.
Samples outside the source image are black.
A workgroup reduction computes mean GFP and RFP intensity for each radius.
The plots use the original intensities and exclude samples outside the image.
They include background pixels inside the image.

Each profile retains its sample count and radius.
The plots omit empty rings at the end and show the sampled radius range.

Scale and Strength do not apply to this view.
Radius is a spatial coordinate, not elapsed time.

### Shared WESL modules

`smooth()` accepts an arbitrary number of fields.
Enhancement and boundary estimation use the same filter.
[correlation.wesl](shaders/correlation.wesl) accumulates correlation statistics
in two passes.
Both kernels import Gaussian weights and boundary handling.
The `horizontal` feature specializes both kernels.

Kernels import reusable modules through `package::examples::imaging`.
Python sets the compiler root to the repository directory.
Modules within the image library use `super::` to import their siblings.

[profiles.wesl](shaders/profiles.wesl) defines three named entry points.
`radial_profile` reduces each row of the unwrapped image.
`accumulate_distance` accumulates intensities and counts within image chunks.
`finalize_distance` combines those partial sums into means for each distance interval.
All three import `sum_workgroup` from [reduction.wesl](../imaging/reduction.wesl).

Select an operation by name:

```python
shader = create_shader("profiles.wesl", dimensions, entry_point="accumulate_distance")
```

The helper passes that name to `CompileOptions.keep` and `ComputeShader`.
WESL retains the selected entry point and its dependencies.
It removes unused declarations, including resource bindings.

| Operation | Entry points |
| --- | --- |
| Enhancement | [filter.wesl](shaders/filter.wesl) smooths each channel. [enhancement.wesl](shaders/enhancement.wesl) combines the two scales with the original. |
| Correlation | [correlation.wesl](shaders/correlation.wesl) accumulates local statistics in two directions. |
| Perimeter distance | [seeds.wesl](shaders/perimeter/seeds.wesl) finds the boundary. [jump.wesl](shaders/perimeter/jump.wesl) propagates seeds. [distance.wesl](shaders/perimeter/distance.wesl) measures distance inside the footprint. |
| Polar view | [polar.wesl](shaders/polar.wesl) resamples the original channels. |
| Profiles | [profiles.wesl](shaders/profiles.wesl) reduces intensities by radius or distance from the perimeter. |
| Display | [display.wesl](shaders/display.wesl) defines `correlation_overlay`, `distance_overlay`, and `polar_guide`. |

## Verify

```bash
pixi run -e testing python -m pytest tests/examples/test_multiscale.py -q
pixi run -e testing python -m pytest \
  tests/examples/test_multiscale_analysis.py tests/examples/multiscale \
  tests/examples/test_example_render.py -q
```

[test_multiscale.py](../../tests/examples/test_multiscale.py) compares the
filter with separable NumPy convolution.
Synthetic checks do not download the TIFF.

[test_multiscale_analysis.py](../../tests/examples/test_multiscale_analysis.py)
compares correlation, distances, polar samples, and profiles with NumPy references.
It verifies that background pixels do not create correlation at a constant
foreground edge.
It also verifies independent channels and correlation after brightness offsets.
[analysis.test.wesl](../../tests/examples/multiscale/analysis.test.wesl)
tests the imported statistics and coordinate functions directly.
The render tests exercise every view and verify that display gains do not change
correlation.
They verify that polar profiles omit unsampled rings.
