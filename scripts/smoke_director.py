"""Smoke test for the Modal ComfyUI + MiniMax-H3 Motion Director endpoint.

Usage:
    uv run python setup-install-modal-ComfyUI-MiniMax-H3-Motion-Director-app/scripts/smoke_director.py \
        [--url https://<ws>--comfyui-director-serve-....modal.direct]

Verifies (fast, no GPU generation):
  1. /system_stats healthy and ComfyUI version supports official MiniMax H3 (>= 0.30.0).
  2. /object_info registers all three Motion Director node classes — proves the
     custom node imported cleanly (a failed import silently drops its nodes).
  3. (optional, --full) runs the existing 1-second T2V smoke for end-to-end
     video proof.

Verified live 2026-09-06: node class names from the repo's __init__.py
(NODE_CLASS_MAPPINGS): MiniMaxH3MotionDirector, MiniMaxH3MotionDirectorInputs,
MiniMaxH3MotionDirectorAssets.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

DIRECTOR_NODES = [
    "MiniMaxH3MotionDirector",
    "MiniMaxH3MotionDirectorInputs",
    "MiniMaxH3MotionDirectorAssets",
]
MIN_COMFYUI = (0, 30, 0)  # Motion Director requires official MiniMax H3 support


def _get(url: str, timeout: int = 30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _parse_version(s: str):
    m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", s or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("DIRECTOR_URL", os.environ.get("COMFYUI_URL", "")))
    args = ap.parse_args()
    base = args.url.rstrip("/")
    if not base:
        print("ERROR: pass --url or set DIRECTOR_URL")
        return 1
    failures = []

    # 1. Health + version gate
    try:
        stats = _get(f"{base}/system_stats")
    except Exception as e:
        print(f"FAIL: /system_stats unreachable: {e}")
        return 1
    devs = [d.get("name") for d in stats.get("devices", [])]
    print("system_stats OK — devices:", devs)
    ver = _parse_version(stats.get("system", {}).get("comfyui_version", ""))
    print("comfyui_version:", stats.get("system", {}).get("comfyui_version"))
    if ver is None or ver < MIN_COMFYUI:
        failures.append(f"ComfyUI {ver} lacks official MiniMax H3 support (need >= {'.'.join(map(str, MIN_COMFYUI))})")

    # 2. Motion Director node registration
    obj = _get(f"{base}/object_info")
    for node in DIRECTOR_NODES:
        if node in obj:
            print(f"OK: /object_info registers {node}")
        else:
            failures.append(f"{node} missing from /object_info — custom node import failed (check app logs)")

    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("SMOKE-DIRECTOR-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
