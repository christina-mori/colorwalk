from PIL import Image, ImageDraw
import numpy as np
import random
import math

from utils.font_utils import LATIN_DISPLAY_FONT_NAME, load_font_for_text


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([1, 1, size - 2, size - 2], fill=255)
    return mask


def _star_mask(size: int, points: int = 5) -> Image.Image:
    mask = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(mask)
    cx, cy = size / 2, size / 2
    outer, inner = size / 2 * 0.92, size / 2 * 0.4
    pts = []
    for i in range(points * 2):
        angle = math.pi / points * i - math.pi / 2
        r = outer if i % 2 == 0 else inner
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    d.polygon(pts, fill=255)
    return mask


def _teardrop_mask(size: int) -> Image.Image:
    def _bezier_points(p0, p1, p2, p3, steps=40):
        pts = []
        for i in range(steps + 1):
            t = i / steps
            mt = 1 - t
            pts.append((
                (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0],
                (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1],
            ))
        return pts

    scale = 4
    large_size = size * scale
    cx = large_size / 2
    outline = []
    outline += _bezier_points(
        (cx, large_size * 0.07),
        (cx - large_size * 0.04, large_size * 0.15),
        (cx - large_size * 0.16, large_size * 0.30),
        (cx - large_size * 0.22, large_size * 0.68),
    )[:-1]
    outline += _bezier_points(
        (cx - large_size * 0.22, large_size * 0.68),
        (cx - large_size * 0.10, large_size * 0.98),
        (cx + large_size * 0.10, large_size * 0.98),
        (cx + large_size * 0.22, large_size * 0.68),
    )[:-1]
    outline += _bezier_points(
        (cx + large_size * 0.22, large_size * 0.68),
        (cx + large_size * 0.16, large_size * 0.30),
        (cx + large_size * 0.04, large_size * 0.15),
        (cx, large_size * 0.07),
    )

    mask = Image.new('L', (large_size, large_size), 0)
    ImageDraw.Draw(mask).polygon(outline, fill=255)
    resample = getattr(Image, 'Resampling', Image).LANCZOS
    return mask.resize((size, size), resample)


def _moon_mask(size: int) -> Image.Image:
    full = Image.new('L', (size, size), 0)
    cut = Image.new('L', (size, size), 0)
    ImageDraw.Draw(full).ellipse([2, 2, size - 2, size - 2], fill=255)
    offset = size // 5
    ImageDraw.Draw(cut).ellipse([offset, 2, size - 2 + offset, size - 2], fill=255)
    arr = np.clip(np.array(full).astype(int) - np.array(cut).astype(int), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _heart_mask(size: int) -> Image.Image:
    mask = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(mask)
    pts = []
    scale = size * 0.44 / 16
    y_shift = size * 0.52
    for i in range(80):
        t = 2 * math.pi * i / 80
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((size / 2 + x * scale, y_shift + y * scale * 0.9))
    d.polygon(pts, fill=255)
    return mask


def _text_mask(size: int, text: str, font_name: str = LATIN_DISPLAY_FONT_NAME) -> Image.Image:
    mask = Image.new('L', (size * max(len(text), 1), size), 0)
    font = load_font_for_text(text, int(size * 0.85), preferred_font=font_name, fallback_font='default')
    ImageDraw.Draw(mask).text((0, 0), text, fill=255, font=font)
    return mask


SHAPE_FUNCS = {
    'circle': _circle_mask,
    'star': _star_mask,
    'teardrop': _teardrop_mask,
    'moon': _moon_mask,
    'heart': _heart_mask,
}


def _get_mask(shape: str, size: int, custom_text: str = '', font_name: str = LATIN_DISPLAY_FONT_NAME) -> Image.Image:
    if shape == 'text' and custom_text:
        return _text_mask(size, custom_text, font_name)
    return SHAPE_FUNCS.get(shape, _circle_mask)(size)


def _block_rect(img_w, img_h, position, ratio):
    r = max(0.15, min(0.65, ratio))
    if position == 'top':
        bh = int(img_h * r)
        return 0, 0, img_w, bh, img_w, img_h + bh, 0, bh
    if position == 'bottom':
        bh = int(img_h * r)
        return 0, img_h, img_w, bh, img_w, img_h + bh, 0, 0
    if position == 'left':
        bw = int(img_w * r)
        return 0, 0, bw, img_h, img_w + bw, img_h, bw, 0
    bw = int(img_w * r)
    return img_w, 0, bw, img_h, img_w + bw, img_h, 0, 0


def _block_fill(block_type, block_color, block_w, block_h, gradient_dir='vertical',
                stripe_dir='vertical', np_rng=None):
    if block_type == 'gradient':
        c1, c2 = tuple(block_color[0]), tuple(block_color[1])
        arr = np.zeros((block_h, block_w, 3), dtype=np.uint8)
        if gradient_dir == 'horizontal':
            for x in range(block_w):
                t = x / max(block_w - 1, 1)
                arr[:, x] = [int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)]
        else:
            for y in range(block_h):
                t = y / max(block_h - 1, 1)
                arr[y, :] = [int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)]
        return Image.fromarray(arr)

    if block_type == 'stripe':
        c1, c2 = tuple(block_color[0]), tuple(block_color[1])
        arr = np.zeros((block_h, block_w, 3), dtype=np.uint8)
        if stripe_dir == 'horizontal':
            stripe_h = max(1, block_h // 8)
            for y in range(block_h):
                arr[y, :] = c1 if (y // stripe_h) % 2 == 0 else c2
        else:
            stripe_w = max(1, block_w // 8)
            for x in range(block_w):
                arr[:, x] = c1 if (x // stripe_w) % 2 == 0 else c2
        return Image.fromarray(arr)

    if block_type == 'vintage':
        base_c = tuple(block_color) if not isinstance(block_color[0], (list, tuple)) else tuple(block_color[0])
        arr = np.full((block_h, block_w, 3), base_c, dtype=np.int16)
        if np_rng is None:
            grain = np.random.randint(-28, 28, (block_h, block_w, 3), dtype=np.int16)
        else:
            grain = np_rng.integers(-28, 28, (block_h, block_w, 3), dtype=np.int16)
        arr = np.clip(arr + grain, 0, 255).astype(np.uint8)
        arr[::4, :] = np.clip(arr[::4, :].astype(np.int16) - 22, 0, 255).astype(np.uint8)
        yy, xx = np.mgrid[0:block_h, 0:block_w]
        ny = (yy / max(block_h - 1, 1) - 0.5) * 2
        nx = (xx / max(block_w - 1, 1) - 0.5) * 2
        vig = np.clip(1.0 - (ny ** 2 + nx ** 2) * 0.45, 0.55, 1.0)
        arr = np.clip(arr * vig[:, :, np.newaxis], 0, 255).astype(np.uint8)
        return Image.fromarray(arr)

    return Image.new('RGB', (block_w, block_h), tuple(block_color))


def _primary_color(block_color):
    if isinstance(block_color, (list, tuple)) and isinstance(block_color[0], (list, tuple)):
        return tuple(block_color[0])
    return tuple(block_color)


def _gen_normalized_positions(count, distribution, rng=None):
    rng = rng or random
    positions = []
    if distribution == 'grid':
        cols = max(1, round(math.sqrt(count)))
        rows = max(1, math.ceil(count / cols))
        gx = 1 / cols
        gy = 1 / rows
        for r in range(rows):
            for c in range(cols):
                x = min(max(gx * (c + 0.5) + rng.uniform(-gx * 0.15, gx * 0.15), 0.02), 0.98)
                y = min(max(gy * (r + 0.5) + rng.uniform(-gy * 0.15, gy * 0.15), 0.02), 0.98)
                positions.append((x, y))
    elif distribution == 'edge':
        band = 0.25
        for _ in range(count):
            side = rng.choice(['top', 'bottom', 'left', 'right'])
            if side == 'top':
                positions.append((rng.uniform(0.02, 0.98), rng.uniform(0.02, band)))
            elif side == 'bottom':
                positions.append((rng.uniform(0.02, 0.98), rng.uniform(1 - band, 0.98)))
            elif side == 'left':
                positions.append((rng.uniform(0.02, band), rng.uniform(0.02, 0.98)))
            else:
                positions.append((rng.uniform(1 - band, 0.98), rng.uniform(0.02, 0.98)))
    else:
        positions = [(rng.uniform(0.02, 0.98), rng.uniform(0.02, 0.98)) for _ in range(count)]
    return positions[:count]


def _scale_positions(normalized_positions, width, height):
    return [(int(nx * width), int(ny * height)) for nx, ny in normalized_positions]


def _clamp_top_left(cx, cy, width, height, patch_w, patch_h):
    return (
        min(max(int(round(cx - patch_w / 2)), 0), max(width - patch_w, 0)),
        min(max(int(round(cy - patch_h / 2)), 0), max(height - patch_h, 0)),
    )


def _build_size_factors(count, size_random, rng):
    if not size_random:
        return [1.0] * count
    return [rng.uniform(0.5, 1.7) for _ in range(count)]


def make_dot_puzzle(
    img: Image.Image,
    position: str = 'right',
    block_ratio: float = 0.4,
    block_type: str = 'solid',
    block_color=None,
    shape: str = 'circle',
    custom_text: str = '',
    font_name: str = LATIN_DISPLAY_FONT_NAME,
    dot_size: int = 60,
    dot_count: int = 12,
    distribution: str = 'random',
    manual_positions=None,
    text_overlay: str = '',
    text_font_size: int = 32,
    text_color: tuple = None,
    gradient_dir: str = 'vertical',
    stripe_dir: str = 'vertical',
    size_random: bool = False,
    decouple: bool = False,
    seed: int = None,
    block_distribution: str = None,
    block_manual_positions=None,
) -> Image.Image:

    img = img.convert('RGB')
    iw, ih = img.size

    rng = random.Random(seed) if seed is not None else random
    np_rng = np.random.default_rng(seed) if seed is not None else None

    if block_color is None:
        block_color = (200, 180, 160)

    bx, by, bw, bh, canvas_w, canvas_h, img_ox, img_oy = _block_rect(iw, ih, position, block_ratio)
    block_img = _block_fill(block_type, block_color, bw, bh, gradient_dir, stripe_dir, np_rng=np_rng)
    img_copy = img.copy()
    fill_color = _primary_color(block_color)
    stripe_colors = None
    if block_type == 'stripe' and isinstance(block_color, (list, tuple)) and len(block_color) >= 2:
        stripe_colors = [tuple(block_color[0]), tuple(block_color[1])]

    if manual_positions is not None:
        image_centers_norm = [(float(nx), float(ny)) for nx, ny in manual_positions]
    else:
        image_centers_norm = _gen_normalized_positions(dot_count, distribution, rng=rng)

    if decouple:
        block_dist = block_distribution or distribution
        if block_dist == 'linked':
            block_centers_norm = list(image_centers_norm)
        elif block_manual_positions is not None:
            block_centers_norm = [(float(nx), float(ny)) for nx, ny in block_manual_positions]
        else:
            block_centers_norm = _gen_normalized_positions(dot_count, block_dist, rng=rng)
    else:
        block_centers_norm = list(image_centers_norm)

    image_centers_px = _scale_positions(image_centers_norm, iw, ih)
    block_centers_px = _scale_positions(block_centers_norm, bw, bh)
    if image_centers_px:
        block_sample_px = [image_centers_px[idx % len(image_centers_px)] for idx in range(len(block_centers_px))]
    else:
        block_sample_px = []

    image_size_factors = _build_size_factors(len(image_centers_px), size_random, rng)
    block_size_factors = _build_size_factors(len(block_centers_px), size_random, rng)

    for idx, (img_cx, img_cy) in enumerate(image_centers_px):
        s = max(20, int(round(dot_size * image_size_factors[idx])))
        mask = _get_mask(shape, s, custom_text, font_name)
        mw, mh = mask.size

        ix, iy = _clamp_top_left(img_cx, img_cy, iw, ih, mw, mh)
        fill = stripe_colors[idx % 2] if stripe_colors else fill_color
        img_copy.paste(Image.new('RGB', (mw, mh), fill), (ix, iy), mask)

    for idx, ((sample_cx, sample_cy), (block_cx, block_cy)) in enumerate(zip(block_sample_px, block_centers_px)):
        s = max(20, int(round(dot_size * block_size_factors[idx])))
        mask = _get_mask(shape, s, custom_text, font_name)
        mw, mh = mask.size

        sample_x, sample_y = _clamp_top_left(sample_cx, sample_cy, iw, ih, mw, mh)
        img_patch = img.crop((sample_x, sample_y, sample_x + mw, sample_y + mh))
        tx, ty = _clamp_top_left(block_cx, block_cy, bw, bh, mw, mh)
        block_img.paste(img_patch, (tx, ty), mask)

    canvas = Image.new('RGB', (canvas_w, canvas_h), (255, 255, 255))
    canvas.paste(img_copy, (img_ox, img_oy))
    canvas.paste(block_img, (bx, by))

    if text_overlay:
        draw = ImageDraw.Draw(canvas)
        font = load_font_for_text(text_overlay, text_font_size, preferred_font=font_name, fallback_font='default')
        auto_color = _auto_text_color(fill_color)
        tc = text_color if text_color else auto_color
        bbox = draw.textbbox((0, 0), text_overlay, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((bx + (bw - tw) // 2, by + (bh - th) // 2), text_overlay, fill=tc, font=font)

    return canvas


def _auto_text_color(bg) -> tuple:
    r, g, b = (bg[0], bg[1], bg[2]) if len(bg) >= 3 else (180, 160, 140)
    return (30, 30, 30) if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5 else (240, 240, 240)
