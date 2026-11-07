"""ClipForge Windows desktop prototype. Background processing keeps UI responsive."""
import os
import argparse
import json
import traceback
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from send2trash import send2trash
from engine import process_video, Cancelled
from remote import remote_process, worker_hardware
from hardware import detect_gpus
from live import live_url, watch_capture

BG = '#10141f'
PANEL = '#1b2333'
TEXT = '#e9edf5'
MUTED = '#aab8d0'


class ClipForge(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ClipForge • Local clipping studio')
        self.geometry('1080x860')
        self.minsize(900, 800)
        self.configure(bg=BG)
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self.result = None
        self.clip_rows = {}
        self.next_clip_number = 1
        self.pending_live_start = False
        self.source = tk.StringVar()
        self.stream_url = tk.StringVar()
        self.output = tk.StringVar(value=str(Path.home() / 'Videos' / 'ClipForge'))
        self.model = tk.StringVar(value='base')
        self.device = tk.StringVar(value='CPU')
        self.gpu_choices = {'CPU': {'device': 'cpu', 'gpu_index': 0}}
        self.gpu_scan_generation = 0
        self.gpu_scan_complete = False
        self.gpu_scope_remote = False
        self.count = tk.IntVar(value=3)
        self.length = tk.IntVar(value=35)
        self.vertical = tk.BooleanVar(value=True)
        self.captions = tk.BooleanVar(value=True)
        self.nvenc = tk.BooleanVar(value=False)
        worker_token = os.environ.pop('CLIPFORGE_WORKER_TOKEN', '')
        self.remote_enabled = tk.BooleanVar(value=bool(worker_token))
        self.worker_url = tk.StringVar(value=os.environ.pop('CLIPFORGE_WORKER_URL', 'http://127.0.0.1:8765'))
        self.worker_token = tk.StringVar(value=worker_token)
        self.status = tk.StringVar(value='Ready • Choose a recording to begin')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT)
        style.configure('TCombobox', fieldbackground=PANEL, foreground=TEXT, arrowcolor=TEXT)
        style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', TEXT)], selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', TEXT)])
        style.configure('TSpinbox', fieldbackground=PANEL, foreground=TEXT, arrowcolor=TEXT)
        style.configure('TProgressbar', background='#7776f2', troughcolor=PANEL)
        style.configure('TButton', background=PANEL, padding=9)
        style.configure('Accent.TButton', background='#6665e8', foreground='white')
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=35)
        style.configure('Treeview.Heading', background=PANEL, foreground=TEXT)
        main = ttk.Frame(self, padding=25)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='CLIPFORGE', font=('Segoe UI', 26, 'bold')).pack(anchor='w')
        ttk.Label(main, text='Turn long recordings into reviewable highlights.', foreground=MUTED).pack(anchor='w', pady=(2, 18))
        self.file_row(main, 'Recording', self.source, self.choose_source)
        live_entry = self.file_row(main, 'Live URL', self.stream_url, None)
        live_entry.bind('<<Paste>>', lambda _: self.after_idle(self.start_pasted_stream))
        live_entry.bind('<Return>', lambda _: self.start_pasted_stream())
        live_entry.focus_set()
        self.file_row(main, 'Save clips to', self.output, self.choose_output)
        worker = ttk.Frame(main)
        worker.pack(fill='x', pady=6)
        ttk.Checkbutton(worker, text='Use remote worker', variable=self.remote_enabled, command=self.refresh_devices).pack(side='left')
        ttk.Entry(worker, textvariable=self.worker_url, width=29).pack(side='left', padx=8)
        ttk.Label(worker, text='Token').pack(side='left')
        ttk.Entry(worker, textvariable=self.worker_token, show='*', width=25).pack(side='left', padx=8)
        options = ttk.Frame(main)
        options.pack(fill='x', pady=12)
        ttk.Label(options, text='Model').pack(side='left', padx=(0, 7))
        ttk.Combobox(options, textvariable=self.model, values=['tiny', 'base', 'small'], state='readonly', width=7).pack(side='left', padx=(0, 15))
        ttk.Label(options, text='Processor').pack(side='left', padx=(0, 7))
        self.processor_box = ttk.Combobox(options, textvariable=self.device, values=['CPU'], state='readonly', width=32)
        self.processor_box.pack(side='left', padx=(0, 8))
        ttk.Button(options, text='Detect GPUs', command=self.refresh_devices).pack(side='left', padx=(0, 15))
        ttk.Label(options, text='Clips').pack(side='left', padx=(0, 7))
        ttk.Spinbox(options, from_=1, to=10, textvariable=self.count, width=4).pack(side='left', padx=(0, 18))
        ttk.Label(options, text='Seconds').pack(side='left', padx=(0, 7))
        ttk.Spinbox(options, from_=10, to=90, textvariable=self.length, width=5).pack(side='left')
        switches = ttk.Frame(main)
        switches.pack(fill='x', pady=(0, 12))
        for label, variable in [('Vertical 9:16 (center crop)', self.vertical), ('Burn in captions', self.captions), ('NVIDIA video encoding', self.nvenc)]:
            ttk.Checkbutton(switches, text=label, variable=variable).pack(side='left', padx=(0, 20))
        buttons = ttk.Frame(main)
        buttons.pack(fill='x')
        self.start_button = ttk.Button(buttons, text='Generate clips', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left')
        self.live_button = ttk.Button(buttons, text='Start live clipping', command=lambda: self.start(live=True))
        self.live_button.pack(side='left', padx=(10, 0))
        self.cancel_button = ttk.Button(buttons, text='Cancel job', command=self.cancel_job, state='disabled')
        self.cancel_button.pack(side='left', padx=10)
        ttk.Button(buttons, text='Open output folder', command=self.open_output).pack(side='right')
        ttk.Label(main, textvariable=self.status, foreground=MUTED).pack(anchor='w', pady=12)
        self.progress = ttk.Progressbar(main, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 12))
        self.clips = ttk.Treeview(main, columns=('clip', 'range', 'reason'), show='headings', height=5)
        for column, title, width in [('clip', 'Clip', 90), ('range', 'Source range', 150), ('reason', 'Why it was selected', 650)]:
            self.clips.heading(column, text=title)
            self.clips.column(column, width=width)
        self.clips.pack(fill='both', expand=True)
        self.clips.bind('<Double-1>', self.preview)
        review = ttk.Frame(main)
        review.pack(fill='x', pady=(8, 0))
        ttk.Button(review, text='Save selected clip', command=self.save_clip).pack(side='left')
        ttk.Button(review, text='Reject selected clip', command=self.reject_clip).pack(side='left', padx=8)
        ttk.Label(main, text='Double-click a finished clip to play it in your video player. Review before posting.', foreground=MUTED).pack(anchor='w', pady=8)
        self.log = tk.Text(main, height=6, bg=PANEL, fg=MUTED, insertbackground=TEXT, relief='flat', font=('Consolas', 9), state='disabled')
        self.log.pack(fill='x')
        ttk.Label(main, text='Prototype • AI transcription + transparent heuristic ranking • No account connections or automatic posting', foreground=MUTED).pack(anchor='w', pady=(10, 0))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(150, self.consume)
        self.after(400, self.refresh_devices)

    def refresh_devices(self):
        if self.running:
            return
        self.gpu_scan_generation += 1
        generation = self.gpu_scan_generation
        remote = self.remote_enabled.get()
        url, token = self.worker_url.get(), self.worker_token.get()
        self.gpu_scan_complete = False
        self.status.set('Detecting worker GPUs…' if remote else 'Detecting this PC’s NVIDIA GPUs…')
        def scan():
            try:
                hardware = worker_hardware(url, token) if remote else {'gpus': detect_gpus(), 'device': 'local'}
                self.events.put(('hardware', (generation, remote, hardware, None)))
            except Exception as error:
                self.events.put(('hardware', (generation, remote, {}, str(error))))
        threading.Thread(target=scan, daemon=True).start()

    def file_row(self, parent, label, variable, command):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=5)
        ttk.Label(row, text=label, width=13).pack(side='left')
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        if command is not None:
            ttk.Button(row, text='Browse', command=command).pack(side='right')
        return entry

    def choose_source(self):
        path = filedialog.askopenfilename(filetypes=[('Video recordings', '*.mp4 *.mkv *.mov *.webm *.avi'), ('All files', '*.*')])
        if path:
            self.source.set(path)

    def choose_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output.set(path)

    def start_pasted_stream(self):
        if self.running:
            return
        try:
            live_url(self.stream_url.get())
        except ValueError as error:
            self.status.set(str(error))
            return
        if not self.gpu_scan_complete or self.gpu_scope_remote != self.remote_enabled.get():
            self.pending_live_start = True
            self.refresh_devices()
            return
        self.start(live=True)

    def start(self, live=False):
        if self.running:
            return
        try:
            source = live_url(self.stream_url.get()) if live else Path(self.source.get()).expanduser()
            output = Path(self.output.get()).expanduser()
            if not live and not source.is_file():
                raise ValueError('Select a video recording first.')
            if not self.output.get().strip():
                raise ValueError('Choose an output folder.')
            count, length = self.count.get(), self.length.get()
            if not 1 <= count <= 10 or not 10 <= length <= 90:
                raise ValueError('Choose 1–10 clips, each 10–90 seconds long.')
            if not self.gpu_scan_complete or self.gpu_scope_remote != self.remote_enabled.get():
                raise ValueError('Click Detect GPUs and wait for detection to finish before starting.')
            processor = self.gpu_choices.get(self.device.get())
            if processor is None:
                raise ValueError('Select an available processor.')
            options = dict(model=self.model.get(), **processor, count=count,
                           length=length, vertical=self.vertical.get(), captions=self.captions.get(),
                           use_nvenc=self.nvenc.get())
            use_remote = self.remote_enabled.get()
            worker_url, worker_token = self.worker_url.get(), self.worker_token.get()
        except (ValueError, tk.TclError) as error:
            messagebox.showerror('Check your settings', str(error))
            return
        self.result = None
        self.clip_rows.clear()
        self.next_clip_number = 1
        self.clips.delete(*self.clips.get_children())
        self.running = True
        self.cancel_event.clear()
        self.start_button.configure(state='disabled')
        self.live_button.configure(state='disabled')
        self.cancel_button.configure(state='normal', text='Stop live' if live else 'Cancel job')
        self.progress.start(15)
        self.status.set('Starting processing…')
        def work():
            try:
                function = remote_process if use_remote else process_video
                if use_remote:
                    options.update(url=worker_url, token=worker_token)
                log = lambda message: self.events.put(('log', message))
                if live:
                    self.clip_live(source, output, function, options, log)
                    self.events.put(('live_done', None))
                else:
                    result = function(source, output, **options, cancel=self.cancel_event, log=log)
                    self.events.put(('done', result))
            except Cancelled as error:
                self.events.put(('cancelled', str(error)))
            except Exception as error:
                self.events.put(('cancelled' if live and isinstance(error, RuntimeError)
                                 and str(error).startswith('Stopped waiting.') else 'error', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def clip_live(self, url, output, function, options, log):
        session = output.resolve() / ('live-' + uuid.uuid4().hex[:12])
        pending = queue.Queue(maxsize=3)
        finished = queue.Queue()
        log('Connecting to the live stream. The first batch takes about 90 seconds to capture.')
        with tempfile.TemporaryDirectory(prefix='clipforge-live-') as temp:
            capture = threading.Thread(
                target=watch_capture, args=(url, Path(temp), pending, finished, self.cancel_event, log),
                daemon=True,
            )
            capture.start()
            try:
                while not self.cancel_event.is_set():
                    try:
                        segment = pending.get(timeout=0.4)
                    except queue.Empty:
                        if finished.empty():
                            continue
                        error = finished.get()
                        if error:
                            raise error
                        return
                    batch = int(segment.stem.rsplit('-', 1)[1]) + 1
                    log(f'Processing live batch {batch}…')
                    try:
                        result = function(segment, session, **options, cancel=self.cancel_event, log=log)
                    except (ValueError, RuntimeError) as error:
                        if not str(error).startswith('Not enough recognized speech'):
                            raise
                        log(f'Batch {batch} did not contain enough speech. Capturing continues.')
                    else:
                        self.events.put(('live_batch', (session, batch, result['clips'])))
                    finally:
                        segment.unlink(missing_ok=True)
                raise Cancelled('Live capture stopped. Completed clips are saved.')
            finally:
                self.cancel_event.set()
                capture.join()

    def add_clips(self, clips, batch=None):
        for clip in clips:
            self.result['clips'].append(clip)
            source_range = f'{clip["start"]:.1f}–{clip["end"]:.1f}s'
            if batch is not None:
                source_range = f'Batch {batch} · {source_range}'
            row = self.clips.insert('', 'end',
                                    values=(f'Clip {self.next_clip_number}', source_range, clip['reason']))
            self.clip_rows[row] = clip
            self.next_clip_number += 1

    def consume(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'hardware':
                    generation, remote, hardware, error = data
                    if generation != self.gpu_scan_generation:
                        continue
                    if error:
                        self.pending_live_start = False
                        self.status.set('GPU detection failed: ' + error)
                        continue
                    choices = {}
                    if not remote or hardware.get('device') == 'cpu':
                        choices['CPU (worker)' if remote else 'CPU'] = {'device': 'cpu', 'gpu_index': 0}
                    if not remote or hardware.get('device') == 'cuda':
                        for gpu in hardware.get('gpus', []):
                            label = f"GPU {gpu['index']} • {gpu['name']} • {gpu['memory_mib']/1024:.1f} GB"
                            choices[label] = {'device': 'cuda', 'gpu_index': gpu['index']}
                    self.gpu_choices = choices
                    self.processor_box.configure(values=list(choices))
                    if self.device.get() not in choices:
                        self.device.set(next(iter(choices), 'No supported GPU'))
                    self.gpu_scan_complete = bool(choices)
                    self.gpu_scope_remote = remote
                    self.status.set(f"Detected {len(hardware.get('gpus', []))} NVIDIA GPU(s) on {'worker' if remote else 'this PC'}. GPU detection does not verify CUDA libraries.")
                    if self.pending_live_start:
                        self.pending_live_start = False
                        self.start(live=True)
                elif kind == 'log':
                    self.status.set(data)
                    self.log.configure(state='normal')
                    self.log.insert('end', data + '\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                elif kind == 'live_batch':
                    session, batch, clips = data
                    if self.result is None:
                        self.result = {'output': str(session), 'clips': []}
                    self.add_clips(clips, batch)
                    self.status.set(f'Live capture • {len(self.result["clips"])} clips ready to review')
                else:
                    self.running = False
                    self.start_button.configure(state='normal')
                    self.live_button.configure(state='normal')
                    self.cancel_button.configure(state='disabled', text='Cancel job')
                    self.progress.stop()
                    if kind == 'done':
                        self.result = {**data, 'clips': []}
                        self.add_clips(data['clips'])
                        self.status.set(f'Ready to review • {len(data["clips"])} clips generated')
                    elif kind == 'live_done':
                        total = len(self.result['clips']) if self.result else 0
                        self.status.set(f'Stream ended • {total} clips saved')
                    else:
                        self.status.set('Cancelled' if kind == 'cancelled' else 'Job failed')
                        messagebox.showinfo('Cancelled', data) if kind == 'cancelled' else messagebox.showerror('Processing failed', data)
        except queue.Empty:
            pass
        self.after(150, self.consume)

    def cancel_job(self):
        self.cancel_event.set()
        self.status.set('Cancelling after the current model operation…')

    def preview(self, _event=None):
        selected = self.clips.selection()
        if selected:
            os.startfile(self.clip_rows[selected[0]]['file'])

    def save_clip(self):
        selected = self.clips.selection()
        if not selected:
            self.status.set('Select a clip to save.')
            return
        source = Path(self.clip_rows[selected[0]]['file'])
        destination = filedialog.asksaveasfilename(
            initialfile=source.name, defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4')])
        if destination and Path(destination).resolve() != source.resolve():
            try:
                shutil.copy2(source, destination)
            except OSError as error:
                messagebox.showerror('Could not save clip', str(error))
            else:
                self.status.set('Clip saved.')

    def reject_clip(self):
        selected = self.clips.selection()
        if not selected:
            self.status.set('Select a clip to reject.')
            return
        row = selected[0]
        clip = self.clip_rows[row]
        try:
            send2trash(clip['file'])
        except OSError as error:
            messagebox.showerror('Could not reject clip', str(error))
            return
        self.clips.delete(row)
        del self.clip_rows[row]
        self.result['clips'].remove(clip)
        self.status.set('Clip rejected and moved to the Recycle Bin.')

    def open_output(self):
        path = Path(self.result['output'] if self.result else self.output.get()).expanduser()
        if path.is_dir():
            os.startfile(str(path))
        else:
            messagebox.showinfo('Output folder', 'Generate a clip or choose an existing output folder first.')

    def close(self):
        if self.running:
            messagebox.showinfo('Job running', 'Cancel the current job and wait for it to stop before closing.')
            return
        self.destroy()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-build', metavar='VIDEO')
    parser.add_argument('--output', default='clips')
    args = parser.parse_args()
    if args.verify_build:
        output = Path(args.output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        messages = []
        try:
            result = process_video(args.verify_build, output, model='tiny', count=1,
                                   length=20, log=messages.append)
            payload = {'status': 'passed', 'result': result, 'messages': messages}
        except Exception as error:
            payload = {'status': 'failed', 'error': str(error), 'traceback': traceback.format_exc(), 'messages': messages}
        (output / 'build-verification.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    else:
        ClipForge().mainloop()
