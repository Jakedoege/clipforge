"""Discover NVIDIA devices through the installed driver, without CUDA initialization."""
import csv
import io
import os
from pathlib import Path
import shutil
import subprocess


def detect_gpus():
    executable = shutil.which('nvidia-smi')
    if not executable and os.name == 'nt':
        candidate = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'nvidia-smi.exe'
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        return []
    try:
        result = subprocess.run([executable,
                                 '--query-gpu=index,name,memory.total,uuid',
                                 '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=8,
                                creationflags=0x08000000 if os.name == 'nt' else 0,
                                check=True)
        return parse_gpu_csv(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def parse_gpu_csv(text):
    devices = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 4:
            continue
        index, name, memory, uuid = (value.strip() for value in row)
        try:
            index, memory = int(index), int(memory)
        except ValueError:
            continue
        if index < 0 or memory <= 0:
            continue
        devices.append({'index': index, 'name': name, 'memory_mib': memory, 'uuid': uuid})
    return devices
