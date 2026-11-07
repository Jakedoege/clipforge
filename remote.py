"""Client for a trusted worker over loopback SSH forwarding or HTTPS."""
import http.client
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit
import uuid
import zipfile


def worker_hardware(url, token):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or parsed.path not in {'', '/'} or parsed.username:
        raise ValueError('Enter an HTTP(S) worker origin without a path or credentials.')
    if parsed.scheme == 'http' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Use HTTPS or a localhost SSH tunnel.')
    connection = (http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection)(parsed.hostname, parsed.port, timeout=10)
    try:
        connection.request('GET', '/health', headers={'Authorization': 'Bearer ' + token})
        response = connection.getresponse()
        data = response.read()
        if response.status != 200:
            raise ValueError(f'Worker hardware query failed (HTTP {response.status}).')
        return json.loads(data)
    finally:
        connection.close()


def remote_process(source, output_root, url, token, *, model, count, length,
                   vertical, captions, use_nvenc, log, cancel, gpu_index=0, **_ignored):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or parsed.path not in {'', '/'} or parsed.username:
        raise ValueError('Worker address must be a plain HTTP(S) origin without a path or credentials.')
    if parsed.scheme == 'http' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Use HTTPS or an SSH tunnel to localhost; plaintext remote uploads are not supported.')
    if not token.strip():
        raise ValueError('Enter the worker token.')
    def connect():
        cls = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
        return cls(parsed.hostname, parsed.port, timeout=120)
    headers = {'Authorization': 'Bearer ' + token}
    def get(path):
        connection = connect()
        try:
            connection.request('GET', path, headers=headers)
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise RuntimeError(f'Worker returned HTTP {response.status}')
            return json.loads(body)
        finally:
            connection.close()
    get('/health')
    source = Path(source)
    log('Uploading recording to your worker. Cancelling locally does not stop a submitted remote job.')
    connection = connect()
    try:
        connection.putrequest('POST', '/jobs')
        upload_headers = {**headers, 'Content-Type': 'application/octet-stream',
                          'Content-Length': str(source.stat().st_size), 'X-Model': model,
                          'X-Clip-Length': str(length), 'X-Clip-Count': str(count),
                          'X-Gpu-Index': str(gpu_index),
                          'X-Vertical': str(int(vertical)), 'X-Captions': str(int(captions)),
                          'X-Nvenc': str(int(use_nvenc))}
        for key, value in upload_headers.items():
            connection.putheader(key, value)
        connection.endheaders()
        with source.open('rb') as handle:
            while block := handle.read(1024 * 1024):
                if cancel.is_set():
                    raise RuntimeError('Upload cancelled.')
                connection.send(block)
        response = connection.getresponse()
        body = response.read()
        if response.status != 202:
            raise RuntimeError(f'Worker rejected upload (HTTP {response.status}). It may be busy.')
        job_id = json.loads(body)['job_id']
    finally:
        connection.close()
    previous = ''
    while True:
        state = get('/jobs/' + job_id)
        if state['message'] != previous:
            log(state['message'])
            previous = state['message']
        if state['status'] == 'error':
            raise RuntimeError(state['message'])
        if state['status'] == 'done':
            break
        if cancel.wait(2):
            raise RuntimeError('Stopped waiting. Remote job continues; its clips remain on the worker.')
    folder = Path(output_root).resolve() / ('remote-' + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    connection = connect()
    try:
        connection.request('GET', f'/jobs/{job_id}/download', headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError('Could not download completed clips.')
        with tempfile.TemporaryFile() as archive:
            shutil.copyfileobj(response, archive)
            archive.seek(0)
            with zipfile.ZipFile(archive) as bundle:
                # Only flat known output files; no ZIP traversal or links.
                for member in bundle.infolist():
                    if Path(member.filename).name != member.filename or member.file_size > 4 * 1024**3:
                        raise ValueError('Invalid worker archive.')
                    bundle.extract(member, folder)
    finally:
        connection.close()
    report = json.loads((folder / 'results.json').read_text(encoding='utf-8'))
    report['output'] = str(folder)
    for clip in report['clips']:
        for key in ['file', 'captions']:
            name = clip[key]
            if Path(name).name != name:
                raise ValueError('Invalid worker file path.')
            clip[key] = str(folder / name)
    return report
