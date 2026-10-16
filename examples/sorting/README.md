# Parallel sorting

Run from the repository root:

```bash
pixi run -e examples python -m examples.sorting
```

Three GPU sorts order the same random colors side by side.
Each bar shows one color, and its height shows the sort key.
Dim bars are out of order with a neighbor.
White caps mark values that moved in the latest stage.

Use the controls to choose the key, the input, the value count, and the speed.
Dots draws one dot per value, which reads better at large counts.
A key change restarts all three sorts from the same input.
Pause and Step advance one stage at a time.

Each stage is one compute dispatch over the whole array.
The panels advance together, so the stage counts compare directly:

| Sort | Stages for `n` values |
| --- | --- |
| [Bitonic](shaders/bitonic.wesl) | `log2(n) * (log2(n) + 1) / 2` |
| [Odd-even transposition](shaders/transposition.wesl) | `n` |
| [Radix](shaders/radix.wesl) | 10, one for each key bit |

All three sorts run every stage for every input.
A nearly sorted input moves few values in the comparison sorts.

## Why WESL

Every shader depends on `package::examples::sorting::key`,
but no file has that path.
[renderer.py](renderer.py) supplies one file from [keys](keys) as that module
through the `modules` argument of `wesl.Compiler.from_project`.
The kernels compile once for each key.
Add a file to [keys](keys) to add an entry to the Key menu.

A key module exports `key(value: u32) -> u32`.
The value is a packed RGBA8 color. The key must be less than 1024.

[order.wesl](order.wesl) compares two values through the key.
Bitonic sort, odd-even transposition sort, and [bars.wesl](shaders/bars.wesl)
import it. The bar renderer uses the same order to dim bars.
The radix sort imports the key directly and splits on one key bit per stage.

[scan.wesl](../parallel/scan.wesl) supplies the workgroup scan for the radix
split. The split runs in one 128-invocation workgroup and keeps equal keys in order.
[renderer.py](renderer.py) copies the result back to the displayed buffer.

The Reversed and Nearly sorted inputs need sorted colors first.
Python does not have a copy of the key. Instead,
[renderer.py](renderer.py) runs the radix sort to completion and reads the result.

[renderer.py](renderer.py) compiles the pipelines, submits stages, and draws the
bars. [viewer.py](viewer.py) generates inputs and manages timing and controls.
Bitonic sort requires a power-of-two value count.

## Verify

```bash
pixi run -e testing python -m pytest tests/examples/test_sorting.py \
  tests/examples/sorting tests/examples/parallel -q
```

The Python tests run each key. They compile a small kernel that imports the
same key module and computes keys on the GPU. With those keys, they check that
radix sort matches a stable NumPy sort and that the other sorts order the keys.
They also check the reversed input, the stage counts, and both display modes.

[Native tests](../../tests/examples/sorting/key.test.wesl) substitute each key
file through the `wesl_modules` fixture. They check that keys stay below 1024 for
random colors and the corners of the RGB cube, and that the order is total.
[The scan test](../../tests/examples/parallel/scan.test.wesl) compares the
workgroup scan with a sequential sum over three rounds.
