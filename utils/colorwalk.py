from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import colorsys

from utils.font_utils import LATIN_DISPLAY_FONT_NAME, load_font_for_text


def extract_dominant_color(img: Image.Image, n_colors: int = 5) -> tuple:
    """Extract dominant color from image using quantization."""
    small = img.copy().convert('RGB')
    small.thumbnail((150, 150))
    quantized = small.quantize(colors=n_colors, method=Image.Quantize.FASTOCTREE)
    palette = quantized.getpalette()[:n_colors * 3]
    colors = [(palette[i], palette[i+1], palette[i+2]) for i in range(0, len(palette), 3)]

    # Pick the most saturated/vivid color (avoid near-white/black)
    best = colors[0]
    best_score = -1
    for c in colors:
        r, g, b = [x/255 for x in c]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        score = s * 0.6 + (1 - abs(v - 0.55)) * 0.4
        if score > best_score:
            best_score = score
            best = c
    return best


def make_colorwalk(
    img: Image.Image,
    color: tuple = None,
    color_ratio: float = 0.45,
    text: str = '',
    font_size: int = 36,
    text_color: tuple = None,
    font_name: str = LATIN_DISPLAY_FONT_NAME,
) -> Image.Image:
    """
    Generate a Colorwalk image: solid color block on top, original photo on bottom.
    color_ratio: fraction of total height occupied by the color block (0.3 ~ 0.6)
    """
    orig_w, orig_h = img.size
    total_h = orig_h + int(orig_h * color_ratio)
    block_h = int(orig_h * color_ratio)

    if color is None:
        color = extract_dominant_color(img)

    canvas = Image.new('RGB', (orig_w, total_h), color)
    canvas.paste(img, (0, block_h))

    # Draw text
    if text:
        draw = ImageDraw.Draw(canvas)
        auto_text_color = _auto_text_color(color) if text_color is None else text_color
        font = load_font_for_text(text, font_size, preferred_font=font_name, fallback_font='default')
        # Center text vertically in color block
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (orig_w - tw) // 2
        ty = (block_h - th) // 2
        draw.text((tx, ty), text, fill=auto_text_color, font=font)

    return canvas


def _auto_text_color(bg: tuple) -> tuple:
    r, g, b = bg
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return (30, 30, 30) if luminance > 0.5 else (240, 240, 240)
