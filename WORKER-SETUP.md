# Remote worker setup

The preview worker accepts one job at a time and binds to localhost. Run it as an unprivileged user on a trusted host. Use an SSH tunnel to connect from Windows.

For CUDA, first verify that the worker OS can see the GPU with `nvidia-smi`. Install compatible NVIDIA drivers and CUDA/cuDNN libraries for your CTranslate2 version. You can also run the worker in CPU mode.

From the project folder on the worker:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export CLIPFORGE_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
printf '%s\n' "$CLIPFORGE_TOKEN"
.venv/bin/python worker.py --device cuda --data ./worker-data
```

Keep the printed token private. Use `--device cpu` for a CPU worker. The worker stays active while this command runs.

On Windows, open a separate PowerShell window and keep the tunnel running:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 YOUR_USER@YOUR_WORKER_HOST
```

Enable remote processing in ClipForge, enter `http://127.0.0.1:8765` and the worker token, then use **Detect GPUs** to refresh the device list. Leave NVENC off unless you have verified hardware encoding on the worker.

The worker removes uploaded media after processing ends. Generated clips, transcripts, and job folders remain until cleaned up by the operator. Job status is held in memory. Stopping the desktop client can leave a submitted job running. Keep the service off the public internet and monitor available disk space.
