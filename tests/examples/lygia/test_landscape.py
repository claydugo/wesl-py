import logging
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

numpy = pytest.importorskip("numpy")
wgpu = pytest.importorskip("wgpu")
imageio = pytest.importorskip("imageio.v3")
pytest.importorskip("imgui_bundle")
Renderer = import_module("examples.lygia.renderer").Renderer
Viewer = import_module("examples.lygia.viewer").Viewer
RenderCanvas = import_module("rendercanvas.offscreen").RenderCanvas


@pytest.mark.gpu
def test_landscape_controls(
    wesl_device: wgpu.GPUDevice, library_directory: Path
) -> None:
    renderer = Renderer(wesl_device, "rgba8unorm", library_directory)
    target = wesl_device.create_texture(
        size=(129, 67, 1),
        format="rgba8unorm",
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
    )
    parameters = numpy.array(
        [[129, 67, 0, 0], [0, 0, 3.4, 0.38], [0.52, 0, 0.5, 0.65]],
        dtype=numpy.float32,
    )
    parameters.view(numpy.int32)[0, 3] = 17
    try:
        renderer.render(target, parameters)
        original = numpy.frombuffer(
            wesl_device.queue.read_texture(
                {"texture": target}, {"bytes_per_row": 129 * 4}, target.size
            ),
            dtype=numpy.uint8,
        ).reshape(67, 129, 4)
        assert numpy.all(original[..., 3] == 255)  # noqa: PLR2004
        assert original[..., :3].std() > 20  # noqa: PLR2004
        for row, column, value in (
            (0, 2, 3),
            (1, 0, 1),
            (1, 2, 6),
            (1, 3, 0.65),
            (2, 0, 0.7),
            (2, 1, 1),
            (2, 1, 2),
            (2, 2, 0),
            (2, 3, 0),
        ):
            changed = parameters.copy()
            changed[row, column] = value
            renderer.render(target, changed)
            actual = numpy.frombuffer(
                wesl_device.queue.read_texture(
                    {"texture": target}, {"bytes_per_row": 129 * 4}, target.size
                ),
                dtype=numpy.uint8,
            ).reshape(67, 129, 4)
            assert numpy.any(actual[..., :3] != original[..., :3])
    finally:
        target.destroy()


@pytest.mark.gpu
def test_surface_formats(wesl_device: wgpu.GPUDevice, library_directory: Path) -> None:
    parameters = numpy.array(
        [[65, 33, 0, 0], [0, 0, 3.4, 0.38], [0.52, 0, 0.5, 0.65]],
        dtype=numpy.float32,
    )
    parameters.view(numpy.int32)[0, 3] = 17
    images = []
    for texture_format in ("rgba8unorm", "rgba8unorm-srgb"):
        renderer = Renderer(wesl_device, texture_format, library_directory)
        target = wesl_device.create_texture(
            size=(65, 33, 1),
            format=texture_format,
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
        )
        try:
            renderer.render(target, parameters)
            images.append(
                numpy.frombuffer(
                    wesl_device.queue.read_texture(
                        {"texture": target}, {"bytes_per_row": 65 * 4}, target.size
                    ),
                    dtype=numpy.uint8,
                )
            )
        finally:
            target.destroy()
    numpy.testing.assert_allclose(images[0], images[1], atol=1)


@pytest.mark.gpu
def test_viewer(
    wesl_device: wgpu.GPUDevice,
    library_directory: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    canvas = RenderCanvas(size=(960, 800))
    try:
        viewer = Viewer(canvas, wesl_device, library_directory=library_directory)
        for _ in range(3):
            original = numpy.asarray(canvas.draw()).copy()
        numpy.testing.assert_array_equal(original, canvas.draw())
        assert viewer.elapsed == 0
        viewer.animated = True
        viewer.previous_time -= 1
        canvas.draw()
        assert viewer.elapsed > 0
        viewer.animated = False
        for palette in (1, 2):
            viewer.palette = palette
            image = numpy.asarray(canvas.draw())
            assert numpy.any(image[:, 320:] != original[:, 320:])
        viewer.save_requested = True
        image = numpy.asarray(canvas.draw())
        saved = imageio.imread(tmp_path / "landscape.png")
        numpy.testing.assert_array_equal(saved[:, 320:], image[:, 320:])
        assert viewer.saved
        canvas.set_logical_size(640, 480)
        resized = numpy.asarray(canvas.draw())
        assert resized.shape == (480, 640, 4)
        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]
    finally:
        canvas.close()


@pytest.mark.gpu
def test_seed_precision(wesl_device: wgpu.GPUDevice, library_directory: Path) -> None:
    canvas = RenderCanvas(size=(640, 480))
    try:
        viewer = Viewer(canvas, wesl_device, library_directory=library_directory)
        images = []
        for seed in (
            0,
            16777216,
            16777217,
            123456789,
            987654321,
            -2147483648,
            -2147483647,
            2147483646,
            2147483647,
        ):
            viewer.seed = seed
            image = numpy.asarray(canvas.draw())[:, 320:, :3].copy()
            for previous in images:
                assert not numpy.array_equal(image, previous), seed
            images.append(image)
        viewer.seed = 0
        numpy.testing.assert_array_equal(
            numpy.asarray(canvas.draw())[:, 320:, :3], images[0]
        )
    finally:
        canvas.close()


@pytest.mark.gpu
@pytest.mark.usefixtures("wesl_device")
@pytest.mark.parametrize("seed", [-2147483648, 2147483647])
def test_cli(library_directory: Path, tmp_path: Path, seed: int) -> None:
    screenshot = tmp_path / "landscape.png"
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "examples.lygia",
            "--library",
            str(library_directory),
            "--seed",
            str(seed),
            "--screenshot",
            str(screenshot),
        ],
        cwd=Path(__file__).parents[3],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Draw error" not in result.stderr
    image = imageio.imread(screenshot)
    assert image.shape == (900, 1440, 4)
    assert image[:, 320:, :3].std() > 20  # noqa: PLR2004


@pytest.mark.parametrize("seed", [-2147483649, 2147483648, 4294967295])
def test_cli_rejects_invalid_seed(tmp_path: Path, seed: int) -> None:
    screenshot = tmp_path / "landscape.png"
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "examples.lygia",
            "--seed",
            str(seed),
            "--screenshot",
            str(screenshot),
        ],
        cwd=Path(__file__).parents[3],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2  # noqa: PLR2004
    assert "--seed must be between -2147483648 and 2147483647" in result.stderr
    assert "Draw error" not in result.stderr
    assert not screenshot.exists()
