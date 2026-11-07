"""Local transcription, transparent candidate ranking, and clip rendering."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import uuid


class Cancelled(Exception):
    pass


def ffmpeg_path():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_media(args, cwd=None, cancel=None):
    """No shell interpolation. Drain stderr while supporting cancellation."""
    command = [ffmpeg_path(), '-hide_banner', '-nostdin', '-y', *map(str, args)]
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8',
                               errors='replace', creationflags=0x08000000 if os.name == 'nt' else 0)
    errors = []
    def read_errors():
        for line in process.stderr:
            errors.append(line)
            if len(errors) > 120:
                del errors[:60]
    reader = threading.Thread(target=read_errors, daemon=True)
    reader.start()
    while process.poll() is None:
        if cancel and cancel.wait(.15):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            reader.join()
            process.stderr.close()
            raise Cancelled('Cancelled. Completed clips remain in the output folder.')
        if not cancel:
            threading.Event().wait(.15)
    reader.join()
    process.stderr.close()
    if process.returncode:
        raise RuntimeError(f'FFmpeg could not process this video (exit {process.returncode}):\n' + ''.join(errors[-15:]))


def validate_segments(segments):
    clean = []
    previous_start = -1.0
    for segment in segments:
        start, end = float(segment['start']), float(segment['end'])
        text = str(segment['text']).strip()
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError('Transcript timestamps must be finite, positive intervals.')
        if start < previous_start:
            raise ValueError('Transcript must be ordered by start time.')
        previous_start = start
        if text:
            item = {'start': start, 'end': end, 'text': text}
            if 'words' in segment:
                item['words'] = segment['words']
            clean.append(item)
    return clean


def rank_candidates(segments, target=35, count=3):
    """Heuristic ranking of AI transcripts, not a virality prediction model."""
    segments = validate_segments(segments)
    if not 10 <= target <= 90 or not 1 <= count <= 10:
        raise ValueError('Clip length must be 10–90 seconds and count 1–10.')
    if not segments:
        return []
    candidates = []
    cues = {'wait', 'watch', 'wow', 'why', 'how', 'never', 'actually', 'insane',
            'finally', 'mistake', 'secret', 'unbelievable', 'what', 'remember'}
    recording_end = max(s['end'] for s in segments)
    for index, first in enumerate(segments):
        window = []
        for segment in segments[index:]:
            if segment['start'] - first['start'] >= target:
                break
            if window and segment['end'] - first['start'] > target:
                break
            window.append(segment)
        if not window:
            continue
        start = max(0, first['start'] - .6)
        end = min(recording_end, window[-1]['end'] + .5)
        duration = end - start
        if duration < min(8, target * .5):
            continue
        text = ' '.join(s['text'] for s in window)
        words = re.findall(r"[\w']+", text.lower())
        speech = sum(min(s['end'], end) - max(s['start'], start) for s in window)
        coverage = min(1, speech / duration)
        cue_count = len(set(words) & cues)
        score = coverage * 3 + min(len(words) / duration, 3) + min(cue_count, 4) * .4
        if text.rstrip().endswith(('.', '!', '?')):
            score += .5
        score -= abs(duration - target) / target
        reasons = [f'{coverage:.0%} speech coverage', f'{len(words)} spoken words']
        if cue_count:
            reasons.append(f'{cue_count} conversational hook cue(s)')
        candidates.append({'start': round(start, 3), 'end': round(end, 3),
                           'score': round(score, 3), 'text': text,
                           'reason': '; '.join(reasons)})
    selected = []
    for candidate in sorted(candidates, key=lambda c: (-c['score'], c['start'])):
        if all(candidate['end'] <= chosen['start'] or candidate['start'] >= chosen['end']
               for chosen in selected):
            selected.append(candidate)
            if len(selected) == count:
                break
    return selected


def srt_timestamp(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'


def make_srt(segments, start, end):
    blocks = []
    for segment in segments:
        left, right = max(start, segment['start']), min(end, segment['end'])
        if right <= left:
            continue
        # Remove subtitle markup and split long ASR segments into readable chunks.
        words = re.sub(r'<[^>]*>|\{[^}]*\}', '', segment['text']).split()
        chunks = [' '.join(words[i:i + 9]) for i in range(0, len(words), 9)]
        for index, text in enumerate(chunks):
            a = left - start + (right - left) * index / len(chunks)
            b = left - start + (right - left) * (index + 1) / len(chunks)
            blocks.append(f'{len(blocks)+1}\n{srt_timestamp(a)} --> {srt_timestamp(b)}\n{text}\n')
    return '\n'.join(blocks)


def make_animated_ass(segments, start, end):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00170E18,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,42,42,245,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    palette = ('55E7FF', 'FF77DE', '91FBA8', 'FFC65D')
    lines = []

    def timestamp(ticks):
        minutes, rest = divmod(ticks, 6000)
        hours, minutes = divmod(minutes, 60)
        seconds, hundredths = divmod(rest, 100)
        return f'{hours}:{minutes:02}:{seconds:02}.{hundredths:02}'

    timings = []
    for segment in segments:
        words = segment.get('words')
        if not words:
            tokens = segment['text'].split()
            step = (segment['end'] - segment['start']) / max(len(tokens), 1)
            words = [{'start': segment['start'] + i * step,
                      'end': segment['start'] + (i + 1) * step, 'text': token}
                     for i, token in enumerate(tokens)]
        for word in words:
            left, right = float(word['start']), float(word['end'])
            if not math.isfinite(left) or not math.isfinite(right):
                continue
            left, right = max(start, left), min(end, right)
            text = re.sub(r'<[^>]*>|\{[^}]*\}', '', str(word['text'])).strip()
            text = text.replace('\\', '＼').replace('{', '｛').replace('}', '｝')
            text = ' '.join(text.split())
            if text and right > left:
                timings.append((left, right, text))

    timings.sort(key=lambda word: word[0])
    for i, (left, right, text) in enumerate(timings):
        if i + 1 < len(timings):
            right = min(right, timings[i + 1][0])
        a, b = round((left - start) * 100), round((right - start) * 100)
        if b <= a:
            continue
        red, green, blue = (palette[i % len(palette)][j:j + 2] for j in (0, 2, 4))
        peak = min(45, (b - a) * 3)
        settle = min(145, (b - a) * 10)
        style = (r'{\1c&H' + blue + green + red + r'&\fscx85\fscy85'
                 + rf'\t(0,{peak},\fscx116\fscy116)\t({peak},{settle},\fscx100\fscy100)' + '}')
        lines.append(f'Dialogue: 0,{timestamp(a)},{timestamp(b)},Pop,,0,0,0,,{style}{text}')
    return header + '\n'.join(lines) + '\n'


def render_clip(source, destination, candidate, segments, vertical=True,
                captions=True, encoder='libx264', cancel=None, gpu_index=0):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    subtitle = destination.with_suffix('.srt')
    subtitle.write_text(make_srt(segments, candidate['start'], candidate['end']), encoding='utf-8')
    filters = []
    if vertical:
        filters.append('scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1')
    else:
        filters.append('scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1')
    if captions:
        animated = destination.with_suffix('.ass')
        animated.write_text(make_animated_ass(segments, candidate['start'], candidate['end']), encoding='utf-8')
        filters.append(f"ass={animated.name}")
    partial = destination.with_name(destination.stem + '.partial.mp4')
    args = ['-filter_threads', '2', '-threads', '4', '-ss', candidate['start'], '-i', Path(source).resolve(),
            '-t', candidate['end'] - candidate['start'], '-map', '0:v:0',
            '-map', '0:a:0?', '-vf', ','.join(filters), '-c:v', encoder, '-threads', '4']
    if encoder == 'libx264':
        args += ['-preset', 'veryfast', '-crf', '22']
    else:
        args += ['-gpu', str(gpu_index), '-preset', 'p4', '-cq', '23']
    args += ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
             '-movflags', '+faststart', '-avoid_negative_ts', 'make_zero', partial]
    try:
        run_media(args, cwd=destination.parent, cancel=cancel)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def transcribe(source, model_name, device, log, cancel, gpu_index=0):
    from faster_whisper import WhisperModel
    if cancel.is_set():
        raise Cancelled('Cancelled.')
    compute = 'int8' if device == 'cpu' else 'int8_float16'
    log(f'Loading {model_name} on {device}:{gpu_index}. First use downloads the model; this may take several minutes.')
    model = WhisperModel(model_name, device=device, device_index=gpu_index, compute_type=compute)
    stream, info = model.transcribe(str(source), beam_size=3, vad_filter=True, word_timestamps=True)
    log(f'Transcribing audio ({info.language}); loading and decoding can take time on CPU.')
    segments = []
    for segment in stream:
        if cancel.is_set():
            raise Cancelled('Cancelled after current transcription segment.')
        segments.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip(),
                         'words': [{'start': word.start, 'end': word.end, 'text': word.word}
                                   for word in segment.words or []]})
        log(f'Transcribed through {segment.end:.0f}s')
    return validate_segments(segments)


def process_video(source, output_root, *, model='base', device='cpu', count=3,
                  length=35, vertical=True, captions=True, log=print, cancel=None,
                  transcript=None, use_nvenc=False, gpu_index=0):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError('Choose an existing video file.')
    if device not in {'cpu', 'cuda'} or model not in {'tiny', 'base', 'small'}:
        raise ValueError('Unsupported model or processing device.')
    if not 10 <= length <= 90 or not 1 <= count <= 10:
        raise ValueError('Clip length must be 10–90 seconds and count 1–10.')
    if not isinstance(gpu_index, int) or gpu_index < 0:
        raise ValueError('GPU index must be a non-negative integer.')
    cancel = cancel or threading.Event()
    folder = Path(output_root).resolve() / ('job-' + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    log('Output: ' + str(folder))
    segments = validate_segments(transcript) if transcript is not None else transcribe(source, model, device, log, cancel, gpu_index)
    (folder / 'transcript.json').write_text(json.dumps(segments, indent=2, ensure_ascii=False), encoding='utf-8')
    candidates = rank_candidates(segments, length, count)
    if not candidates:
        raise ValueError('Not enough recognized speech to make a clip. Try a longer recording or another model.')
    results = []
    for index, candidate in enumerate(candidates, 1):
        if cancel.is_set():
            raise Cancelled('Cancelled. Completed clips remain in ' + str(folder))
        destination = folder / f'clip-{index:02}.mp4'
        log(f'Rendering clip {index}/{len(candidates)} ({candidate["start"]:.1f}–{candidate["end"]:.1f}s)')
        encoder = 'h264_nvenc' if use_nvenc else 'libx264'
        render_clip(source, destination, candidate, segments, vertical, captions, encoder, cancel, gpu_index)
        results.append({**candidate, 'file': str(destination), 'captions': str(destination.with_suffix('.srt'))})
    report = {'version': 1, 'source': str(source), 'output': str(folder),
              'selection': 'Transcript heuristics; human review required', 'clips': results}
    (folder / 'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    log(f'Done. {len(results)} clip(s) ready for review.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ClipForge processing engine')
    parser.add_argument('source')
    parser.add_argument('--output', default='clips')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--model', choices=['tiny', 'base', 'small'], default='base')
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--length', type=int, default=35)
    parser.add_argument('--original-layout', action='store_true')
    parser.add_argument('--no-captions', action='store_true')
    parser.add_argument('--nvenc', action='store_true')
    parser.add_argument('--gpu-index', type=int, default=0)
    args = parser.parse_args()
    process_video(args.source, args.output, model=args.model, device=args.device,
                  count=args.count, length=args.length, vertical=not args.original_layout,
                  captions=not args.no_captions, use_nvenc=args.nvenc, gpu_index=args.gpu_index)
