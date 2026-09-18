"""导出场景 JSON 供前端 3D 可视化（P6 CLI）。

用法：
    python3 export_scenes.py                 # 导出 HomeBench + SAGE 两套静态场景
    python3 export_scenes.py --live          # 额外导出一个带实时设备动作的 SAGE 场景示例
    python3 export_scenes.py --out-dir ./web  # 指定输出目录

输出：
    <out>/homebench_scene.json   # HomeBench 12 房间场景（含 3D 坐标）
    <out>/sage_scene.json        # SAGE 抽象场景（含 3D 坐标）
    <out>/sage_scene_live.json   # (--live) 执行若干动作后的实时状态叠加
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from homeclaw.scene import (  # noqa: E402
    build_homebench_scene,
    build_sage_scene,
    export_scene_json,
    export_scene_with_live,
)
from homeclaw.executor import make_executor  # noqa: E402


def _out(out_dir, name):
    if out_dir is None:
        return None
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, name)


def main():
    ap = argparse.ArgumentParser(description="导出智能家居场景 JSON（供 3D 可视化）")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认 runtime/scenes/）")
    ap.add_argument("--live", action="store_true", help="额外导出带实时动作的 SAGE 场景")
    args = ap.parse_args()

    hb = build_homebench_scene()
    sg = build_sage_scene()

    p1 = export_scene_json(hb, _out(args.out_dir, "homebench_scene.json"))
    p2 = export_scene_json(sg, _out(args.out_dir, "sage_scene.json"))
    print("HomeBench 场景 -> %s (%d 房间)" % (p1, len(hb.rooms)))
    print("SAGE 场景     -> %s (%d 房间)" % (p2, len(sg.rooms)))

    if args.live:
        # 演示：在 SAGE 场景上执行若干动作，导出实时状态叠加（供 P7 动态渲染）
        ex = make_executor("sim", home_status=sg.to_home_status())
        for act in ["bedroom.light.turn_on()",
                           "bedroom.light.set_color((255, 0, 0))",
                           "living_room.tv.turn_on()",
                           "kitchen.dishwasher.turn_on()"]:
            ex.execute(act)
        p3 = export_scene_with_live(sg, ex, _out(args.out_dir, "sage_scene_live.json"))
        print("SAGE 实时场景 -> %s" % p3)


if __name__ == "__main__":
    main()
