from pathlib import Path
from urllib.request import urlopen

directory = Path(__file__).resolve().parents[1] / ".wesl/lygia"
for filename in ("color/palette/heatmap.wesl", "math/map.wesl"):
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(
        f"https://raw.githubusercontent.com/patriciogonzalezvivo/lygia/"
        f"ce08fe351478b6c14297d103a8ce98d8e787d4d2/{filename}",
        timeout=30,
    ) as response:
        path.write_bytes(response.read())

(directory / "wesl.toml").write_text(
    'edition = "2026_pre"\nroot = "."\n', encoding="utf-8"
)
