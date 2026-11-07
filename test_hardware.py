from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
from hardware import parse_gpu_csv
from engine import render_clip, transcribe


class HardwareTests(unittest.TestCase):
    def test_multiple_cards_keep_driver_indices(self):
        devices = parse_gpu_csv('0, NVIDIA RTX A2000, 6144, GPU-one\n2, NVIDIA RTX 3090, 24576, GPU-two\n')
        self.assertEqual([gpu['index'] for gpu in devices], [0, 2])
        self.assertEqual(devices[0]['memory_mib'], 6144)

    def test_malformed_driver_output(self):
        self.assertEqual(parse_gpu_csv('not a device\n0, Unknown, N/A, id\n'), [])

    def test_nvenc_uses_selected_card(self):
        calls = []
        def media(args, **_kwargs):
            calls.append(args)
            Path(args[-1]).write_bytes(b'fixture')
        with tempfile.TemporaryDirectory() as temporary:
            with patch('engine.run_media', media):
                render_clip('source.mp4', Path(temporary) / 'clip.mp4',
                            {'start': 0, 'end': 10}, [], encoder='h264_nvenc', gpu_index=2)
            args = calls[0]
            self.assertEqual(args[args.index('-gpu') + 1], '2')

    def test_transcription_uses_selected_card(self):
        with patch('faster_whisper.WhisperModel') as model:
            model.return_value.transcribe.return_value = (iter([]), SimpleNamespace(language='en'))
            transcribe('source.mp4', 'tiny', 'cuda', lambda _: None, threading.Event(), gpu_index=2)
            self.assertEqual(model.call_args.kwargs['device_index'], 2)
            self.assertEqual(model.call_args.kwargs['device'], 'cuda')


if __name__ == '__main__':
    unittest.main()
