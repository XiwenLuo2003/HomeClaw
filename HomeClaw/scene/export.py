"""场景 JSON 导出接口（P6）：把 Scene 导出为前端 3D 可视化可用的 JSON 文件。

提供两类导出：
  1. export_scene_json(scene)          → 静态场景（房间/设备/3D 坐标），P7 3D 建模用；
  2. export_scene_with_live(scene, ex)  → 叠加 executor 实时状态，演示"真实设备动作"。

导出文件默认落到 data_paths.runtime_path("scenes", ...)（runtime/scenes/），
前端可直接读取；也可指定 out_path。
"""
from __future__ import annotations

import json
import os
from typing import Optional

from homeclaw import data_paths
from homeclaw.scene.schema import Scene


def export_scene_json(scene: Scene, out_path: Optional[str] = None) -> str:
    """导出静态场景 JSON，返回文件路径。"""
    data = scene.to_json()
    return _write(data, out_path, f"{scene.source}_scene.json")


def export_scene_with_live(scene: Scene, executor, out_path: Optional[str] = None) -> str:
    """导出叠加实时设备状态的场景 JSON（executor 需支持 snapshot()）。"""
    live = executor.snapshot() if hasattr(executor, "snapshot") else None
    data = scene.to_json(live_status=live)
    return _write(data, out_path, f"{scene.source}_scene_live.json")


def scene_to_dict(scene: Scene, executor=None) -> dict:
    """返回场景 dict（不落盘），供进程内直接喂给前端/API。"""
    live = executor.snapshot() if (executor is not None and hasattr(executor, "snapshot")) else None
    return scene.to_json(live_status=live)


def _write(data: dict, out_path: Optional[str], default_name: str) -> str:
    if out_path is None:
        out_path = data_paths.runtime_path("scenes", default_name)
    else:
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path
