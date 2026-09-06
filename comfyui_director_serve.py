"""Serverless ComfyUI on Modal H200 — MiniMax-H3 + Motion Director (custom node).

Verified live 2026-09-06 (Firecrawl against github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director):
  * Motion Director v1.2.0 is a ComfyUI CUSTOM NODE PACK (GPL-3.0). No LLM, no
    Qwen endpoint, no extra API — pure ComfyUI. Install = clone into
    ComfyUI/custom_nodes/ + pip install -r requirements.txt (tiny:
    opencv-python-headless, imageio-ffmpeg, scenedetect).
  * Requires a recent ComfyUI with OFFICIAL MiniMax H3 support (>= v0.30.0);
    we clone ComfyUI master at build time, so this is satisfied.
  * Registers nodes: MiniMaxH3MotionDirector / MiniMaxH3MotionDirectorInputs /
    MiniMaxH3MotionDirectorAssets, a web/js UI frontend, and PromptServer HTTP
    routes. It is an OUTPUT_NODE.
  * Do NOT install ComfyUI-H3-Motion-Context alongside it (integrated already).
  * Model set — user-selected MiniMax-H3 files (NEVER replace with turbo or
    other variants): fl2va bf16 (66.3 GB), ref2va int8 (34.0 GB),
    qwen3vl_32b text encoder (51.5 GB), video vae fp16 (5.2 GB), audio vae
    fp32 (0.6 GB). All downloaded at first container start into the
    'comfy-models' Modal Volume and persisted there (~157 GB total).

USAGE (this is a UI-driven node — use a BROWSER, not just the API):
    Open https://<ws>--comfyui-director-serve-....modal.direct in a browser,
    double-click the canvas, add the "MiniMax H3 Motion Director" node, and
    build T2V / I2V / FL2V / R2V / V2V / RV2V / Mixed timelines in its panel.

DEPLOY:
    modal deploy comfyui_director_serve.py
    curl -s <endpoint>/system_stats
    uv run python scripts/smoke_director.py --url <endpoint>

Idle hygiene:  modal app stop comfyui-director-serve -y
"""
import os
import subprocess
import time

import modal

APP_NAME = "comfyui-director-serve"
WORKDIR = "/workflow"            # ComfyUI source (image layer, read-only at runtime)
DIRECTOR_REPO = "https://github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director"
DIRECTOR_DIR = os.path.join(WORKDIR, "custom_nodes", "ComfyUI-MiniMax-H3-Motion-Director")
MODELS_ROOT = "/ComfyUI/models"  # Volume mount point: models/ + outputs/ persist here
COMFYUI_PORT = 8188
GPU = os.environ.get("GPU", "H200")          # 141 GB — fits full BF16 MiniMax-H3
MINUTES = 60

app = modal.App(APP_NAME)

# All weights and outputs live on this Modal Volume (persists across
# restarts and scaledowns). If you run other ComfyUI-on-Modal apps, reuse the
# same volume name to share the downloaded weights.
models_vol = modal.Volume.from_name("comfy-models", create_if_missing=True)

hf_secret = modal.Secret.from_name("huggingface-token")

comfy_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "ffmpeg", "curl")
    # NOTE: Modal builds images on GPU-enabled builders for GPU images; torch
    # wheels resolve at build time. If you see CPU-only torch, pin the CUDA
    # index explicitly (see GOTCHAS.md and the Modal GPU docs).
    .pip_install("torch", "torchvision", "torchaudio")
    .run_commands(
        "git clone --depth 1 https://github.com/comfyanonymous/ComfyUI /workflow",
        "pip install -r /workflow/requirements.txt",
        # Motion Director custom node — deps are 3 small pure-Python wheels
        # (opencv-python-headless, imageio-ffmpeg, scenedetect), safe at build.
        f"git clone --depth 1 {DIRECTOR_REPO} {DIRECTOR_DIR}",
        f"pip install -r {DIRECTOR_DIR}/requirements.txt",
        # Volume-backed model/output dirs, symlinked into stock ComfyUI layout.
        # ComfyUI's model scanner follows symlinks. NOTE: the ComfyUI repo
        # SHIPS a real empty models/ tree — `ln -sfn` would create the link
        # INSIDE it (/workflow/models/models) and ComfyUI would scan empty
        # dirs ("value not in list" errors). rm -rf first, then link. Also:
        # do NOT mkdir /ComfyUI here — the volume mounts at /ComfyUI and Modal
        # refuses to mount over a non-empty image path.
        "rm -rf /workflow/models",
        "ln -sfn /ComfyUI/models /workflow/models",
        "ln -sfn /ComfyUI/outputs /workflow/outputs",
    )
    .pip_install("huggingface_hub>=0.32.0")  # hf_xet (Xet) by default
    .env(
        {
            "HF_XET_HIGH_PERFORMANCE": "1",   # Xet is the Hub's standard backend
            # CRITICAL: stage HF downloads ON THE VOLUME, not the container
            # disk (~30 GB) — 157 GB of models would kill the build sandbox.
            "HF_HUB_CACHE": "/ComfyUI/.hf-cache",
        }
    )
)

# User-selected MiniMax-H3 model set — NEVER replace (hard rule).
PATTERNS = [
    "diffusion_models/minimax_h3_fl2va_bf16.safetensors",
    "diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors",
    "vae/minimax_h3_video_vae_fp16.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
]


def _ensure_models() -> None:
    """Download any missing user-selected MiniMax-H3 files into the volume.

    RUNTIME download (build-time Image.run_function of 157 GB is unreliable —
    build sandboxes have limited disk and the download dies mid-flight).
    The volume persists, so this runs once; later cold starts skip it.
    """
    from huggingface_hub import snapshot_download

    missing = [
        rel
        for rel in PATTERNS
        if not os.path.exists(os.path.join(MODELS_ROOT, rel))
    ]
    if not missing:
        print("models already present on volume — skipping download")
        return
    print(f"downloading {len(missing)} missing model files (Xet)...")
    snapshot_download(
        repo_id="Comfy-Org/MiniMax-H3",
        allow_patterns=missing,
        local_dir=MODELS_ROOT,
    )
    missing = [
        rel
        for rel in PATTERNS
        if not os.path.exists(os.path.join(MODELS_ROOT, rel))
    ]
    if missing:
        raise RuntimeError(f"Missing model files after download: {missing}")
    print(f"OK: {len(PATTERNS)} MiniMax-H3 files present under {MODELS_ROOT}")


def _wait_ready(proc, port: int, timeout_s: int = 1800) -> None:
    import urllib.request

    url = f"http://127.0.0.1:{port}/system_stats"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"ComfyUI exited early: {proc.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=5):
                return
        except Exception:
            time.sleep(2)
    raise TimeoutError("ComfyUI did not become healthy in time")


@app.server(
    image=comfy_image,
    gpu=GPU,
    scaledown_window=15 * MINUTES,     # auto-scale: containers spin down when idle
    startup_timeout=45 * MINUTES,      # first start: any missing model download + boot
    volumes={"/ComfyUI": models_vol},   # parent mount: models/ AND outputs/ persist
    secrets=[hf_secret],
    port=COMFYUI_PORT,
    target_concurrency=4,              # one generation at a time per container
    unauthenticated=True,              # dev server — stop the app when idle
)
class ComfyUIDirectorServer:
    @modal.enter()
    def start(self):
        # First start: ensure the user-selected MiniMax-H3 set is on the
        # volume, then run ComfyUI (with Motion Director loaded from
        # custom_nodes) as a background subprocess — never block readiness.
        os.makedirs("/ComfyUI/outputs", exist_ok=True)
        _ensure_models()
        cmd = [
            "python", os.path.join(WORKDIR, "main.py"),
            "--listen", "0.0.0.0",       # REQUIRED inside Modal — the web endpoint proxies to the container
            "--port", str(COMFYUI_PORT),
            "--disable-auto-launch",
        ]
        self.proc = subprocess.Popen(cmd, cwd=WORKDIR)
        _wait_ready(self.proc, COMFYUI_PORT)
        # Do NOT call proc.wait() here — return and let Modal mark ready.

    @modal.exit()
    def stop(self):
        if hasattr(self, "proc"):
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()

