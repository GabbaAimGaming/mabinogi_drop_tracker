import unittest
from drop_tool.hud_text import is_hud_text

class HudTextTests(unittest.TestCase):
    def test_percentages_and_clock_only(self):
        for text in ['100%','100%100%100%100%','３４％','0.97%','午前 2:50','12:34:56']:
            self.assertTrue(is_hud_text(text),text)

    def test_item_names_quantities_and_uncertain_numbers_are_kept(self):
        for text in ['6段階青い改造石','スピリットジェム(100)','フィニージェム:ゴースト','金貨(100)','100','2','炎の糸','101%','25:90']:
            self.assertFalse(is_hud_text(text),text)
