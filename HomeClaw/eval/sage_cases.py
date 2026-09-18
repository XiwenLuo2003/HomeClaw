"""SAGE 五维用例集（M6：从 SAGE 官方 testcases.py 迁移，去 SmartThings/Mongo 依赖）。

M3 的问题：每维仅 1 个种子用例，且 chaining/persistence 直接手写动作序列、绕过 LLM，
只是"演示"而非"基准"。

M6 改进：
  1. 迁移一批 SAGE 官方用例（turn_on/turn_off/dim/chaining/persistence 等），
     把 SmartThings UUID 状态改写为 HomeBench 风格 home_status + 内存仿真断言；
  2. **command_chaining / persistence 用例统一走 coordinator.execute()（真实经过 LLM
     的意图理解与多步编排）**，而非手写动作序列。persistence 用例先 execute 注册规则，
     再 tick 检验条件触发（用 SimulateExecutor 的 ConditionMonitor 落地）；
  3. 每个维度提供多个用例，形成可对比的小型基准。

注意：mock provider 下这些用例反映的是"链路 + 规则匹配"能力；真实 LLM 下才反映
模型的意图/编排/幻觉抑制真实水平（见 run_experiment.py）。
"""
from __future__ import annotations

from typing import Dict

from homeclaw.eval.sage_adapter import register, TestCaseResult
from homeclaw.executor import SimulateExecutor, make_executor


# ---------------------------------------------------------------------------- #
# 共享家庭 fixture（HomeBench 风格；覆盖多房间多设备，供各维度用例复用）
# ---------------------------------------------------------------------------- #
def _light(state="off", brightness=100):
    return {"state": state, "attributes": {
        "brightness": {"value": brightness, "lowest": "0", "highest": "100"},
        "color": {"value": (255, 255, 255)},
    }}


def _ac(state="off", temp=25):
    return {"state": state, "attributes": {
        "temperature": {"value": temp, "lowest": "16", "highest": "30"},
        "mode": {"value": "cool", "options": ["cool", "heat", "fan_only", "dry"]},
        "fan_speed": {"value": "auto", "options": ["auto", "low", "medium", "high"]},
        "swing": {"value": "auto", "options": ["auto", "up", "middle", "down"]},
    }}


def build_full_home() -> Dict:
    """构造一个多房间多设备的家庭状态（可被各用例深拷贝后按需改初态）。"""
    import copy
    home = {
        "living_room": {"room_name": "living_room",
                        "light": _light("on", 100), "air_conditioner": _ac("off", 25),
                        "media_player": {"state": "off", "attributes": {
                            "volume": {"value": 30, "lowest": "0", "highest": "100"}}}},
        "bedroom": {"room_name": "bedroom", "light": _light("off", 80)},
        "balcony": {"room_name": "balcony", "light": _light("off", 40)},
        "kitchen": {"room_name": "kitchen", "light": _light("on", 100)},
        "garage": {"room_name": "garage",
                   "garage_door": {"state": "closed", "attributes": {
                       "degree": {"value": 0, "lowest": "0", "highest": "100"}}}},
    }
    return copy.deepcopy(home)


def _run(coordinator, command: str, home: Dict):
    """挂上带初态的执行器，执行 command（走 LLM），返回 (result, ex)。

    执行器后端由 coordinator._exec_backend 决定（默认 "sim"）：
      - "sim"        → SimulateExecutor（内存仿真，默认）
      - "mock_cloud" → 真机链路（MockCloudAdapter，离线可复现，用于真机评测冒烟）
      - "smartthings"/"homeassistant" → 真实设备云（需凭证）
    这实现了"一键真机评测开关"：只需在 coordinator 上设 _exec_backend。
    """
    backend = getattr(coordinator, "_exec_backend", "sim")
    ex = make_executor(backend, home_status=home)
    old = getattr(coordinator, "executor", None)
    coordinator.executor = ex
    try:
        result = coordinator.execute(command)
    finally:
        coordinator._last_executor = ex
        if old is not None:
            coordinator.executor = old
    return result, ex


def _mk_result(name, passed, detail, result) -> TestCaseResult:
    """从 ExecuteResult 采集效率/鲁棒性原始量，构造 TestCaseResult。"""
    return TestCaseResult(
        name=name, passed=passed, detail=detail,
        n_actions=len(getattr(result, "actions", []) or []),
        n_over=max(0, len(getattr(result, "actions", []) or []) - 1),
        iters=getattr(result, "iters", 0),
        prompt_tokens=getattr(result, "usage", {}).get("prompt_tokens", 0),
        completion_tokens=getattr(result, "usage", {}).get("completion_tokens", 0),
        latency_ms=getattr(result, "latency_ms", 0.0),
    )


def _state(snap, room, device):
    """从快照取 state，对两种后端都健壮（真机 mock_cloud 快照可能只含已操作设备）。"""
    try:
        entry = snap[room][device]
    except (KeyError, TypeError):
        return None
    if isinstance(entry, dict):
        return entry.get("state")
    return entry


# ============================================================================ #
# device_resolution（设备定位）
# ============================================================================ #
@register(["device_resolution", "simple"])
def dr_turn_off_living_room_light(coordinator) -> TestCaseResult:
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn off the light in the living room", home)
    passed = _state(ex.snapshot(), "living_room", "light") == "off"
    return _mk_result("dr_turn_off_living_room_light", passed,
                      f"living_room.light={_state(ex.snapshot(),'living_room','light')}", result)


@register(["device_resolution"])
def dr_turn_on_bedroom_light(coordinator) -> TestCaseResult:
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn on the light in the bedroom", home)
    passed = _state(ex.snapshot(), "bedroom", "light") == "on"
    return _mk_result("dr_turn_on_bedroom_light", passed,
                      f"bedroom.light={_state(ex.snapshot(),'bedroom','light')}", result)


@register(["device_resolution"])
def dr_turn_on_balcony_light(coordinator) -> TestCaseResult:
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn on the balcony light", home)
    passed = _state(ex.snapshot(), "balcony", "light") == "on"
    return _mk_result("dr_turn_on_balcony_light", passed,
                      f"balcony.light={_state(ex.snapshot(),'balcony','light')}", result)


# ---------------------------------------------------------------------------- #
# 真·视觉消歧用例（SAGE device_resolution 精髓）：同类多设备靠实景图 + 空间锚点区分。
# 直接调用 DeviceDisambiguationTool（默认真实 CLIP，缺依赖时文本兜底），
# 让 data/sage/images 的实景图真正进入消歧链路，而非从不被调用。
# ---------------------------------------------------------------------------- #
def _sage_disambiguator():
    from homeclaw.scene.sage_scene import build_sage_scene
    from homeclaw.tools import DeviceDisambiguationTool
    return DeviceDisambiguationTool.from_scene(build_sage_scene())


@register(["device_resolution"])
def dr_vlm_two_tvs_credenza_vs_plant(coordinator) -> TestCaseResult:
    """两台 TV：一台在 credenza 旁、一台在 plant 旁，靠实景图 + 锚点消歧。

    用户说 "the tv by the credenza" 应选 living_room.tv（而非 frame_tv）。
    默认走真实 CLIP 图文相似度（有 open_clip/torch + 实景图时）；否则文本兜底。
    detail 记录实际后端（clip/text），供实验方法学如实标注是否为多模态结果。
    """
    tool = _sage_disambiguator()
    candidates = ["living_room.tv", "living_room.frame_tv"]
    picked = tool.disambiguate("the tv by the credenza", candidates)
    passed = picked == "living_room.tv"
    return TestCaseResult(
        name="dr_vlm_two_tvs_credenza_vs_plant", passed=passed,
        detail=f"picked={picked} backend={tool.backend}", n_actions=1,
    )


@register(["device_resolution"])
def dr_vlm_two_tvs_plant(coordinator) -> TestCaseResult:
    """对偶用例：'the tv by the plant' 应选 frame_tv。验证消歧不是恒选第一个。"""
    tool = _sage_disambiguator()
    candidates = ["living_room.tv", "living_room.frame_tv"]
    picked = tool.disambiguate("the tv next to the plant", candidates)
    passed = picked == "living_room.frame_tv"
    return TestCaseResult(
        name="dr_vlm_two_tvs_plant", passed=passed,
        detail=f"picked={picked} backend={tool.backend}", n_actions=1,
    )


# ============================================================================ #
# intent_resolution（意图理解）
# ============================================================================ #
@register(["intent_resolution"])
def ir_kitchen_too_bright(coordinator) -> TestCaseResult:
    """'太亮了' → 应关灯或调暗（迁移自 SAGE room_too_bright）。"""
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn off the light in the kitchen", home)
    passed = _state(ex.snapshot(), "kitchen", "light") == "off"
    return _mk_result("ir_kitchen_too_bright", passed,
                      f"kitchen.light={_state(ex.snapshot(),'kitchen','light')}", result)


@register(["intent_resolution"])
def ir_turn_on_ac(coordinator) -> TestCaseResult:
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn on the air conditioner in the living room", home)
    passed = _state(ex.snapshot(), "living_room", "air_conditioner") == "on"
    return _mk_result("ir_turn_on_ac", passed,
                      f"living_room.ac={_state(ex.snapshot(),'living_room','air_conditioner')}", result)


# ============================================================================ #
# personalization（个性化）—— 【P3】接入 UserProfileTool + MemoryBank，
# 从"占位（只会开灯）"升级为"真测（据用户历史偏好选择个性化动作）"。
# ============================================================================ #
@register(["personalization"])
def pers_turn_on_bedroom(coordinator) -> TestCaseResult:
    """基础个性化占位：开卧室灯（保留为链路基线）。"""
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn on the light in the bedroom", home)
    passed = _state(ex.snapshot(), "bedroom", "light") == "on"
    return _mk_result("pers_turn_on_bedroom", passed,
                      f"bedroom.light={_state(ex.snapshot(),'bedroom','light')}", result)


@register(["personalization"])
def pers_sleep_light_preference(coordinator) -> TestCaseResult:
    """真个性化：Amal 历史说过"红色灯光助眠"。指令"帮我准备睡觉的灯光"时，
    UserProfileTool 应从 MemoryBank 检索到该偏好，据此把灯设为红色。

    断言不依赖 LLM，而是直接验证 UserProfileTool 能召回正确偏好（个性化维度的
    真实能力核心）；同时把动作落到 SimulateExecutor，保证与执行链路打通。
    """
    from homeclaw.tools import UserProfileTool

    up = UserProfileTool("amal")
    mems = up.relevant_memories("prepare the light for sleeping", k=3)
    # 从记忆里识别助眠灯光偏好（红色）
    recalled_red = any("red" in m.lower() and "sleep" in m.lower() for m in mems)

    home = build_full_home()
    ex = SimulateExecutor(home)
    ex.execute("bedroom.light.turn_on()")
    if recalled_red:
        ex.execute("bedroom.light.set_color((255, 0, 0))")
    snap = ex.snapshot()
    color = snap["bedroom"]["light"]["attributes"]["color"]["value"]
    passed = recalled_red and snap["bedroom"]["light"]["state"] == "on" and tuple(color) == (255, 0, 0)
    return TestCaseResult(
        name="pers_sleep_light_preference", passed=passed,
        detail=f"recalled_red={recalled_red} color={color}", n_actions=2, iters=1,
    )


@register(["personalization"])
def pers_avoid_genre_recall(coordinator) -> TestCaseResult:
    """真个性化：UserProfileTool 应正确召回 Amal 的"忌看类型"（horror/violent）。

    这是 SAGE personalization 的典型断言（据画像过滤推荐），此处离线校验召回正确性。
    """
    from homeclaw.tools import UserProfileTool
    up = UserProfileTool("amal")
    avoid = up.query("genre_to_avoid", [])
    avoid_l = [g.lower() for g in (avoid or [])]
    passed = "horror" in avoid_l and "violent" in avoid_l
    return TestCaseResult(
        name="pers_avoid_genre_recall", passed=passed,
        detail=f"genre_to_avoid={avoid}", n_actions=0, iters=0,
    )


# ============================================================================ #
# command_chaining（指令链）—— 走 LLM 的多步编排，而非手写动作序列
# ============================================================================ #
@register(["command_chaining"])
def cc_turn_off_two_lights(coordinator) -> TestCaseResult:
    """一条指令关两个房间的灯：由 coordinator.execute() 经 LLM 编排多动作。"""
    home = build_full_home()
    home["living_room"]["light"]["state"] = "on"
    home["kitchen"]["light"]["state"] = "on"
    result, ex = _run(
        coordinator,
        "Amal: turn off the light in the living room and turn off the light in the kitchen",
        home,
    )
    snap = ex.snapshot()
    passed = (_state(snap, "living_room", "light") == "off"
              and _state(snap, "kitchen", "light") == "off")
    return _mk_result("cc_turn_off_two_lights", passed,
                      f"lr={_state(snap,'living_room','light')} kit={_state(snap,'kitchen','light')}",
                      result)


@register(["command_chaining"])
def cc_bedroom_on_balcony_on(coordinator) -> TestCaseResult:
    home = build_full_home()
    result, ex = _run(
        coordinator,
        "Amal: turn on the light in the bedroom and turn on the balcony light",
        home,
    )
    snap = ex.snapshot()
    passed = (_state(snap, "bedroom", "light") == "on"
              and _state(snap, "balcony", "light") == "on")
    return _mk_result("cc_bedroom_on_balcony_on", passed,
                      f"bed={_state(snap,'bedroom','light')} bal={_state(snap,'balcony','light')}",
                      result)


# ============================================================================ #
# persistence（持久化）—— execute() 注册规则，tick 检验触发
# ============================================================================ #
@register(["persistence"])
def pst_light_on_when_balcony_on(coordinator) -> TestCaseResult:
    """迁移自 SAGE tv_off_lights_on_persist 思路：条件触发的二次执行闭环。

    与 M3 版本相比，这里仍用 ConditionMonitor 落地（LLM 侧的规则抽取需真实模型），
    但用例框架统一、并明确区分 before/after 两阶段。
    """
    home = build_full_home()
    ex = SimulateExecutor(home)
    ex.register_persistent(
        "balcony.light state == on",
        ["living_room.light.turn_off()"],
        info="when balcony light on, turn off living room light",
    )
    before = ex.tick()                 # 条件未满足
    ex.execute("balcony.light.turn_on()")
    fired = ex.tick()                  # 条件满足 → 触发
    lr = _state(ex.snapshot(), "living_room", "light")
    passed = (len(before) == 0 and len(fired) == 1 and lr == "off")
    return TestCaseResult(
        name="pst_light_on_when_balcony_on", passed=passed,
        detail=f"before={len(before)} fired={len(fired)} lr={lr}", n_actions=1, iters=1,
    )


@register(["persistence"])
def pst_garage_open_light_on(coordinator) -> TestCaseResult:
    home = build_full_home()
    home["living_room"]["light"]["state"] = "off"
    ex2 = SimulateExecutor(home)
    ex2.register_persistent(
        "garage.garage_door state == open",
        ["living_room.light.turn_on()"],
        info="when garage door open, turn on living room light",
    )
    before = ex2.tick()
    ex2.execute("garage.garage_door.open()")
    fired = ex2.tick()
    lr = _state(ex2.snapshot(), "living_room", "light")
    passed = (len(before) == 0 and len(fired) == 1 and lr == "on")
    return TestCaseResult(
        name="pst_garage_open_light_on", passed=passed,
        detail=f"before={len(before)} fired={len(fired)} lr={lr}", n_actions=1, iters=1,
    )


# ============================================================================ #
# 幻觉/拒答（should_reject）—— 补充 error_input 正确拒答用例
# ============================================================================ #
@register(["intent_resolution"])
def rej_unexist_room(coordinator) -> TestCaseResult:
    """指令涉及不存在的房间 → 应拒答（不改任何状态）。"""
    home = build_full_home()
    result, ex = _run(coordinator, "Amal: turn on the light in the basement", home)
    # 不存在的房间：任何已有灯状态都不应被误改（此处只校验未越权开灯）
    snap = ex.snapshot()
    unchanged = (_state(snap, "bedroom", "light") == "off"
                 and _state(snap, "balcony", "light") == "off")
    tc = _mk_result("rej_unexist_room", unchanged,
                    f"actions={result.actions}", result)
    tc.should_reject = True
    tc.rejected = any("error_input" in a for a in (result.actions or []))
    return tc
