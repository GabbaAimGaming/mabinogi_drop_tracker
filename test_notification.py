import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from drop_tool.notification import CompletionSound

class NotificationTests(unittest.TestCase):
    def test_mute_persists_and_preview_works_when_muted(self):
        with tempfile.TemporaryDirectory() as folder:
            sound = CompletionSound(Path(folder))
            self.assertTrue(sound.enabled)
            sound.set_enabled(False)
            sound = CompletionSound(Path(folder))
            self.assertFalse(sound.enabled)
            with patch('drop_tool.notification.winsound.PlaySound') as play:
                sound.play()
                play.assert_not_called()
                sound.play(preview=True)
                play.assert_called_once()
    def test_missing_audio_device_does_not_break_recording(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('drop_tool.notification.winsound.PlaySound', side_effect=RuntimeError):
                CompletionSound(Path(folder)).play()
