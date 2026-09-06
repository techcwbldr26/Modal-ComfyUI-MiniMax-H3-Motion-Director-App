"""End-to-end smoke test for the Modal ComfyUI endpoint (MiniMax-H3 T2V).

Usage:
    uv run python scripts/smoke_t2v.py [--url https://<ws>--comfyui-director-serve-....modal.direct]

Submits the official T2V workflow (workflows/minimax_h3_t2v.json, UI format —
converted to API format here) with a short smoke prompt, waits for completion,
and verifies a real video output comes back (downloaded to outputs/).
Exits 0 on success, 1 on failure.

NOTE: this is the FULL video-generation proof (costs GPU minutes). For the
free health/node-registration check use scripts/smoke_director.py first.

The UI-format template + API conversion is adapted from the workflow proven
against this deployment (base mode verified 2026-09-06 on ComfyUI 0.34.0).

Model set (user-selected, verified on HF 2026-08-21 — NEVER replace):
    diffusion_models/minimax_h3_fl2va_bf16.safetensors (full BF16 fl2va UNET)
    text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors
    vae/minimax_h3_video_vae_fp16.safetensors
    vae/minimax_h3_audio_vae_fp32.safetensors

Base mode only: 20 steps, NO turbo LoRA (hard rule — user-selected models).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "minimax_h3_t2v.json"
OUT_DIR = ROOT / "outputs"

UNET = "minimax_h3_fl2va_bf16.safetensors"
# MiniMax-H3's text encoder (BF16). NOTE: despite the "qwen3vl" filename this
# is MiniMax-H3's own text encoder — MiniMax built H3 on a Qwen3-VL-32B
# backbone (verified: MiniMaxAI/MiniMax-H3 text_encoder/config.json ->
# architectures: Qwen3VLForConditionalGeneration). It is NOT the separately
# served Qwen LLM and there is no Qwen3.8 substitute for it.
CLIP = "qwen3vl_32b_minimax_h3_bf16.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
BASE_STEPS = 20  # base (non-turbo) sampling — no LoRA in this project

SMOKE_PROMPT = (
    "A tiny lighthouse on a rocky shore at dusk, gentle waves lapping the rocks, "
    "the beam sweeping slowly across calm water, gulls drifting in the distance. "
    "Audio: soft ocean waves and a distant foghorn, one short blast."
)


def _post(url: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(url: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _subgraph_instance(wf: dict) -> dict:
    """The top-level node whose type is the subgraph UUID (MiniMax-H3 T2V)."""
    for node in wf.get("nodes", []):
        ntype = node.get("type") or ""
        # skip the core UI nodes; the subgraph instance is the UUID-typed one
        if ntype and ntype not in (
            "SaveVideo", "ResolutionSelector", "MarkdownNote", "Note",
        ) and len(ntype) > 30:
            return node
    raise RuntimeError("subgraph instance node not found in workflow")


def _definition_nodes(wf: dict) -> list:
    defs = wf.get("definitions", {})
    subs = defs.get("subgraphs", [])
    if not subs:
        raise RuntimeError("no subgraph definitions in workflow")
    return subs[0].get("nodes", [])


def to_api_format(wf: dict) -> dict:
    """Convert this UI-format subgraph template into ComfyUI /prompt API format.

    The MiniMax-H3 T2V template is a single subgraph instance wrapping a fixed
    internal graph (UNETLoader -> [LoRA switch] -> BasicGuider/Sampler ->
    VAEDecode(+audio) -> CreateVideo -> SaveVideo). We expand it to the exact
    internal node set with the instance's widget values wired in.

    BASE MODE (this project): turbo_mode=False — the LoRA/switch nodes are
    omitted entirely and the base UNET feeds the sampler at 20 steps.
    """
    inst = _subgraph_instance(wf)
    wv = inst["widgets_values"]
    # Instance widgets (verified against template 2026-08-21):
    # 0 prompt, 1 width, 2 height, 3 duration(s), 4 noise_seed, 5 unet_name,
    # 6 clip_name, 7 vae_name, 8 audio_vae, 9 turbo_mode(bool), 10 lora_name,
    # 11 turbo_model_strength, 12 turbo_steps
    prompt_text, width, height, duration = wv[0], int(wv[1]), int(wv[2]), float(wv[3])
    seed = int(wv[4])
    unet_name = wv[5]
    clip_name = wv[6]
    vae_name = wv[7]
    audio_vae_name = wv[8]
    # wv[9..12] are the turbo-mode widgets (turbo_mode, lora_name, strength,
    # steps) — NOT used in this project: base mode only, no LoRA.

    # length: snap duration to the model's 17-frames-per-block (17k+5) grid @24fps
    # (same expression the template's ComfyMathExpression node evaluates)
    base = max(5, round(duration * 24))
    length = base + (5 - base % 17) % 17

    steps = BASE_STEPS  # base mode — no turbo LoRA in this project

    save_prefix = f"smoke_{int(time.time())}"

    api = {
        # UNETLoader (node 127 in the template)
        "127": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        # CLIPLoader (128)
        "128": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": "minimax", "device": "default"},
        },
        # Video VAE (119) / Audio VAE (120)
        "119": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "120": {"class_type": "VAELoader", "inputs": {"vae_name": audio_vae_name}},
        # Sampler plumbing
        "123": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "124": {
            "class_type": "BasicScheduler",
            "inputs": {"model": ["127", 0], "scheduler": "simple", "steps": steps, "denoise": 1},
        },
        "129": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed, "control_after_generate": "fixed"}},
        # MiniMaxH3ImageToVideo (131) — T2V: no first/last frame
        "131": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["128", 0],
                "vae": ["119", 0],
                "prompt": prompt_text,
                "width": width,
                "height": height,
                "length": length,
            },
        },
        "126": {
            "class_type": "BasicGuider",
            "inputs": {"model": ["127", 0], "conditioning": ["131", 0]},
        },
        "125": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["129", 0],
                "guider": ["126", 0],
                "sampler": ["123", 0],
                "sigmas": ["124", 0],
                "latent_image": ["131", 1],
            },
        },
        "122": {"class_type": "VAEDecode", "inputs": {"samples": ["125", 0], "vae": ["119", 0]}},
        "121": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["125", 0], "vae": ["120", 0]}},
        "130": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["122", 0], "audio": ["121", 0], "fps": 24, "bit_depth": 8},
        },
        "92": {
            "class_type": "SaveVideo",
            # SaveVideo.format is COMFY_DYNAMICCOMBO_V3 on current ComfyUI:
            # the codec sub-input is the dotted key "format.codec".
            "inputs": {"video": ["130", 0], "filename_prefix": save_prefix, "format": "auto", "format.codec": "auto"},
        },
    }
    # sanity: internal template nodes we rely on must exist in the definition
    internal_types = {n.get("type") for n in _definition_nodes(wf)}
    required = {"UNETLoader", "CLIPLoader", "MiniMaxH3ImageToVideo", "SamplerCustomAdvanced", "CreateVideo"}
    missing = required - internal_types
    if missing:
        raise RuntimeError(f"workflow template missing expected node types: {missing}")
    return api


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("COMFYUI_URL", ""))
    ap.add_argument("--duration", type=float, default=1.0, help="clip length in seconds (snapped to 17k+5 frames @24fps)")
    ap.add_argument("--megapixels", type=float, default=0.2, help="smoke resolution budget (0.2 = 608x352 @16:9)")
    args = ap.parse_args()
    base = args.url.rstrip("/")
    if not base:
        print("ERROR: pass --url or set COMFYUI_URL")
        return 1

    # 1. Health
    stats = _get(f"{base}/system_stats")
    devs = stats.get("devices", [])
    print("system_stats OK — devices:", [d.get("name") for d in devs])

    # 2. Load the official T2V workflow (UI format) and shrink it to a smoke clip.
    wf = json.loads(WORKFLOW.read_text())
    inst = _subgraph_instance(wf)
    wv = inst["widgets_values"]
    wv[0] = SMOKE_PROMPT
    wv[3] = args.duration
    wv[5] = UNET  # enforce the user-selected BF16 fl2va UNET
    wv[9] = False  # turbo_mode OFF — base models, 20 steps, no LoRA (hard rule)

    # Resolution: the instance's width/height widgets are overridden by the
    # ResolutionSelector in the UI graph; in our API expansion we compute them
    # directly from the megapixel budget on the 32-multiple grid (16:9).
    mp = args.megapixels
    width = int(round((mp * 1e6 * 16 / 9) ** 0.5 / 32) * 32)
    height = int(round(width * 9 / 16 / 32) * 32)
    wv[1], wv[2] = width, height

    api_prompt = to_api_format(wf)

    # 3. Submit (ComfyUI /prompt expects API format)
    prompt_id = _post(f"{base}/prompt", {"prompt": api_prompt})["prompt_id"]
    print("submitted prompt_id:", prompt_id)

    # 4. Poll history until done (deadline loop — no `timeout` cmd on macOS).
    deadline = time.time() + 1800
    while time.time() < deadline:
        time.sleep(5)
        try:
            hist = _get(f"{base}/history/{prompt_id}")
        except urllib.error.HTTPError:
            continue
        except Exception:
            continue
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                print("ERROR: workflow failed:", json.dumps(status)[:2000])
                return 1
            outputs = entry.get("outputs", {})
            for node_id, out in outputs.items():
                for f in out.get("gifs", []) + out.get("videos", []) + out.get("images", []):
                    fn = f.get("filename")
                    if fn:
                        print("output file:", fn)
                        # 5. Download the artifact as proof it's a real video.
                        OUT_DIR.mkdir(exist_ok=True)
                        sub = f.get("subfolder", "")
                        q = f"filename={fn}&subfolder={sub}&type={f.get('type', 'output')}"
                        data = urllib.request.urlopen(f"{base}/view?{q}", timeout=120).read()
                        dest = OUT_DIR / fn
                        dest.write_bytes(data)
                        print("downloaded:", dest, f"({len(data)} bytes)")
                        return 0
            print("ERROR: workflow finished but no video output found")
            return 1
    print("ERROR: timed out waiting for workflow")
    return 1


if __name__ == "__main__":
    sys.exit(main())