"""Offline validation of every local image referenced by a generated README."""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def validate(path: Path) -> int:
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8"))
    for reference in images:
        if "://" in reference:
            continue
        image = path.parent / reference
        if not image.is_file():
            raise ValueError(f"Missing image: {image}")
        if image.suffix == ".svg":
            root = ET.parse(image).getroot()
            if not root.tag.endswith("svg") or not root.attrib.get("viewBox"):
                raise ValueError(f"Invalid SVG: {image}")
    return len(images)


if __name__ == "__main__":
    print(f"Validated {validate(Path(sys.argv[1]))} dashboard images.")
