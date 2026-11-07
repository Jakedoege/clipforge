
ClipForge v0.1.0
ClipForge is a Windows app that turns recordings and supported livestreams into vertical MP4 clips with AI speech transcription, clip ranking, and animated captions. Preview clips, save the ones you want, and reject clips you don't.

Status: Early preview. Twitch capture through remote GPU transcription and export has been tested; YouTube Live capture was verified separately. Kick stream capture has not yet been verified end-to-end.

Download for Windows — recommended
Download ClipForge v0.1.0 for Windows (ZIP)

No Python, PowerShell, or developer setup is required for the packaged Windows app.

Download the Windows ZIP above from the GitHub release. Do not select GitHub's automatically generated “Source code (zip)”—that is for developers.
Right-click the downloaded ZIP and select Extract All.
Open the extracted ClipForge folder and double-click ClipForge.exe.
Choose a recording or enter a supported stream URL to start generating clips.
Keep the extracted folder intact. ClipForge.exe requires its companion _internal and ClipForgeStream folders. Do not move the EXE by itself. The AI speech model may download when first used, requiring an internet connection.

CPU processing works without an NVIDIA GPU. Compatible NVIDIA GPUs and optional remote workers can accelerate parts of processing. The maintainer has confirmed the ZIP launches successfully, but broad clean-machine compatibility testing is still pending.

Using ClipForge
Recording: Browse for a local video, choose an output folder, then click Generate clips.
Live URL: Paste a supported Twitch or YouTube Live link; Kick URLs are recognized but Kick playback is not yet verified. Capture begins after processor detection. The first batch takes roughly 90 seconds to capture plus additional processing time. Click Stop live to finish.
Review: Double-click a clip to preview it. Save selected clip exports a copy. Reject selected clip moves the local MP4 to the Windows Recycle Bin. Previously exported copies and copies on remote workers are separate.
ClipForge uses a vertical center crop and animated captions by default. Choose original layout if the crop removes important content. SRT subtitles and transcript/result JSON files are saved to the output folder.

Processing options
CPU processing is available without an NVIDIA GPU. Local CUDA transcription requires compatible NVIDIA drivers and CUDA/cuDNN libraries. GPU discovery displays device choices and VRAM; test with a short recording before processing long streams. NVENC encoding requires a compatible FFmpeg build.

For optional remote GPU processing, see Remote worker setup. Launching ClipForge normally uses local processing.

Limitations and responsible use
Permissions: Only capture, edit, or redistribute content you own or are authorized to use. A publicly viewable stream is not automatically licensed for redistribution. Follow platform and creator rules. ClipForge is not affiliated with Twitch, Kick, or YouTube.
Clip selection: Ranking is heuristic-based over AI-generated speech transcripts, not a trained virality predictor. Clips, captions, timestamps, and framing need review. Automatic social publishing is not implemented.
Livestreams: Capture depends on stream availability and third-party Streamlink compatibility. Up to three pending batches are queued; older pending batches may be dropped when processing cannot keep up.
Data: Local outputs are saved in your selected folder. Remote mode uploads video batches to the configured worker, where output files can persist after local cancellation or rejection. Use the preview worker only through a trusted SSH tunnel.
Preview quality: This is early software. Keep originals and expect bugs. The application is provided as-is, without guarantees of accuracy, compatibility, or uninterrupted service.
Run from source — developers only
The Windows ZIP above does not require any of these commands. To run from the repository source, install Python 3.12 (64-bit, including Tkinter) and open PowerShell in the extracted directory containing app.py and requirements.txt:

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
If the first command reports that Python 3.12 isn't installed, install it from python.org. Internet access is needed for dependencies and the first model download.

Build and test — developers only
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe build_windows.py
The Windows build outputs dist/ClipForge. Distribute the entire folder, preserving ClipForge.exe, _internal, and ClipForgeStream.

Third-party packages, model weights, and bundled FFmpeg distributions have separate license terms. Applicable attribution, notices, corresponding-source, and other redistribution requirements must be reviewed for publicly distributed binaries.

