"""Capture a public live stream into completed batches for ClipForge."""
from contextlib import contextmanager
import csv
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

from engine import Cancelled, ffmpeg_path


def live_url(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port:
        raise ValueError('Paste an HTTPS Twitch, Kick, or YouTube Live link.')
    host = (parsed.hostname or '').removeprefix('www.').removeprefix('m.')
    path = parsed.path.strip('/')
    if host in {'twitch.tv', 'kick.com'} and re.fullmatch(r'[A-Za-z0-9_\-]+', path):
        return f'https://{host}/{path}'
    if host == 'youtube.com' and path == 'watch':
        video = parse_qs(parsed.query).get('v', [''])[0]
    elif host == 'youtube.com' and path.startswith('live/'):
        video = path.removeprefix('live/')
    elif host == 'youtu.be':
        video = path
    else:
        video = ''
    if re.fullmatch(r'[A-Za-z0-9_\-]{11}', video):
        return f'https://www.youtube.com/watch?v={video}'
    if host == 'youtube.com' and re.fullmatch(r'@[A-Za-z0-9_.\-]+/live', path):
        return f'https://www.youtube.com/{path}'
    raise ValueError('Use a Twitch or Kick channel link, or a YouTube Live broadcast link.')


def stream_command(url):
    ffmpeg = ffmpeg_path()
    if getattr(sys, 'frozen', False):
        bundled = Path(sys.executable).parent / 'ClipForgeStream' / 'ClipForgeStream.exe'
        executable = str(bundled) if bundled.is_file() else shutil.which('streamlink')
        if not executable:
            raise RuntimeError('Use Start ClipForge Remote.cmd for live capture, or install Streamlink on PATH.')
        command = [executable]
    else:
        command = [sys.executable, '-m', 'streamlink']
    return [*command, '--stdout', '--loglevel', 'warning', '--ffmpeg-ffmpeg', ffmpeg,
            '--stream-timeout', '25', url, '720p,720p60,480p,best']


def stop_process(process):
    if process.poll() is None:
        if os.name == 'nt':
            # Streamlink can start its own browser or FFmpeg process.
            subprocess.run(
                [str(Path(os.environ['SystemRoot']) / 'System32' / 'taskkill.exe'),
                 '/F', '/T', '/PID', str(process.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False,
            )
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@contextmanager
def capture_segments(source_command, folder, *, seconds=90):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (folder / 'source.log').open('wb') as source_log, (folder / 'ffmpeg.log').open('wb') as ffmpeg_log:
        source = subprocess.Popen(source_command, stdout=subprocess.PIPE, stderr=source_log, creationflags=flags)
        try:
            with source.stdout:
                muxer = subprocess.Popen(
                    [ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', 'pipe:0',
                     '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', '-f', 'segment',
                     '-segment_time', str(seconds), '-reset_timestamps', '1',
                     '-segment_list', 'segments.csv', '-segment_list_type', 'csv', 'batch-%06d.mkv'],
                    cwd=folder, stdin=source.stdout, stdout=subprocess.DEVNULL, stderr=ffmpeg_log,
                    creationflags=flags,
                )
            try:
                yield source, muxer
            finally:
                stop_process(source)
                stop_process(muxer)
        finally:
            stop_process(source)


def completed_segments(folder, seen):
    index = folder / 'segments.csv'
    if not index.exists():
        return []
    with index.open(encoding='utf-8', newline='') as handle:
        lines = handle.readlines()
    result = []
    for row in csv.reader(line for line in lines if line.endswith('\n')):
        if len(row) != 3 or row[0] in seen:
            continue
        seen.add(row[0])
        path = folder / row[0]
        result.append((path, float(row[2]) - float(row[1])))
    return result


def watch_capture(url, folder, pending, finished, cancel, log):
    """Keep capturing during inference and cap the queue if inference falls behind."""
    import queue

    seen = set()
    try:
        with capture_segments(stream_command(url), folder) as (source, muxer):
            while True:
                if cancel.is_set():
                    raise Cancelled('Live capture stopped. Completed clips are saved.')
                ended = muxer.poll() is not None
                for path, duration in completed_segments(folder, seen):
                    if duration < 10:
                        path.unlink(missing_ok=True)
                        continue
                    try:
                        pending.put_nowait(path)
                    except queue.Full:
                        try:
                            pending.get_nowait().unlink(missing_ok=True)
                            log('Dropped an older batch because clipping fell behind.')
                        except queue.Empty:
                            pass
                        pending.put_nowait(path)
                if ended:
                    if source.poll() not in (None, 0) or muxer.returncode:
                        detail = (folder / 'source.log').read_text(encoding='utf-8', errors='replace').strip()
                        detail = detail or (folder / 'ffmpeg.log').read_text(encoding='utf-8', errors='replace').strip()
                        raise RuntimeError(detail[-700:] or 'Could not capture the stream. Check that the channel is live.')
                    break
                cancel.wait(0.4)
    except Exception as error:
        finished.put(error)
    else:
        finished.put(None)
