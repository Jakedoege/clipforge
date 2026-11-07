# ClipForge 0.1.0

ClipForge turns local recordings and supported livestreams into short MP4 clips on Windows. It uses Whisper to transcribe speech, ranks candidate moments, and renders clips with a vertical crop and animated word-by-word captions. Review clips in the app, export the ones you want, and send rejected local MP4s to the Windows Recycle Bin.

**Status:** Early preview. Twitch was tested from capture through GPU transcription and export. YouTube Live capture was verified separately. Kick URLs are recognized, and live Kick playback still needs end-to-end testing.

## Get started

Run from source on Windows with Python 3.12 and Tk. An internet connection is needed to install dependencies, download the transcription model on first use, and capture live streams.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

- **Recording:** Browse for a local video, choose an output folder, and click **Generate clips**.
- **Live URL:** Paste a Twitch or Kick channel URL or a YouTube Live broadcast URL. A valid paste starts capture after processor detection. The first batch takes about 90 seconds to capture, plus processing time. Use **Stop live** to end the session.
- **Review:** Double-click a clip to preview it. **Save selected clip** copies the MP4 to a location you choose. **Reject selected clip** moves the local MP4 to the Recycle Bin. Previously exported copies and copies on a remote worker are managed separately.

Vertical center crop and animated captions are enabled by default. Choose original layout when the crop would cut off important content. SRT files and JSON transcripts are available in the output folder.

## Processing options

CPU mode works without an NVIDIA GPU. Local CUDA transcription requires a compatible NVIDIA driver and CUDA/cuDNN libraries. GPU detection lists devices and VRAM. Use a short recording to verify the selected GPU before processing a longer stream. NVENC is a separate option for hardware video encoding and requires an FFmpeg build with working NVENC support.

For GPU processing on another machine, see [Remote worker setup](WORKER-SETUP.md). Direct launch uses local processing by default.

## Usage and limitations

- **Content and permissions.** Use media you own or are authorized to capture, edit, and share. Public availability alone does not grant permission to redistribute a stream. Follow the platform rules and any conditions set by the creator. ClipForge is an independent project and is not affiliated with Twitch, Kick, or YouTube.
- **Review before sharing.** Clip selection uses speech coverage, speaking density, and conversational cues. It can miss key moments, pick weak highlights, or produce no clips when speech is sparse. Captions, timing, and framing can be inaccurate. The app does not automatically post clips.
- **Live availability.** Capture depends on the stream being accessible and on the platform and Streamlink continuing to work together. A slow processor can fall behind. ClipForge keeps up to three pending batches and drops the oldest pending batch when that queue fills.
- **Data handling.** Local clips and transcripts are saved to your chosen output folder. When remote mode is enabled, the selected recording or live batch is uploaded to your configured worker. Remote results can remain on the worker after local cancellation or rejection. Run the preview worker on a trusted machine through an SSH tunnel.
- **Preview software.** Expect rough edges and keep the original recordings. ClipForge is provided as-is, without warranties or guarantees of accuracy, compatibility, availability, or uninterrupted capture.

## Build and test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe build_windows.py
```

A local Windows build places the executable in `dist/ClipForge`. Keep the `_internal` and `ClipForgeStream` folders beside `ClipForge.exe`.

Third-party components and model weights have their own license terms. Version 0.1.0 is planned as a source release while notices and corresponding-source requirements for the bundled Windows dependencies are reviewed.
