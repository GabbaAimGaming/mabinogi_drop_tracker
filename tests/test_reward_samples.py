# Gameplay samples stay private; validated separately before publication.
from pathlib import Path as _FixturePath
import unittest as _fixture_unittest
if not (_FixturePath(__file__).resolve().parent / 'fixtures').exists() or not (_FixturePath(__file__).resolve().parents[1] / 'tools/benchmarks/video').exists():
    raise _fixture_unittest.SkipTest('非公開の提出画像で別途検証済み')

"""試験版の取得条件と提出保存を検証。ゲームの実機認識率を保証するテストではない。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile
from PIL import Image
from drop_tool.reward_gate import RewardGate
from drop_tool.sample_reports import SampleReports
from drop_tool.chest_detector import ChestDetector
from drop_tool.tracker import ROOT


class GateTests(unittest.TestCase):
    def test_alt_alone_never_triggers(self):
        gate=RewardGate()
        self.assertFalse(any(gate.observe(False,True,t) for t in range(10)))

    def test_chest_alone_never_triggers(self):
        gate=RewardGate()
        self.assertFalse(any(gate.observe(True,False,t) for t in range(10)))

    def test_three_seconds_and_once_per_run(self):
        gate=RewardGate()
        for t in (1,2,3): self.assertFalse(gate.observe(True,True,t))
        self.assertTrue(gate.observe(True,True,4))
        self.assertFalse(gate.observe(True,True,5))
        gate.reset()
        self.assertFalse(gate.observe(True,True,6))

    def test_alt_interrupt_restarts_three_seconds(self):
        gate=RewardGate()
        for t,alt in ((1,True),(2,True),(3,False),(4,True),(5,True),(6,True)):
            self.assertFalse(gate.observe(True,alt,t))
        self.assertTrue(gate.observe(True,True,7))

    def test_recent_chest_can_be_hidden_by_labels(self):
        gate=RewardGate()
        for t in (1,2,3): self.assertFalse(gate.observe(t==1,True,t))
        self.assertTrue(gate.observe(False,True,4))

    def test_old_chest_and_long_gap_do_not_trigger(self):
        gate=RewardGate()
        gate.observe(True,False,1)
        for t in range(2,12):self.assertFalse(gate.observe(False,t>=9,t))
        gate.reset()
        gate.observe(True,True,1)
        self.assertFalse(gate.observe(True,True,5))
        self.assertEqual(gate.elapsed(5),0)


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.reports=SampleReports(self.temp.name)

    def test_max_three_images_and_metadata(self):
        frames=[Image.new('RGB',(10+i,8)) for i in range(6)]
        folder=self.reports.save('auto_failure',frames,{'reason':'ALTが消えた'})
        report=json.loads((folder/'report.json').read_text('utf-8'))
        self.assertEqual([r['width'] for r in report['images']],[10,13,15])
        self.assertEqual(report['kind'],'auto_failure')
        self.assertEqual(report['reason'],'ALTが消えた')

    def test_zip_only_completed_samples_not_records(self):
        self.reports.save('missed_detection',[Image.new('RGB',(8,8))],{})
        (Path(self.temp.name)/'records.json').write_text('private')
        incomplete=self.reports.folder/'incomplete';incomplete.mkdir()
        (incomplete/'frame-00.png').write_bytes(b'partial')
        target=Path(self.temp.name)/'samples.zip'
        self.assertEqual(self.reports.export(target),1)
        with ZipFile(target) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(len(z.namelist()),2)
            self.assertFalse(any('records' in n or 'incomplete' in n for n in z.namelist()))

    def test_limit_preserves_previous_report(self):
        self.reports.MAX_REPORTS=1
        folder=self.reports.save('auto_success',[],{})
        with self.assertRaisesRegex(OSError,'上限'):self.reports.save('auto_failure',[],{})
        self.assertTrue((folder/'report.json').exists())

    def test_empty_export_is_reported(self):
        with self.assertRaises(ValueError):self.reports.export(Path(self.temp.name)/'empty.zip')


class DetectorTests(unittest.TestCase):
    def test_templates_load_and_blank_frame_is_not_chest(self):
        detector=ChestDetector()
        self.assertGreaterEqual(len(detector.templates),19)
        self.assertFalse(detector.detect(Image.new('RGB',(1280,720),'gray'))['found'])

    def test_known_full_scene_detected(self):
        detector=ChestDetector()
        with Image.open(ROOT/'tests/fixtures/albi-hd-near.png') as image:
            self.assertTrue(detector.detect(image)['found'])


class AppSampleTests(unittest.TestCase):
    def app(self):
        from drop_tool.app import App
        app=App.__new__(App)
        from drop_tool.tracker import Store
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        app.store=Store(temporary.name)
        app.jobs=__import__('queue').Queue();app.epoch=0;app.busy=True
        app.root=Mock();app.status=Mock();app.completion_sound=Mock()
        app.stable=Mock();app.reward_gate=RewardGate();app.watching=True
        app.submit_sample=Mock()
        return app

    def test_error_stops_auto_and_requests_manual(self):
        app=self.app();frame=Image.new('RGB',(20,20))
        app.read_failed('auto',{'sample_frames':[frame]},'品名なし')
        self.assertFalse(app.watching)
        app.completion_sound.play.assert_called_once_with(kind='error')
        self.assertIn('手動読取',app.status.set.call_args.args[0])
        self.assertEqual(app.submit_sample.call_args.args[0],'auto_failure')

    def test_missed_sample_does_not_register_run_or_play_completion(self):
        app=self.app();app.store=Mock();app.jobs.put((0,'missed',{'frame':Image.new('RGB',(20,20))},None))
        app.poll()
        app.store.record.assert_not_called()
        app.completion_sound.play.assert_not_called()
        self.assertEqual(app.submit_sample.call_args.args[0],'missed_detection')

    def test_sample_saved_does_not_unlock_another_worker_and_keeps_error_notice(self):
        app=self.app();app.jobs.put((0,'sample_saved',{'path':'sample','kind':'auto_failure'},None))
        app.poll()
        self.assertTrue(app.busy)
        self.assertIn('手動読取',app.status.set.call_args.args[0])
