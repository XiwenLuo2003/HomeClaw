"""P7 · 3D 可视化只读后端（FastAPI）。

职责（对齐 06-3D场景可视化实施方案.md §6）：
  - GET  /scene              → 默认（SAGE）场景 + 实时状态的完整 3D JSON
  - GET  /scenes             → 可选场景清单（sage / homebench）
  - GET  /scenes/{source}    → 指定场景 + 实时状态
  - POST /act                → 下发一条动作文本（room.device.op(arg)），驱动实时联动
  - GET  /images/*           → SAGE 实景照片静态目录（data/sage/images/ 下的 UUID.jpg）

设计原则：
  - 复用 P6 现成的 scene_to_dict(scene, executor)（不落盘、直接返回 dict）；
  - 全程 --executor sim，离线可演示，无需真机/数据库（对齐 00「可复现优先」）；
  - executor 进程内常驻，执行动作后状态即时反映到 /scene（前端轮询即可看到颜色变）。

运行：
    cd HomeClaw
    pip install -r web/requirements.txt
    uvicorn web.server:app --reload --port 8000
"""
from __future__ import annotations

import os
import threading
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from homeclaw import data_paths
from homeclaw.scene import build_sage_scene, build_homebench_scene, scene_to_dict
from homeclaw.executor import make_executor


# ---------------------------------------------------------------------------- #
# 场景 + executor 进程内常驻（sim 后端，离线可复现）
# ---------------------------------------------------------------------------- #
def _make_entry(build_fn):
    scene = build_fn()
    ex = make_executor("sim", home_status=scene.to_home_status())
    return {"scene": scene, "executor": ex, "lock": threading.Lock()}


_SCENES: Dict[str, dict] = {
    "sage": _make_entry(build_sage_scene),
    "homebench": _make_entry(build_homebench_scene),
}
_DEFAULT = "sage"


def _entry(source: str) -> dict:
    entry = _SCENES.get(source)
    if entry is None:
        raise HTTPException(status_code=404,
                            detail=f"未知场景 source={source!r}，可选 {list(_SCENES)}")
    return entry


# ---------------------------------------------------------------------------- #
# FastAPI 应用
# ---------------------------------------------------------------------------- #
app = FastAPI(title="HomeClaw 3D Scene API", version="0.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 本地 demo，允许所有来源（Vite dev server / 静态站点）
    allow_methods=["*"],
    allow_headers=["*"],
)

# SAGE 实景照片静态目录：/images/<uuid>.jpg → data/sage/images/<uuid>.jpg
_IMAGES_DIR = os.path.join(data_paths.SAGE_DIR, "images")
if os.path.isdir(_IMAGES_DIR):
    app.mount("/images", StaticFiles(directory=_IMAGES_DIR), name="images")


class ActRequest(BaseModel):
    action: str                       # 动作文本，如 "bedroom.nightstand_light.turn_on()"
    source: str = _DEFAULT            # 作用于哪套场景


@app.get("/scenes")
def list_scenes():
    """返回可选场景清单及基本信息。"""
    out = []
    for src, entry in _SCENES.items():
        scene = entry["scene"]
        out.append({
            "source": src,
            "name": scene.name,
            "rooms": len(scene.rooms),
            "devices": sum(len(r.slots) for r in scene.rooms),
        })
    return {"default": _DEFAULT, "scenes": out}


@app.get("/scene")
def get_default_scene():
    """默认（SAGE）场景 + 实时状态的完整 3D JSON。"""
    return _scene_payload(_DEFAULT)


@app.get("/scenes/{source}")
def get_scene(source: str):
    """指定场景 + 实时状态。"""
    return _scene_payload(source)


@app.post("/act")
def act(req: ActRequest):
    """下发一条动作文本，驱动对应场景的实时状态变化。

    返回 executor 执行结果 + 该场景最新 3D JSON，前端可直接吃到「变化后」的场景。
    """
    entry = _entry(req.source)
    with entry["lock"]:
        result = entry["executor"].execute(req.action)
        payload = scene_to_dict(entry["scene"], entry["executor"])
    return {"result": result, "scene": payload}


def _scene_payload(source: str) -> dict:
    entry = _entry(source)
    with entry["lock"]:
        payload = scene_to_dict(entry["scene"], entry["executor"])
    payload["source"] = source
    return payload
