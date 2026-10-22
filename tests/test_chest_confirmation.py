"""形だけ・一点だけ・一瞬だけの誤検知で自動読取を始めない。"""
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image

from drop_tool.app import App
from drop_tool.chest_detector import ChestDetector
from drop_tool.reward_gate import ChestConfirmation, RewardGate
from drop_tool import read_worker


def chest(box=(100, 100, 200, 200)):
    return {'found': True, 'match': {'template': 'chest', 'box': list(box)}}


class ConfirmationTests(unittest.TestCase):
    def test_isolated_or_displaced_detection_never_starts_memory(self):
        confirmation = ChestConfirmation(); gate = RewardGate()
        observations = [chest(), {'found': False}, chest((400, 100, 500, 200)),
                        chest(), {'found': False}, {'found': False}]
        for now, detection in enumerate(observations, 1):
            self.assertFalse(gate.observe(confirmation.observe(detection, now), True, now))
        self.assertEqual(gate.chest_until, 0)

    def test_same_box_twice_then_three_seconds_of_alt(self):
        confirmation = ChestConfirmation(); gate = RewardGate()
        self.assertFalse(gate.observe(confirmation.observe(chest(), 1), True, 1))
        self.assertFalse(gate.observe(confirmation.observe(chest((105, 95, 205, 195)), 2), True, 2))
        self.assertEqual(gate.chest_until, 10)
        for now in (3, 4):
            self.assertFalse(gate.observe(False, True, now))
        self.assertTrue(gate.observe(False, True, 5))

    def test_repeated_timestamp_gap_and_missing_box_do_not_confirm(self):
        for second, now in ((chest(), 1), (chest(), 6), ({'found': True}, 2),
                            (chest((110, 110, 115, 115)), 2)):
            c = ChestConfirmation(); self.assertFalse(c.observe(chest(), 1))
            self.assertFalse(c.observe(second, now))

    def test_dialog_and_reset_discard_first_unconfirmed_frame(self):
        app = App.__new__(App); app.reward_gate = RewardGate()
        app.chest_detector = Mock(); app.chest_detector.detect.return_value = chest()
        frame = Image.new('RGB', (512, 512))
        self.assertFalse(app.reward_detection(frame, False, 1)['found'])
        app.reward_detection(frame, True, 1.5)
        self.assertFalse(app.reward_detection(frame, False, 2)['found'])
        app.reset_reward()
        self.assertFalse(app.reward_detection(frame, False, 3)['found'])
        self.assertTrue(app.reward_detection(frame, False, 4)['found'])

    def test_stopped_worker_does_not_seed_confirmation_for_next_run(self):
        app = App.__new__(App); app.reward_gate = RewardGate(); app.epoch = 1
        app.chest_detector = Mock()
        def cancelled(frame):
            app.epoch += 1; app.reset_reward()
            return chest()
        app.chest_detector.detect.side_effect = cancelled
        result = app.reward_detection(Image.new('RGB', (512, 512)), False, 1)
        self.assertFalse(result['found'])
        self.assertIsNone(app.chest_confirmation.box)

    def test_sample_keeps_the_frame_that_confirmed_the_chest_without_extra_saved_images(self):
        app = Mock(); app.epoch = 1; app.worker_phase = ''
        evidence = Image.new('RGB', (512, 512), 'red')
        frame = Image.new('RGB', (512, 512), 'blue')
        app.chest_evidence_frame = evidence; app.chest_evidence_scan = chest()
        put = Mock()
        with patch('drop_tool.read_worker.alt_capture.collect', return_value=[frame, frame]), \
                patch('drop_tool.read_worker.alt_capture.read', return_value={'labels': []}):
            read_worker._burst(app, put, frame, [], {}, epoch=1, hwnd=1, center=False)
        result = put.call_args.args[1]
        self.assertIs(result['sample_frames'][0], evidence)
        self.assertIs(result['frame'], frame)  # 読取対象は引き続き報酬の連写画像。
        self.assertEqual(result['chest_evidence'], chest())


class DetectorEvidenceTests(unittest.TestCase):
    def test_dark_shape_alone_is_only_a_search_hint(self):
        d = ChestDetector.__new__(ChestDetector)
        d.fragments = Mock(); d.fragments.detect.return_value = {'found': False}
        d.shape = Mock(); d.shape.detect.return_value = {
            'found': True, 'match': {'template': 'shape-alt', 'box': [100, 100, 200, 200]}}
        d._detect = Mock(return_value={'found': False, 'match': None})
        with patch('drop_tool.chest_shape.plate_rows', return_value=[(0, 0, 20, 10)] * 3):
            result = d._near_plates(Image.new('RGB', (512, 512)))
        self.assertFalse(result['found'])
        self.assertEqual(result['search'], 'shape-unconfirmed')

    def detector(self, points, duplicate=False):
        d = ChestDetector.__new__(ChestDetector)
        points = np.float32(points)
        d.templates = [('test', points, np.zeros((len(points), 128), np.float32), np.array([200, 200]))]
        d.sift = Mock(); d.matcher = Mock()
        d.sift.detectAndCompute.return_value = (
            [cv2.KeyPoint(float(x + 100), float(y + 100), 1) for x, y in points],
            np.zeros((len(points), 128), np.float32))
        d.matcher.knnMatch.return_value = [
            (cv2.DMatch(i, 0 if duplicate else i, 1), cv2.DMatch(i, (i+1) % len(points), 10))
            for i in range(len(points))]
        return d

    def test_repeated_matches_to_one_screen_point_cannot_form_a_chest(self):
        d = self.detector([(10,10), (60,10), (110,10), (10,110), (60,110), (110,110)], True)
        with patch('drop_tool.chest_detector.cv2.findHomography') as fit:
            self.assertFalse(d._detect(Image.new('RGB', (512, 512)))['found'])
        fit.assert_not_called()

    def test_thin_support_is_rejected_but_distributed_surface_is_accepted(self):
        matrix = np.array([[1.,0,100], [0,1,100], [0,0,1]])
        for points, expected in (([(x,10) for x in (10,30,50,70,90,110)], False),
                                 ([(10,10), (60,10), (110,10), (10,110), (60,110), (110,110)], True)):
            d = self.detector(points)
            with patch('drop_tool.chest_detector.cv2.findHomography', return_value=(matrix, np.ones((6,1), np.uint8))):
                self.assertEqual(d._detect(Image.new('RGB', (512, 512)))['found'], expected)
