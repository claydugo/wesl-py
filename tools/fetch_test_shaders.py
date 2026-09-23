from pathlib import Path
from urllib.request import urlopen

directory = Path(__file__).resolve().parents[1] / ".wesl/lygia"
for filename in (
    "generative/snoise.wesl",
    "math/mod289.wesl",
    "math/permute.wesl",
    "math/taylorInvSqrt.wesl",
    "math/grad4.wesl",
):
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(
        f"https://raw.githubusercontent.com/patriciogonzalezvivo/lygia/"
        f"ce08fe351478b6c14297d103a8ce98d8e787d4d2/{filename}",
        timeout=30,
    ) as response:
        path.write_bytes(response.read())

(directory / "NOISE-LICENSE-MIT").write_bytes(
    (Path(__file__).resolve().parents[1] / "licenses/LYGIA-NOISE-MIT").read_bytes()
)

(directory / "wesl.toml").write_text(
    'edition = "2026_pre"\nroot = "."\n', encoding="utf-8"
)
