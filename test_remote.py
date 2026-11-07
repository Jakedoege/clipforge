import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import worker
from remote import remote_process


class WorkerTests(unittest.TestCase):
    def test_auth_upload_status_and_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            worker.ROOT = Path(temporary) / 'worker'
            worker.TOKEN = 'test-secret-' + 'x' * 32
            worker.JOBS.clear()
            worker.DEVICE = 'cpu'
            def process(source, folder, **settings):
                output = folder / 'completed'
                output.mkdir()
                (output / 'clip-01.mp4').write_bytes(b'protocol-test-placeholder')
                (output / 'clip-01.srt').write_text('captions')
                return {'output': str(output), 'source': str(source),
                        'clips': [{'file': str(output / 'clip-01.mp4'),
                                   'captions': str(output / 'clip-01.srt')}]}
            server = worker.ThreadingHTTPServer(('127.0.0.1', 0), worker.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_address[1]}'
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(url + '/health')
                self.assertEqual(error.exception.code, 401)
                source = Path(temporary) / 'source.mp4'
                source.write_bytes(b'upload-fixture')
                with patch.object(worker, 'process_video', process):
                    result = remote_process(source, Path(temporary) / 'desktop', url, worker.TOKEN,
                                            model='tiny', count=1, length=10, vertical=True,
                                            captions=True, use_nvenc=False, log=lambda _: None,
                                            cancel=threading.Event())
                self.assertTrue(Path(result['clips'][0]['file']).is_file())
                self.assertEqual(Path(result['clips'][0]['file']).read_bytes(), b'protocol-test-placeholder')
                self.assertFalse(list(worker.ROOT.glob('*/source.media')))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_reject_plaintext_remote(self):
        with self.assertRaises(ValueError):
            remote_process('unused', 'unused', 'http://192.0.2.1:8765', 'token',
                           model='tiny', count=1, length=10, vertical=True, captions=True,
                           use_nvenc=False, log=print, cancel=threading.Event())


if __name__ == '__main__':
    unittest.main()
