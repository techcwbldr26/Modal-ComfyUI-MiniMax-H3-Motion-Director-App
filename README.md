# ComfyUI-MiniMax-H3-Motion-Director App (Modal H200, no LLM)

Headless **ComfyUI + [MiniMax H3 Motion Director](https://github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director)**
(v1.2.0) on a Modal H200. Multi-segment video production — `T2V / I2V / FL2V /
R2V / V2V / RV2V` and **Mixed Mode** timelines with cross-segment continuity,
Selective Run, Material Library, live preview, and post-processing.

**No LLM.** Pure ComfyUI. You drive it from a **browser**.

Model set: the user-selected MiniMax-H3 files from
[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) are
downloaded into a Modal Volume (`comfy-models`) on first container start
(~157 GB via Xet; persists across restarts). Base mode only, 20 steps
(no turbo LoRA).

## Quick start

Prerequisites: a [Modal](https://modal.com) account, a
[HuggingFace](https://huggingface.co) token, `uv` and `ffmpeg` installed.

```bash
git clone https://github.com/techcwbldr26/Modal-ComfyUI-MiniMax-H3-Motion-Director-App.git
cd Modal-ComfyUI-MiniMax-H3-Motion-Director-App

cp .env.example .env          # fill MODAL_TOKEN_ID, MODAL_TOKEN_SECRET, HF_TOKEN
uv venv .venv && uv pip install --python .venv/bin/python "modal>=1.5.2,<1.6" huggingface_hub

set -a; source .env; set +a
modal secret create huggingface-token HF_TOKEN="$HF_TOKEN"   # once per workspace
modal profile current                                         # verify the right account

modal deploy comfyui_director_serve.py 2>&1 | tee deploy_director.log
# copy the printed URL → DIRECTOR_URL (also put it in .env)

curl -s "$DIRECTOR_URL/system_stats"                                 # NVIDIA H200
uv run python scripts/smoke_director.py --url "$DIRECTOR_URL"        # SMOKE-DIRECTOR-OK
```

> **First deploy:** the image build is fast (~1 min), but the first container
> start downloads ~157 GB of model weights into the Modal Volume — allow
> 20–40 minutes before the first request. Later cold starts skip it.

Then open `https://<ws>--comfyui-director-serve-....modal.direct` in a browser:

1. Double-click the canvas → search **"MiniMax H3 Motion Director"** → add it.
2. Pick a generation mode (`T2V` to start), set aspect/megapixels/FPS.
3. Add a Prompt Group with a prompt + duration → **Run** (queue prompt).
4. Watch **Live Preview**; enable Postprocess only once content is worth keeping.
5. **Results → Final Result** → save the video (lands in `/ComfyUI/outputs` on
   the volume; fetch with `modal volume get comfy-models outputs/<file>`).

Multi-segment: **Add Prompt Group** per segment (e.g. 3 × 10 s T2V), or switch
to **Mixed** to give each segment its own mode. Use **Selective Run** to re-roll
only failed segments. Full manual: the Director repo's `docs/USER_GUIDE.md`.

## Files

| File | Purpose |
|---|---|
| `comfyui_director_serve.py` | Modal app (class `@app.server()`, H200, volume-backed models) |
| `scripts/smoke_director.py` | health + Director node registration check |
| `PLAN.md` / `GOTCHAS.md` | plan + pitfalls |
| `.env.example` | Modal keys + HF_TOKEN only (no LLM vars) |

## Costs & hygiene

- H200 ≈ $0.001261/s (~$4.54/h) per running container; auto-scaledown after
  15 min idle; cold start ~1–2 min (weights on volume) + several minutes to
  load ~118 GB into VRAM on the first generation.
- When done: `modal app stop comfyui-director-serve -y`.
- Check spend: `modal billing report --for "this month"`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Director node missing in UI | Custom node import failed — `uv run python scripts/smoke_director.py`, then `modal app logs comfyui-director-serve` for the traceback. |
| Broken/blank Director panel after redeploy | Hard-refresh the browser (Cmd+Shift+R) — stale web/js cache. |
| `503 no upstreams` on first curl | Normal cold start — retry a few minutes. |
| First generation times out | Models loading into VRAM (~118 GB) — allow several minutes. |
| Import check fails locally | `uv run --with "modal>=1.5.2,<1.6" python -c "import comfyui_director_serve"` from this folder. |
