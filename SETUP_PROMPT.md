# SETUP_PROMPT.md — Paste this prompt into any SOTA LLM / AI harness

Copy everything between the markers below into a fresh chat with a SOTA coding
LLM (Claude, GPT, Gemini, Qwen, etc.) or into an agent harness (Cline, Claude
Code, Codex, Hermes-Agent, OpenCode, Antigravity, pi). It is fully
self-contained: context, constraints, task list, verification, deliverables.

---

```
You are setting up "Modal–ComfyUI–MiniMax-H3-Motion-Director", a serverless
ComfyUI app on a Modal H200. Everything below was verified against live
sources on 2026-09-06 (Firecrawl: GitHub repo files, HF repo layout, Modal
docs). Follow it exactly; do not "improve" versions without re-verifying
against the cited live source.

=== CONTEXT ===
1. Local machine: macOS or Linux. Use `uv` for ALL Python envs (never pip
   directly for venvs, never conda). ffmpeg installed.
2. A Modal account with MODAL_TOKEN_ID / MODAL_TOKEN_SECRET / HF_TOKEN in a
   gitignored .env (see .env.example). Verify the active account with
   `modal profile current`. Modal CLI 1.5.x installed via `uv tool install modal`.
3. This repo contains the complete app: comfyui_director_serve.py (Modal app),
   scripts/smoke_director.py (smoke test), README.md, GOTCHAS.md, PLAN.md.
   Your job is to deploy, verify, and operate it — not to rewrite it.

=== GOAL ===
A) Deploy `comfyui_director_serve.py`: headless ComfyUI 0.34+ with the MiniMax
   H3 Motion Director custom node (v1.2.0, j955229) on an H200 GPU, served as
   a class-based @app.server() (Modal 1.5.x — function form raises TypeError).
B) The custom node is installed at IMAGE BUILD: git clone into
   /workflow/custom_nodes/ + pip install -r its requirements.txt (only:
   opencv-python-headless, imageio-ffmpeg, scenedetect). No LLM, no extra API.
C) Model weights (the fixed user-selected MiniMax-H3 set from
   Comfy-Org/MiniMax-H3 — 5 files, ~157 GB, NEVER turbo/other variants)
   download at FIRST CONTAINER START into Modal Volume "comfy-models" mounted
   at /ComfyUI (runtime download; build-time download of 157 GB dies on the
   build sandbox). Later cold starts skip it.
D) Users drive the app from a BROWSER at the Modal HTTPS endpoint: the
   Director node's timeline UI (T2V/I2V/FL2V/R2V/V2V/RV2V + Mixed Mode).
   Agents verify health over HTTP and fetch outputs from the volume.

=== VERIFIED SOURCES (2026-09-06; re-verify via live fetch if older) ===
- Motion Director repo: https://github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director
  (v1.2.0, GPL-3.0; NODE_CLASS_MAPPINGS = MiniMaxH3MotionDirector,
  MiniMaxH3MotionDirectorInputs, MiniMaxH3MotionDirectorAssets; WEB_DIRECTORY
  ./web/js; requires ComfyUI >= 0.30.0 with official MiniMax H3 support; do
  NOT install ComfyUI-H3-Motion-Context alongside it)
- Models: https://huggingface.co/Comfy-Org/MiniMax-H3
  (diffusion_models/minimax_h3_fl2va_bf16.safetensors 66.3 GB,
  diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors 34.0 GB,
  text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors 51.5 GB,
  vae/minimax_h3_video_vae_fp16.safetensors 5.2 GB,
  vae/minimax_h3_audio_vae_fp32.safetensors 0.6 GB)
- Modal GPU docs: https://modal.com/docs/guide/gpu (H200 = 141 GB SXM)

=== EXECUTION ORDER (do not skip verification) ===
Phase 0 — Environment audit ($0): uv --version; modal --version;
  modal profile current (must show the intended account); .env present with
  MODAL_TOKEN_ID/MODAL_TOKEN_SECRET/HF_TOKEN (NEVER print values).
Phase 1 — Local validation ($0):
  uv run --with "modal>=1.5.2,<1.6" python -c "import comfyui_director_serve"
  (must not raise — class-based @app.server() is mandatory in Modal 1.5.x).
Phase 2 — Deploy: modal secret create huggingface-token HF_TOKEN="$HF_TOKEN"
  (once per workspace), then `modal deploy comfyui_director_serve.py`
  (image build ~1 min). Save the printed endpoint as DIRECTOR_URL.
Phase 3 — Cold start: first request triggers the ~157 GB weight download
  into the volume — allow 20–40 min; watch `modal app logs comfyui-director-serve`.
Phase 4 — Verification gates (below). Do NOT start paid generations unless
  the user asked for one.
Phase 5 — Handoff: tell the user to open DIRECTOR_URL in a browser, add the
  "MiniMax H3 Motion Director" node, and follow README.md. Before writing any
  video prompts, read PROMPT_AUTHORING_GUIDE.md.

=== VERIFICATION GATES (must all pass) ===
- curl -s "$DIRECTOR_URL/system_stats" → NVIDIA H200 device, comfyui_version >= 0.30.0
- uv run python scripts/smoke_director.py --url "$DIRECTOR_URL" → SMOKE-DIRECTOR-OK
  (proves all 3 Director nodes registered in /object_info)
- modal app list shows comfyui-director-serve deployed
- Browser: Director node visible on the canvas (user-confirmed)

=== OPERATIONS ===
- Auto-scaledown after 15 min idle; cold start ~1–2 min (weights on volume),
  then ~118 GB VRAM load on the first generation (allow several minutes).
- Cost: H200 ~$0.001261/s per container. When done:
  modal app stop comfyui-director-serve -y
- Fetch outputs: modal volume get comfy-models outputs/<file> ./

=== REPORT ===
Produce a report with: exact commands run, the deployed DIRECTOR_URL,
verification outputs (truncated), estimated Modal spend, and idle-cleanup
instructions. Flag anything that diverged from this plan with the reason.
```
