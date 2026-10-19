import unittest
from unittest.mock import Mock
from PIL import Image
from drop_tool.app import App
from drop_tool.reward_gate import RewardGate

class RewardScanReuseTests(unittest.TestCase):
    def app(self):
        app=App.__new__(App);app.reward_gate=RewardGate()
        app.chest_detector=Mock();app.chest_detector.detect.return_value={'found':True}
        return app

    def test_remembered_chest_keeps_alt_checks_light_and_still_waits_three_seconds(self):
        app=self.app();frame=Image.new('RGB',(100,100));trigger=[]
        for t in (10.,10.5,11.,11.5,12.,12.5,13.):
            r=app.reward_detection(frame,False,t)
            trigger.append(app.reward_gate.observe(r['found'],True,t))
        self.assertEqual(app.chest_detector.detect.call_count,1)
        self.assertEqual(trigger,[False]*6+[True])

    def test_observation_gap_or_expired_memory_requires_new_chest_evidence(self):
        app=self.app();gate=app.reward_gate;frame=Image.new('RGB',(100,100))
        gate.observe(True,True,10.)
        app.reward_detection(frame,False,13.)
        self.assertEqual(app.chest_detector.detect.call_count,1)
        gate.previous=19.5
        app.reward_detection(frame,False,20.)
        self.assertEqual(app.chest_detector.detect.call_count,2)

    def test_near_dialog_and_released_alt_cannot_finish_the_wait(self):
        app=self.app();frame=Image.new('RGB',(100,100));g=app.reward_gate
        g.observe(True,True,10.)
        r=app.reward_detection(frame,True,10.5)
        self.assertEqual(app.chest_detector.detect.call_count,1)
        self.assertFalse(g.observe(r['found'],True,10.5,blocked=True))
        self.assertIsNone(g.since)
        self.assertFalse(g.observe(False,False,11.))
        self.assertIsNone(g.since)
