import tempfile
import unittest
from unittest.mock import Mock

import numpy as np
from PIL import Image, ImageDraw

from drop_tool.label_images import text_pixels, split_labels
from drop_tool.tracker import Store
from drop_tool.vision import Vision
from drop_tool.label_detection import recover_rows


def cyan_label(text):
    image = Image.new('RGB', (150,18), (10,10,10))
    draw = ImageDraw.Draw(image)
    draw.point((2,2), fill='white')
    draw.text((10,3), text, fill=(30,190,240))
    return image


class CyanLabelTests(unittest.TestCase):
    def test_cyan_glyphs_are_retained_but_pure_blue_names_are_not(self):
        cyan = Image.new('RGB', (20,14), (30,190,240))
        blue = Image.new('RGB', (20,14), (30,70,240))
        self.assertTrue(text_pixels(cyan,include_cyan=True).all())
        self.assertFalse(text_pixels(blue,include_cyan=True).any())

    def test_different_cyan_names_do_not_share_the_white_artifact_cache_key(self):
        # Both crops contain the same white point. Earlier only that point was
        # kept, so a subsequent different blue item inherited the first name.
        with tempfile.TemporaryDirectory() as folder:
            vision = Vision(Store(folder))
            vision.templates = []
            vision.boxes = lambda image: [image]
            vision.ocr_suggestions = Mock(side_effect=[['青装備A'], ['青装備B']])
            first = vision.analyze(cyan_label('HAMMER'))['labels'][0]
            second = vision.analyze(cyan_label('STAFF'))['labels'][0]
            self.assertNotEqual(first['fingerprint'], second['fingerprint'])
            self.assertEqual(second['name'], '青装備B')
            self.assertEqual(vision.ocr_suggestions.call_count, 2)

    def test_adjacent_cyan_plates_split_without_changing_pixels(self):
        image = Image.new('RGB', (84,14), 'black')
        draw = ImageDraw.Draw(image)
        for left in (2,44):
            for x in range(left,left+30,5):
                draw.rectangle((x,3,x+2,10), fill=(30,190,240))
        draw.rectangle((36,0,39,13), fill=(120,100,100))
        parts = split_labels(image)
        self.assertEqual(len(parts), 2)
        np.testing.assert_array_equal(np.concatenate([np.asarray(p) for p in parts],axis=1),
                                      np.asarray(image))

    def test_long_cyan_row_crossing_a_bright_beam_is_complete(self):
        image = Image.new('RGB',(600,300),(100,80,70))
        draw = ImageDraw.Draw(image)
        for y in (100,125,150):
            draw.rectangle((95,y-3,355,y+12),fill=(10,10,10))
            draw.rectangle((155,y-3,265,y+12),fill=(115,115,115))
            for x in range(100,350,8):
                draw.rectangle((x,y,x+4,y+9),fill=(30,190,240))
        rows = recover_rows(image)
        for y in (100,125,150):
            self.assertTrue(any(ry==y and x<=100 and x+w>=345 for x,ry,w,h in rows))

    def test_white_prefix_is_recovered_from_its_connected_text_row(self):
        image = Image.new('RGB',(600,300),(100,80,70))
        draw = ImageDraw.Draw(image)
        for y in (100,125,150):
            draw.rectangle((95,y-3,305,y+12),fill=(10,10,10))
            draw.rectangle((95,y-3,130,y+12),fill=(120,60,60))
            for x in range(100,300,8):
                draw.rectangle((x,y,x+4,y+9),fill='white')
        rows = recover_rows(image)
        for y in (100,125,150):
            self.assertTrue(any(ry==y and x<=100 and x+w>=295 for x,ry,w,h in rows))
