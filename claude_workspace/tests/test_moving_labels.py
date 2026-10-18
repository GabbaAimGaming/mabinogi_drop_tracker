import unittest
from drop_tool.tracker import consensus

def reading(*rows):
    return {'labels': [{'name': name, 'pos': pos} for name, pos in rows]}

class MovingLabelTests(unittest.TestCase):
    def test_orb_eight_pixels_and_neighbor(self):
        orb = 'ペルシウスアークトゥルスオーブ'
        a = reading((orb, (477, 385, 173)), ('炎の糸', (507, 513, 35)))
        b = reading((orb, (485, 390, 168)), ('炎の糸', (507, 513, 35)))
        self.assertEqual([x['name'] for x in consensus([a,b])['labels']], [orb,'炎の糸'])

    def test_different_names_eight_pixels_apart_do_not_merge(self):
        self.assertIsNone(consensus([reading(('A',(20,20,60))),reading(('B',(28,20,60)))]))

    def test_same_frame_duplicates_cannot_vote_twice(self):
        a=reading(('A',(20,20,60)),('A',(24,20,60)))
        b=reading(('A',(22,20,60)))
        self.assertEqual(len(consensus([a,b])['labels']),1)

    def test_two_matching_items_keep_separate_rows(self):
        a=reading(('A',(20,20,60)),('A',(38,20,60)))
        b=reading(('A',(28,20,60)),('A',(46,20,60)))
        self.assertEqual(len(consensus([a,b])['labels']),2)

    def test_far_or_horizontal_move_is_not_the_same_label(self):
        for pos in [(40,20,60),(28,100,60)]:
            self.assertIsNone(consensus([reading(('A',(20,20,60))),reading(('A',pos))]))

    def test_existing_typo_vote_still_works(self):
        result=consensus([reading(('A',(20,20,60))),reading(('B',(22,20,60))),reading(('A',(23,20,60)))])
        self.assertEqual(result['labels'][0]['name'],'A')
