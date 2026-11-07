import json
from pathlib import Path
import tempfile
import threading
import unittest
import av
from engine import rank_candidates, make_srt, process_video, run_media, Cancelled


class EngineTests(unittest.TestCase):
    def test_nonoverlapping_candidates(self):
        segments = [{'start': i * 3, 'end': i * 3 + 2.8,
                     'text': 'Wait, watch how this actually works!'} for i in range(30)]
        clips = rank_candidates(segments, 20, 3)
        self.assertEqual(len(clips), 3)
        for i, left in enumerate(clips):
            for right in clips[i+1:]:
                self.assertTrue(left['end'] <= right['start'] or right['end'] <= left['start'])

    def test_caption_offsets_and_markup(self):
        srt = make_srt([{'start': 8, 'end': 13, 'text': '<b>Hello</b> {tag} world'}], 10, 12)
        self.assertIn('00:00:00,000 --> 00:00:02,000', srt)
        self.assertIn('Hello world', srt)
        self.assertNotIn('<b>', srt)

    def test_invalid_and_empty_transcript(self):
        self.assertEqual(rank_candidates([], 20, 3), [])
        with self.assertRaises(ValueError):
            rank_candidates([{'start': 5, 'end': 2, 'text': 'bad'}])

    def test_real_vertical_caption_render(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'fixture.mp4'
            run_media(['-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=15',
                       '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000',
                       '-t', '12', '-c:v', 'libx264', '-preset', 'ultrafast',
                       '-c:a', 'aac', source])
            segments = [{'start': i * 2, 'end': i * 2 + 1.9,
                         'text': 'Watch this test clip with readable captions.'} for i in range(6)]
            report = process_video(source, root / 'outputs', count=1, length=10,
                                   transcript=segments, log=lambda _: None)
            path = Path(report['clips'][0]['file'])
            self.assertTrue(path.is_file())
            with av.open(str(path)) as video:
                stream = video.streams.video[0]
                self.assertEqual((stream.width, stream.height), (720, 1280))
                self.assertGreater(len(list(video.decode(video=0))), 20)
            self.assertTrue(path.with_suffix('.srt').is_file())
            saved = json.loads((Path(report['output']) / 'results.json').read_text())
            self.assertEqual(len(saved['clips']), 1)

    def test_cancel_stops_media_process(self):
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(Cancelled):
                run_media(['-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=30',
                           '-t', '600', Path(temporary) / 'cancelled.mp4'], cancel=cancel)


if __name__ == '__main__':
    unittest.main()
