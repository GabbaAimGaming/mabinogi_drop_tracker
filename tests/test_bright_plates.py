import unittest

import numpy as np
from PIL import Image, ImageDraw

from drop_tool.bright_plates import recover
from drop_tool.alt_display import quick_check
from drop_tool.vision import Vision


def scene(plates=True):
    image = Image.new('RGB', (600, 400), (230, 110, 95))
    draw = ImageDraw.Draw(image)
    for y, color in ((130, 'white'), (156, (60, 240, 30)), (182, (20, 230, 250))):
        if plates:
            draw.rectangle((180, y, 380, y+20), fill=(135, 65, 55))
        for x in range(185, 372, 11):
            draw.rectangle((x, y+5, x+6, y+14), outline=color, width=1)
            draw.line((x, y+9, x+6, y+9), fill=color)
    return image


class BrightPlateTests(unittest.TestCase):
    def test_translucent_plates_keep_color_pixels_and_position(self):
        image = scene()
        before = image.tobytes()
        rows = recover(image)
        self.assertEqual(len(rows), 3)
        for y, x, crop in rows:
            expected = image.crop((x-2, y-2, x-2+crop.width, y-2+crop.height))
            self.assertTrue(np.array_equal(np.asarray(crop), np.asarray(expected)))
            self.assertTrue(crop.info['recovered_plate'])
        self.assertEqual(image.tobytes(), before)
        self.assertTrue(quick_check(image))
        self.assertGreaterEqual(len(Vision.boxes(None, image, cropped=True)), 3)

    def test_text_without_plate_edges_is_not_recovered(self):
        self.assertEqual(recover(scene(plates=False)), [])

    def test_blank_colored_glow_is_not_recovered(self):
        for color in ('white', 'red', 'purple', (135,65,55)):
            with self.subTest(color=color):
                self.assertEqual(recover(Image.new('RGB', (600,400), color)), [])

    def test_one_rectangle_is_insufficient_for_extra_route(self):
        image = scene()
        image.paste((230,110,95), (0,155,600,400))
        self.assertEqual(recover(image), [])
