"""P1~P6 冒烟测试：六个阶段交付的回归保护（纯离线、零外部依赖、mock LLM）。

运行：
    cd HomeClaw
    python3 tests/smoke_p1_p6.py

覆盖：
  [P1] 数据自包含    ：data/ 内数据文件存在；data_paths 无跨项目 ../HomeBench/../SAGE 引用；
                       homebench_adapter 走包内路径可加载。
  [P2] 场景层+SAGE设备：homebench 场景 12 房间可构建；sage 场景**全量覆盖** SAGE 官方
                       testcases 的 8 台真实设备（不再是子集）；SAGE 设备类已进 device_map。
  [P3] SAGE 工具补齐  ：MemoryBank 关键词检索可召回；UserProfileTool 个性化召回正确；
                       MemoryBank 可插拔向量检索器（EmbeddingRetriever）可用。
  [P4] 本地模型入口   ：create_llm_client 支持 provider=local（LocalHFClient 工厂可创建）。
  [P5] 真机评测开关   ：make_executor 可切 sim / mock_cloud / smartthings / homeassistant。
  [P6] 3D 可视化接口  ：Scene.to_json 导出含房间/设备/坐标/锚点；live 状态可叠加。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeclaw import data_paths  # noqa: E402
from homeclaw.config import LLMConfig  # noqa: E402
from homeclaw.llm import create_llm_client, LocalHFClient, MockLLMClient  # noqa: E402
from homeclaw.executor import make_executor, SimulateExecutor, BACKENDS  # noqa: E402
from homeclaw.scene import (  # noqa: E402
    build_homebench_scene, build_sage_scene, coverage_report,
    scene_device_fullnames, SAGE_REQUIRED_DEVICES,
)
from homeclaw.scene.schema import Scene  # noqa: E402
from homeclaw.tools import (  # noqa: E402
    MemoryBank, UserProfileTool, KeywordRetriever, EmbeddingRetriever,
)
from homeclaw.devices.device import device_map  # noqa: E402


def _assert(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        raise AssertionError(msg)


# ============================================================================ #
# P1 数据自包含
# ============================================================================ #
def test_p1_data_self_contained():
    print("[P1] 数据自包含 / 去跨项目引用")
    # HomeBench 数据文件在包内
    test_file = data_paths.homebench_split_file("test")
    _assert(os.path.isfile(test_file), f"HomeBench test_data.jsonl 在包内存在: {test_file}")
    _assert(os.path.isfile(data_paths.HOMEBENCH_HOME_STATUS_METHOD),
            "home_status_method.jsonl 在包内存在")
    # SAGE 数据在包内
    _assert(os.path.isfile(data_paths.SAGE_MEMORY_BANK), "SAGE memory_bank.json 在包内存在")
    _assert(len(data_paths.list_sage_users()) >= 1, "SAGE user_info 至少收录 1 个用户")

    # data_paths 解析出的路径都落在 HomeClaw 项目内（无 ../HomeBench、../SAGE 跨项目引用）
    project_root = data_paths.PROJECT_ROOT
    for p in (data_paths.DATA_DIR, data_paths.HOMEBENCH_DIR, data_paths.SAGE_DIR):
        real = os.path.realpath(p)
        _assert(real.startswith(os.path.realpath(project_root)),
                f"路径落在 HomeClaw 项目内（非跨项目）: {p}")
        _assert("HomeBench" + os.sep not in real or real.startswith(os.path.realpath(project_root)),
                "无 ../HomeBench 跨项目引用")

    # 源码层面：homeclaw 包内不再有跨项目路径。用 AST 只检查**字符串常量**里是否出现
    # "../HomeBench" 或把 "HomeBench"/"SAGE" 当作路径片段拼接；docstring/注释里的说明性
    # 文字（如"已去除 ../HomeBench 引用"）不算违规——因为 ast 遍历时 docstring 也是字符串
    # 常量，为避免误伤，只在**赋值/函数调用参数**语境里出现的路径片段才判违规。
    import ast

    pkg_dir = data_paths.PACKAGE_ROOT
    bad = []

    class _PathVisitor(ast.NodeVisitor):
        def __init__(self, path):
            self.path = path

        def _check_str(self, s, lineno):
            if not isinstance(s, str):
                return
            if "../HomeBench" in s or "..\\HomeBench" in s:
                bad.append(f"{self.path}:{lineno} 相对跨项目路径 {s!r}")

        def visit_Call(self, node):
            # os.path.join("...", "HomeBench", ...) 之类的路径拼接
            func = node.func
            is_join = (isinstance(func, ast.Attribute) and func.attr == "join")
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if is_join and arg.value in ("HomeBench", "SAGE"):
                        bad.append(f"{self.path}:{node.lineno} join 拼接 {arg.value!r}")
                    self._check_str(arg.value, arg.lineno)
            self.generic_visit(node)

        def visit_Assign(self, node):
            if isinstance(node.value, ast.Constant):
                self._check_str(node.value.value, node.lineno)
            self.generic_visit(node)

    for root, _dirs, files in os.walk(pkg_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fp)
            _PathVisitor(fp).visit(tree)
    _assert(not bad, f"包内无跨项目路径拼接（命中: {bad}）")

    # 真加载一批 HomeBench 样本，确认包内路径可用
    from homeclaw.eval import load_homebench_dataset
    samples, home_index = load_homebench_dataset(limit=5)
    _assert(len(samples) == 5 and len(home_index) > 0, "包内路径可加载 HomeBench 样本")


# ============================================================================ #
# P2 场景层 + SAGE 设备类
# ============================================================================ #
def test_p2_scene_and_sage_devices():
    print("[P2] 场景层 + SAGE 设备类")
    hb = build_homebench_scene()
    _assert(len(hb.rooms) == 12, "HomeBench 场景 12 房间")
    _assert(hb.get_room("living_room") is not None, "含 living_room")

    # SAGE 场景全量覆盖（本轮重点：从"子集"升级为"全量"）
    rep = coverage_report()
    print(f"      SAGE 场景覆盖: {len(rep['covered'])}/{len(SAGE_REQUIRED_DEVICES)} "
          f"missing={rep['missing']}")
    _assert(rep["full"] is True,
            f"SAGE 场景全量覆盖官方 testcases 8 台真实设备（缺失: {rep['missing']}）")

    # SAGE 特有设备类已进 device_map
    for dt in ("tv", "frame_tv", "fridge", "dishwasher"):
        _assert(dt in device_map, f"SAGE 设备类型已注册: {dt}")

    # SAGE 场景可转为可执行的 home_status，并真正跑一个动作
    sage = build_sage_scene()
    home = sage.to_home_status()
    ex = SimulateExecutor(home)
    ex.execute("living_room.tv.turn_on()")
    _assert(ex.snapshot()["living_room"]["tv"]["state"] == "on",
            "SAGE 场景设备可被 SimulateExecutor 执行")

    # 实景锚点（SAGE 特征）：两台 TV 能靠 credenza/plant 锚点区分
    names = scene_device_fullnames(sage)
    _assert("living_room.tv" in names and "living_room.frame_tv" in names,
            "两台 TV 都在场景中（credenza / plant 锚点区分）")


# ============================================================================ #
# P3 SAGE 工具补齐（个性化核心）
# ============================================================================ #
def test_p3_sage_tools():
    print("[P3] SAGE 工具：MemoryBank / UserProfileTool / 可插拔检索器")
    mb = MemoryBank("amal")
    _assert(len(mb.all_entries()) > 0, "MemoryBank 从包内 SAGE 数据加载到历史记忆")
    # auto 策略：装了 sentence-transformers 则自动语义向量检索，否则关键词降级。
    # 两种后端都合法，但必须能如实报告（供论文方法学标注）。
    _assert(mb.retriever_kind in ("keyword", "embedding"),
            f"MemoryBank auto 检索后端可如实报告：{mb.retriever_kind}"
            f"（semantic={mb.is_semantic}）")
    if mb.retriever_kind == "keyword":
        print("    [注意] 未装 sentence-transformers，记忆检索为关键词降级版，"
              "与 SAGE 对比时须在方法学中标注")
    hits = mb.retrieve("recommend a horror movie", k=3)
    _assert(any("horror" in h["text"].lower() for h in hits),
            "检索能召回含 horror 的历史记忆")

    # UserProfileTool 个性化召回
    up = UserProfileTool("amal")
    ctx = up.personalization_context("what should I watch tonight")
    _assert("<user_profile>" in ctx, "UserProfileTool 产出个性化上下文段")

    # 可插拔向量检索器：注入一个玩具 embedding（词袋向量），验证 EmbeddingRetriever 生效
    vocab = {}

    def toy_embed(texts):
        # 先扩充词表
        for t in texts:
            for w in t.lower().split():
                vocab.setdefault(w, len(vocab))
        dim = max(len(vocab), 1)
        out = []
        for t in texts:
            v = [0.0] * dim
            for w in t.lower().split():
                v[vocab[w]] += 1.0
            out.append(v)
        return out

    mb_vec = MemoryBank.with_embedding(toy_embed, user="amal")
    _assert(mb_vec.is_semantic is True and mb_vec.retriever_kind == "embedding",
            "MemoryBank.with_embedding 切到语义向量检索器")
    vhits = mb_vec.retrieve("horror movie", k=3)
    _assert(len(vhits) > 0, "向量检索器可返回结果（论文对比用真实向量替换 toy_embed 即可）")
    _assert(isinstance(mb_vec.retriever, EmbeddingRetriever), "检索器实例为 EmbeddingRetriever")


# ============================================================================ #
# P4 本地模型入口
# ============================================================================ #
def test_p4_local_model_entry():
    print("[P4] 本地模型入口")
    # 不实际加载权重（无 transformers 也应能构造工厂对象，惰性依赖）
    client = create_llm_client(LLMConfig(provider="local", model="dummy-local"))
    _assert(isinstance(client, LocalHFClient), "provider=local 返回 LocalHFClient")
    # mock 仍可用（离线默认路径）
    _assert(isinstance(create_llm_client(LLMConfig(provider="mock")), MockLLMClient),
            "provider=mock 返回 MockLLMClient")
    # openai_compatible（本地 vLLM/Ollama 走 base_url）工厂可创建
    oc = create_llm_client(LLMConfig(provider="openai_compatible", base_url="http://localhost:8000/v1"))
    _assert(oc is not None, "provider=openai_compatible 支持 base_url（本地 vLLM/Ollama）")


# ============================================================================ #
# P5 真机评测开关
# ============================================================================ #
def test_p5_real_device_switch():
    print("[P5] 真机评测开关（executor 后端可切）")
    home = build_sage_scene().to_home_status()
    for backend in ("sim", "mock_cloud"):
        _assert(backend in BACKENDS, f"后端已注册: {backend}")
        ex = make_executor(backend, home_status=home)
        _assert(ex is not None, f"make_executor('{backend}') 可创建（离线可复现）")
    # smartthings / homeassistant 后端登记在册（需凭证，不实连）
    _assert("smartthings" in BACKENDS and "homeassistant" in BACKENDS,
            "真机后端 smartthings / homeassistant 已登记")


# ============================================================================ #
# P6 3D 可视化数据接口
# ============================================================================ #
def test_p6_scene_export():
    print("[P6] 3D 可视化 JSON 导出")
    sage = build_sage_scene()
    data = sage.to_json()
    _assert(data["source"] == "sage" and len(data["rooms"]) >= 4, "导出含 source 与房间列表")
    # 每个房间/设备都有 3D 坐标；设备带 anchors（SAGE 空间锚点，供 3D 打标签）
    dev_count = 0
    anchored = 0
    for room in data["rooms"]:
        _assert(len(room["pos"]) == 3 and len(room["size"]) == 3, "房间含 pos/size 3D 字段")
        for dev in room["devices"]:
            _assert(len(dev["pos"]) == 3, "设备含 3D 坐标 pos")
            _assert("anchors" in dev, "设备导出含 anchors 字段")
            dev_count += 1
            if dev["anchors"]:
                anchored += 1
    _assert(dev_count > 0 and anchored > 0, "至少部分设备带实景锚点（SAGE 特征）")

    # live 状态叠加：执行动作后导出带 live_state
    home = sage.to_home_status()
    ex = SimulateExecutor(home)
    ex.execute("living_room.tv.turn_on()")
    live = sage.to_json(live_status=ex.snapshot())
    tv = None
    for room in live["rooms"]:
        if room["name"] == "living_room":
            for dev in room["devices"]:
                if dev["name"] == "tv":
                    tv = dev
    _assert(tv is not None and tv["live_state"] == "on",
            "导出可叠加 executor 实时状态（P7 3D 演示用）")


def main():
    print("== P1~P6 冒烟测试：六阶段交付回归 ==\n")
    test_p1_data_self_contained()
    test_p2_scene_and_sage_devices()
    test_p3_sage_tools()
    test_p4_local_model_entry()
    test_p5_real_device_switch()
    test_p6_scene_export()
    print("\n== 全部 P1~P6 冒烟用例通过 ==")


if __name__ == "__main__":
    main()
