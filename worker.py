"""Single-job GPU worker, bound to loopback by default. Use an SSH tunnel."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from engine import process_video
from hardware import detect_gpus

JOBS = {}
LOCK = threading.Lock()
BUSY = threading.Lock()
ROOT = Path('worker-data').resolve()
TOKEN = ''
DEVICE = 'cuda'


class Handler(BaseHTTPRequestHandler):
    def authorized(self):
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
            self.send_error(401)
            return False
        return True

    def json_response(self, status, data):
        content = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if not self.authorized():
            return
        if self.path == '/health':
            self.json_response(200, {'status': 'ready', 'device': DEVICE, 'busy': BUSY.locked(), 'gpus': detect_gpus()})
            return
        match = re.fullmatch(r'/jobs/([a-f0-9]{32})(/download)?', self.path)
        if not match:
            self.send_error(404)
            return
        with LOCK:
            job = dict(JOBS.get(match[1], {}))
        if not job:
            self.send_error(404)
        elif match[2]:
            if job['status'] != 'done':
                self.send_error(409)
                return
            archive = ROOT / match[1] / 'clips.zip'
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Length', str(archive.stat().st_size))
            self.end_headers()
            with archive.open('rb') as handle:
                shutil.copyfileobj(handle, self.wfile)
        else:
            self.json_response(200, job)

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != '/jobs':
            self.send_error(404)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            length = int(self.headers.get('X-Clip-Length', '35'))
            count = int(self.headers.get('X-Clip-Count', '3'))
            model = self.headers.get('X-Model', 'base')
            gpu_index = int(self.headers.get('X-Gpu-Index', '0'))
            if gpu_index < 0:
                raise ValueError('Invalid GPU index')
            if not 0 < size <= 8 * 1024**3 or not 10 <= length <= 90 or not 1 <= count <= 10:
                raise ValueError('Invalid size or settings')
            if model not in {'tiny', 'base', 'small'}:
                raise ValueError('Invalid model')
            if DEVICE == 'cuda' and gpu_index not in {gpu['index'] for gpu in detect_gpus()}:
                raise ValueError('Selected GPU is not available on this worker')
        except ValueError:
            self.send_error(400)
            return
        if not BUSY.acquire(blocking=False):
            self.send_error(409, 'Worker is busy; try again after the current job finishes.')
            return
        job_id = uuid.uuid4().hex
        folder = ROOT / job_id
        source = folder / 'source.media'
        try:
            folder.mkdir(parents=True)
            self.connection.settimeout(120)
            remaining = size
            with source.open('wb') as destination:
                while remaining:
                    block = self.rfile.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('Upload ended early')
                    destination.write(block)
                    remaining -= len(block)
        except Exception:
            BUSY.release()
            source.unlink(missing_ok=True)
            self.send_error(400, 'Upload failed')
            return
        with LOCK:
            JOBS[job_id] = {'status': 'processing', 'message': 'Starting worker'}
        vertical = self.headers.get('X-Vertical', '1') == '1'
        captions = self.headers.get('X-Captions', '1') == '1'
        nvenc = self.headers.get('X-Nvenc', '0') == '1'
        def log(message):
            with LOCK:
                JOBS[job_id]['message'] = message
        def work():
            try:
                report = process_video(source, folder, device=DEVICE, model=model, count=count,
                                       length=length, vertical=vertical, captions=captions,
                                       use_nvenc=nvenc, gpu_index=gpu_index, log=log)
                output = Path(report['output'])
                # Source recording is excluded. Result paths become portable.
                report['source'] = 'Remote recording'
                report['output'] = '.'
                for clip in report['clips']:
                    clip['file'] = Path(clip['file']).name
                    clip['captions'] = Path(clip['captions']).name
                (output / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                shutil.make_archive(str(folder / 'clips'), 'zip', output)
                with LOCK:
                    JOBS[job_id] = {'status': 'done', 'message': 'Clips ready'}
            except Exception as error:
                with LOCK:
                    JOBS[job_id] = {'status': 'error', 'message': str(error)}
            finally:
                source.unlink(missing_ok=True)
                BUSY.release()
        threading.Thread(target=work, daemon=True).start()
        self.json_response(202, {'job_id': job_id})

    def log_message(self, *_args):
        pass  # Do not log authorization headers or uploaded filenames.


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data', default='worker-data')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    args = parser.parse_args()
    TOKEN = os.environ.get('CLIPFORGE_TOKEN', '')
    if len(TOKEN) < 24:
        parser.error('Set CLIPFORGE_TOKEN to a random secret at least 24 characters long.')
    ROOT = Path(args.data).resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    DEVICE = args.device
    print(f'ClipForge worker listening on 127.0.0.1:{args.port}; device={DEVICE}. Use an SSH tunnel.')
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
