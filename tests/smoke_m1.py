"""M1 冒烟测试：验证 smart-home Skill + 单主循环内核可端到端跑通。

运行（无需真实 API，使用 MockLLMClient）：
    cd HomeClaw
    python -m tests.smoke_m1
或：
    python tests/smoke_m1.py

覆盖：
  1. Skill 正文加载（frontmatter 剥离）；
  2. home_status / method 序列化；
  3. predict_actions（HomeBench 文本入口）；
  4. execute（SAGE 执行入口，走 NullExecutor 记录动作）；
  5. error_input 幻觉拒答路径。
"""
from __future__ import annotations

import os
import sys

# 允许直接 python tests/smoke_m1.py 运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw import HomeClawCoordinator, HomeClawCoordinatorConfig  # noqa: E402
from homeclaw.config import LLMConfig  # noqa: E402
from homeclaw.prompt import (  # noqa: E402
    load_skill_body,
    serialize_home_status,
    serialize_methods,
)


# 一个最小的家庭状态（HomeBench 风格）
HOME_STATUS = {
    "living_room": {
        "room_name": "living_room",
        "light": {
            "state": "on",
            "attributes": {
                "brightness": {"value": 100, "lowest": "0", "highest": "100"},
                "color": {"value": (255, 255, 255)},
            },
        },
    },
    "balcony": {
        "room_name": "balcony",
        "light": {
            "state": "on",
            "attributes": {
                "brightness": {"value": 80, "lowest": "0", "highest": "100"},
            },
        },
    },
}

METHODS = [
    {"room_name": "living_room", "device_name": "light", "operation": "turn_off", "parameters": []},
    {"room_name": "balcony", "device_name": "light", "operation": "set_brightness",
     "parameters": [{"name": "brightness", "type": "int"}]},
]


def _assert(cond: bool, msg: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    print("== M1 冒烟测试：HomeClaw Skill + 单主循环内核 ==\n")

    # 1. Skill 正文加载
    print("[1] Skill 正文加载")
    body = load_skill_body(None, "smart-home")
    _assert("error_input" in body, "SKILL 正文包含 error_input 规则")
    _assert(not body.startswith("---"), "frontmatter 已被剥离")

    # 2. 序列化
    print("[2] home_status / method 序列化")
    state_str = serialize_home_status(HOME_STATUS)
    method_str = serialize_methods(METHODS)
    _assert("living_room:" in state_str and "brightness" in state_str, "home_status 序列化含房间与属性")
    _assert("balcony.light.set_brightness(brightness:int);" in method_str, "method 序列化格式正确")

    # 3. Coordinator 初始化（mock LLM）
    print("[3] Coordinator 初始化")
    cfg = HomeClawCoordinatorConfig(llm_config=LLMConfig(provider="mock"))
    coord = HomeClawCoordinator(cfg)
    _assert(coord.skill_body == body, "Coordinator 已加载 Skill 正文")

    # 4. predict_actions（HomeBench 入口）—— 合法指令
    print("[4] predict_actions 合法指令")
    out = coord.predict_actions(HOME_STATUS, "Turn off the light in the living room.", METHODS)
    print(f"      → {out}")
    _assert(out.startswith("{") and out.endswith("}"), "输出被花括号包裹")
    _assert("living_room.light.turn_off()" in out, "正确识别 living_room.light.turn_off()")

    # 5. predict_actions —— 幻觉指令（不存在的房间）
    print("[5] predict_actions 幻觉拒答")
    out2 = coord.predict_actions(HOME_STATUS, "Turn on the light in the kitchen.", METHODS)
    print(f"      → {out2}")
    _assert("error_input" in out2, "不存在的 kitchen 触发 error_input")

    # 6. execute（SAGE 入口）—— 注入状态快照的 NullExecutor，演示落地记录
    print("[6] execute（SAGE 入口）")
    from homeclaw.executor import NullExecutor  # noqa: E402

    cfg2 = HomeClawCoordinatorConfig(
        llm_config=LLMConfig(provider="mock"),
        executor=NullExecutor(home_status=HOME_STATUS, methods=METHODS),
    )
    coord2 = HomeClawCoordinator(cfg2)
    result = coord2.execute("Amal: turn off the light in the living room")
    print(f"      → reply: {result}")
    print(f"      → actions: {result.actions}, iters: {result.iters}, usage: {result.usage}")
    _assert(len(result.actions) >= 1, "execute 至少产出一条动作")
    _assert("living_room.light.turn_off()" in result.actions, "SAGE 入口正确产出关灯动作")
    _assert(result.iters >= 1, "记录了迭代轮数（供效率评测维度）")

    print("\n== 全部冒烟用例通过 ==")


if __name__ == "__main__":
    main()
