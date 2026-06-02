from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

FONT_PATH = Path(__file__).resolve().parent.parent / "static" / "fonts"
LATIN_DISPLAY_FONT_NAME = "CoralLovers"


def _looks_latin_display_text(text: str) -> bool:
    visible = False
    for ch in text:
        if ch.isspace():
            continue
        visible = True
        code = ord(ch)
        if code < 128:
            continue
        if 0x00A0 <= code <= 0x024F:
            continue
        if 0x2000 <= code <= 0x206F:
            continue
        if 0x20A0 <= code <= 0x20CF:
            continue
        return False
    return visible


def _project_font_candidates(font_name: str) -> list[tuple[Path, int]]:
    if not font_name:
        return []

    raw_names = [font_name] if font_name.lower().endswith((".otf", ".ttf", ".ttc")) else [
        f"{font_name}.otf",
        f"{font_name}.ttf",
        f"{font_name}.ttc",
    ]
    return [(FONT_PATH / name, 0) for name in raw_names]


def load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        *_project_font_candidates(font_name),
        *_project_font_candidates("NotoSerifSC-Regular"),
        *_project_font_candidates("default"),
        (Path("C:/Windows/Fonts/msyh.ttc"), 0),
        (Path("C:/Windows/Fonts/simhei.ttf"), 0),
        (Path("C:/Windows/Fonts/simsun.ttc"), 0),
        (Path("C:/Windows/Fonts/georgia.ttf"), 0),
        (Path("C:/Windows/Fonts/arial.ttf"), 0),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), 0),
    ]

    seen: set[tuple[str, int]] = set()
    for path, index in candidates:
        key = (str(path), index)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        try:
            return ImageFont.truetype(str(path), size, index=index)
        except Exception:
            continue

    return ImageFont.load_default()


def load_font_for_text(
    text: str,
    size: int,
    preferred_font: str = LATIN_DISPLAY_FONT_NAME,
    fallback_font: str = "default",
) -> ImageFont.FreeTypeFont:
    font_name = preferred_font if _looks_latin_display_text(text) else fallback_font
    return load_font(font_name, size)
