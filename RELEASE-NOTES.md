The Windows application is now available as a downloadable ZIP. No separate Python installation is necessary.
Install
1. Download ClipForge-v0.1.0-Windows.zip from Assets below (not the automatically generated source-code archive).
2. Extract the ZIP.
3. Open the ClipForge folder and double-click ClipForge.exe.
4. Keep _internal and ClipForgeStream alongside the EXE; they are required.
The AI speech model may need an internet connection on first use. Local CPU processing works without an NVIDIA GPU.
Included in v0.1.0
- Local recording and supported livestream capture
- AI speech transcription with faster-whisper
- Heuristic clip selection and ranking
- Vertical 720×1280 rendering and animated word-by-word captions
- SRT subtitle and transcript export
- Preview, save, and reject workflow
- Local CPU mode, compatible NVIDIA GPU selection, and optional authenticated remote GPU worker
- Configurable processing settings and logs
Verified so far
- The maintainer confirmed the Windows ZIP launches.
- Twitch live capture through remote A2000 GPU transcription and export was tested.
- YouTube Live capture was verified separately.
Known limitations
- Kick playback has not been verified end-to-end.
- Automatic social media posting is not implemented.
- Clip ranking uses speech heuristics, not a trained virality predictor.
- Some GPU and NVENC configurations need additional drivers or FFmpeg support.
- A remote GPU worker requires separate setup; local mode is the default.
- Broader testing on clean Windows systems and a bundled dependency/FFmpeg redistribution-license review remain outstanding.
Use only media you have permission to capture and share. ClipForge is independent of the streaming platforms it supports. This is early preview software; review clip selection, captions, and framing before publication.
