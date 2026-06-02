import unittest

import numpy as np
from PIL import Image

from utils.colorwalk import make_colorwalk
from utils.dot_puzzle import _block_fill, _teardrop_mask, make_dot_puzzle


def make_sample_image(width=120, height=90):
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            arr[y, x] = (
                (x * 2) % 256,
                (y * 3) % 256,
                ((x + y) * 4) % 256,
            )
    return Image.fromarray(arr, "RGB")


class BlockFillTests(unittest.TestCase):
    def test_vertical_stripe_alternates_by_columns(self):
        img = _block_fill(
            "stripe",
            [(10, 20, 30), (40, 50, 60)],
            16,
            8,
            stripe_dir="vertical",
        )
        arr = np.array(img)
        self.assertTrue((arr[:, 0] == (10, 20, 30)).all())
        self.assertTrue((arr[:, 1] == (10, 20, 30)).all())
        self.assertTrue((arr[:, 2] == (40, 50, 60)).all())
        self.assertTrue((arr[:, 3] == (40, 50, 60)).all())

    def test_horizontal_stripe_alternates_by_rows(self):
        img = _block_fill(
            "stripe",
            [(10, 20, 30), (40, 50, 60)],
            8,
            16,
            stripe_dir="horizontal",
        )
        arr = np.array(img)
        self.assertTrue((arr[0, :] == (10, 20, 30)).all())
        self.assertTrue((arr[1, :] == (10, 20, 30)).all())
        self.assertTrue((arr[2, :] == (40, 50, 60)).all())
        self.assertTrue((arr[3, :] == (40, 50, 60)).all())


class DotPuzzleTests(unittest.TestCase):
    def test_teardrop_mask_has_soft_tip_and_rounded_base(self):
        arr = np.array(_teardrop_mask(120)) > 127

        top_width = int(arr[12].sum())
        mid_width = int(arr[60].sum())
        base_width = int(arr[84].sum())
        bottom_width = int(arr[108].sum())

        self.assertGreater(mid_width, top_width * 4)
        self.assertGreater(base_width, mid_width)
        self.assertLess(bottom_width, base_width)
        self.assertGreater(bottom_width, 0)

    def test_photo_side_alternates_two_stripe_colors(self):
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        result = make_dot_puzzle(
            img,
            position="right",
            block_ratio=0.2,
            block_type="stripe",
            block_color=[(10, 20, 30), (40, 50, 60)],
            shape="circle",
            dot_size=20,
            distribution="manual",
            manual_positions=[(0.25, 0.5), (0.75, 0.5)],
            seed=7,
        )
        self.assertEqual(result.getpixel((25, 50)), (10, 20, 30))
        self.assertEqual(result.getpixel((75, 50)), (40, 50, 60))

    def test_decouple_variants_render_without_error(self):
        img = make_sample_image()
        manual_points = [(0.2, 0.2), (0.7, 0.6), (0.5, 0.85)]
        block_manual_points = [(0.15, 0.3), (0.65, 0.55)]
        variants = [
            {"distribution": "random", "block_distribution": "linked"},
            {"distribution": "grid", "block_distribution": "random"},
            {"distribution": "edge", "block_distribution": "grid"},
            {"distribution": "random", "block_distribution": "edge"},
            {
                "distribution": "manual",
                "manual_positions": manual_points,
                "block_distribution": "manual",
                "block_manual_positions": block_manual_points,
            },
        ]

        for variant in variants:
            with self.subTest(variant=variant):
                result = make_dot_puzzle(
                    img,
                    position="right",
                    block_ratio=0.4,
                    block_type="gradient",
                    block_color=[(240, 200, 180), (120, 170, 220)],
                    shape="circle",
                    dot_size=26,
                    dot_count=6,
                    size_random=True,
                    decouple=True,
                    seed=12345,
                    **variant,
                )
                self.assertEqual(result.size, (168, 90))
                self.assertNotEqual(result.getbbox(), None)

    def test_empty_block_manual_positions_do_not_fallback_to_random(self):
        img = make_sample_image(100, 100)
        result = make_dot_puzzle(
            img,
            position="top",
            block_ratio=0.4,
            block_type="solid",
            block_color=(180, 220, 200),
            shape="circle",
            dot_size=18,
            dot_count=5,
            distribution="manual",
            manual_positions=[(0.3, 0.7), (0.7, 0.7)],
            decouple=True,
            block_distribution="manual",
            block_manual_positions=[],
            seed=999,
        )
        arr = np.array(result)
        block_region = arr[:40, :, :]
        self.assertEqual(int(np.count_nonzero(np.any(block_region != (180, 220, 200), axis=2))), 0)


class ColorwalkTests(unittest.TestCase):
    def test_explicit_color_is_used_for_block(self):
        img = make_sample_image(80, 60)
        result = make_colorwalk(
            img,
            color=(12, 34, 56),
            color_ratio=0.5,
            text="",
        )
        self.assertEqual(result.getpixel((5, 5)), (12, 34, 56))


if __name__ == "__main__":
    unittest.main()
