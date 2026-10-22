import unittest
from unittest.mock import Mock
from PIL import Image
from drop_tool.app import App
from drop_tool.reward_gate import RewardGate

class RewardScanReuseTests(unittest.TestCase):
    def app(self):
        app=App.__new__(App);app.reward_gate=RewardGate()
        app.chest_detector=Mock();app.chest_detector.detect.return_value={
            'found':True,'match':{'template':'chest','box':[30,30,70,70]}}
        return app

    def test_remembered_chest_keeps_alt_checks_light_and_still_waits_three_seconds(self):
        app=self.app();frame=Image.new('RGB',(100,100));trigger=[]
        for t in (10.,10.5,11.,11.5,12.,12.5,13.,13.5):
            r=app.reward_detection(frame,False,t)
            trigger.append(app.reward_gate.observe(r['found'],True,t))
        self.assertEqual(app.chest_detector.detect.call_count,2)
        self.assertEqual(trigger,[False]*7+[True])

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
        self.assertEqual(app.chest_detector.detect.call_count,0)
        self.assertEqual(r['search'],'blocked')
        self.assertFalse(g.observe(r['found'],True,10.5,blocked=True))
        self.assertIsNone(g.since)
        self.assertFalse(g.observe(False,False,11.))
        self.assertIsNone(g.since)

    def test_countdown_started_before_expiry_finishes_without_rescanning(self):
        app=self.app();frame=Image.new('RGB',(100,100));g=app.reward_gate
        g.observe(True,False,10.)
        for t in (11.,12.,13.,14.,15.,16.):
            g.observe(False,False,t)
        trigger=[]
        for t in (16.3,17.,17.8,18.5,19.4):
            r=app.reward_detection(frame,False,t)
            trigger.append(g.observe(r['found'],True,t))
        self.assertEqual(trigger,[False]*4+[True])
        app.chest_detector.detect.assert_not_called()
        self.assertEqual(g.chest_until,18.)

    def test_expiry_grace_is_lost_on_alt_release_dialog_or_observation_gap(self):
        for interruption in ('alt','dialog','gap','reset'):
            with self.subTest(interruption=interruption):
                g=RewardGate();g.observe(True,False,10.)
                for t in (12.,14.,16.):g.observe(False,False,t)
                g.observe(False,True,17.)
                if interruption=='alt':g.observe(False,False,18.)
                elif interruption=='dialog':g.observe(False,True,18.,blocked=True)
                elif interruption=='gap':g.observe(False,True,20.)
                else:g.reset()
                self.assertFalse(g.observe(False,True,20.5))
                self.assertFalse(g.has_chest_evidence(20.5))

    def test_alt_beginning_after_expiry_never_reuses_old_chest(self):
        g=RewardGate();g.observe(True,False,10.)
        for t in (12.,14.,16.,18.):g.observe(False,False,t)
        for t in (18.1,19.,20.,21.,22.):
            self.assertFalse(g.observe(False,True,t))
        self.assertIsNone(g.since)
