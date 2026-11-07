"""Run in the development venv: python build_windows.py. Requires PyInstaller."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys

import streamlink

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--dist', type=Path, default=root / 'dist')
parser.add_argument('--work', type=Path, default=root / 'build')
options = parser.parse_args()
dist = options.dist.resolve()
work = options.work.resolve()
base = [sys.executable, '-m', 'PyInstaller', '--noconfirm',
        '--distpath', str(dist), '--workpath', str(work), '--specpath', str(work)]
arguments = ['--onedir', '--windowed', '--name', 'ClipForge']
for package in ['faster_whisper', 'ctranslate2', 'onnxruntime', 'tokenizers',
                'av', 'imageio_ffmpeg', 'huggingface_hub']:
    arguments += ['--collect-all', package]
# Some supplied Python runtimes require an extra public certificate data file.
# Preserve it when present; do not modify certificate-validation behavior.
certificate_data = Path(sys.base_prefix) / 'Lib' / 'codex-rejected-cas.pem'
if certificate_data.is_file():
    base += ['--add-data', str(certificate_data) + ';.']
subprocess.run([*base, *arguments, str(root / 'app.py')], check=True)
streamlink_entry = Path(streamlink.__file__).with_name('__main__.py')
subprocess.run([*base, '--onedir', '--console', '--name', 'ClipForgeStream',
                '--collect-all', 'streamlink', '--collect-all', 'streamlink_cli',
                '--copy-metadata', 'streamlink', str(streamlink_entry)], check=True)
shutil.move(dist / 'ClipForgeStream', dist / 'ClipForge' / 'ClipForgeStream')
