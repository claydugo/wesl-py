from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import wesl

with TemporaryDirectory() as temporary_directory:
    directory = Path(temporary_directory)
    (directory / "math").mkdir()
    with urlopen(
        "https://raw.githubusercontent.com/patriciogonzalezvivo/lygia/"
        "ce08fe351478b6c14297d103a8ce98d8e787d4d2/math/mod289.wesl",
        timeout=30,
    ) as response:
        (directory / "math/mod289.wesl").write_bytes(response.read())

    result = wesl.compile_source(
        """
        import lygia::math::mod289::mod289;

        @fragment
        fn main() -> @location(0) vec4f {
            return vec4f(mod289(300.0) / 289.0, 0.0, 0.0, 1.0);
        }
        """,
        dependencies={"lygia": directory},
    )
    print(result.wgsl)  # noqa: T201
