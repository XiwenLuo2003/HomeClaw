"""SAGE 五维评测适配器（M3）。

复用 SAGE 的评测思想（装饰器声明式注册 @register + 五维难度标签 + 集合交并筛选），
但**去除 MongoDB / SmartThings 依赖**：改用 HomeClaw 的 SimulateExecutor 内存仿真做状态断言。

五维标签：
  - personalization / intent_resolution / device_resolution
  - persistence / command_chaining
  - simple（基线）

每个测试用例是一个函数 (coordinator) -> TestCaseResult，用 @register([...]) 登记。
用例内部：设初态(构造 home_status) → coordinator.execute(command) → 断言执行后状态/动作。

新增维度（设计文档 03 §3）：过度执行率 / 正确拒答率 / 平均 LLM 调用轮数 / 平均 token。
这些指标在 run_dimension() 聚合时从每个 ExecuteResult 的 actions/iters/usage 统计。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List

from homeclaw.executor import SimulateExecutor


# 五维 + 基线 标签注册中心
TEST_REGISTER: Dict[str, set] = {
    "personalization": set(),
    "intent_resolution": set(),
    "device_resolution": set(),
    "persistence": set(),
    "command_chaining": set(),
    "simple": set(),
}


def register(names: List[str]):
    """把测试用例登记到对应难度桶（对齐 SAGE @register）。"""
    def wrapper(fn):
        for name in names:
            TEST_REGISTER.setdefault(name, set()).add(fn)
        return fn
    return wrapper


def get_tests(class_list: List[str], combination: str = "union") -> List[Callable]:
    """按标签交/并集筛选用例（对齐 SAGE get_tests）。"""
    _ensure_cases_loaded()
    if not class_list:
        return []
    tests = set(TEST_REGISTER.get(class_list[0], set()))
    for c in class_list[1:]:
        s = TEST_REGISTER.get(c, set())
        tests = tests.union(s) if combination == "union" else tests.intersection(s)
    return list(tests)


def _ensure_cases_loaded() -> None:
    """惰性导入 sage_cases 触发 @register（避免模块级循环导入）。"""
    import importlib
    importlib.import_module("homeclaw.eval.sage_cases")


@dataclass
class TestCaseResult:
    name: str
    passed: bool
    detail: str = ""
    # 从 ExecuteResult 采集的效率/鲁棒性原始量
    n_actions: int = 0
    n_over: int = 0          # 过度执行的动作数（相对期望）
    rejected: bool = False   # 是否发生拒答
    should_reject: bool = False
    iters: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0   # 【M4】端到端耗时


@dataclass
class DimensionResult:
    dimension: str = ""
    system_name: str = ""
    total: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    over_execution_rate: float = 0.0
    correct_rejection_rate: float = 0.0
    avg_iters: float = 0.0
    avg_prompt_tokens: float = 0.0
    avg_completion_tokens: float = 0.0
    avg_latency_ms: float = 0.0   # 【M4】平均端到端耗时


# ---------------------------------------------------------------------------- #
# 用例集在 homeclaw.eval.sage_cases 中定义（M6：从 SAGE 官方 testcases 迁移多用例）。
# 通过 _ensure_cases_loaded() 惰性导入触发 @register，避免模块级循环导入。
# ---------------------------------------------------------------------------- #
class SageEvalAdapter:
    """驱动 Coordinator 做五维 + 新增维度评测。"""

    def __init__(self):
        _ensure_cases_loaded()

    def run_dimension(self, coordinator, dimension: str, system_name: str = "") -> DimensionResult:
        """跑某一维度下的全部用例，聚合通过率与新增维度指标。"""
        tests = get_tests([dimension])
        results: List[TestCaseResult] = [t(coordinator) for t in tests]
        return self._aggregate(dimension, system_name, results)

    def run_all(self, coordinator, system_name: str = "") -> Dict[str, DimensionResult]:
        """跑所有维度，返回 {dimension: DimensionResult}。"""
        out: Dict[str, DimensionResult] = {}
        for dim in TEST_REGISTER:
            if TEST_REGISTER[dim]:
                out[dim] = self.run_dimension(coordinator, dim, system_name)
        return out

    @staticmethod
    def _aggregate(dimension, system_name, results: List[TestCaseResult]) -> DimensionResult:
        n = len(results)
        if n == 0:
            return DimensionResult(dimension=dimension, system_name=system_name)
        passed = sum(1 for r in results if r.passed)
        over = sum(1 for r in results if r.n_over > 0)
        need_reject = [r for r in results if r.should_reject]
        reject_ok = sum(1 for r in need_reject if r.rejected)
        return DimensionResult(
            dimension=dimension,
            system_name=system_name,
            total=n,
            passed=passed,
            pass_rate=passed / n,
            over_execution_rate=over / n,
            correct_rejection_rate=(reject_ok / len(need_reject)) if need_reject else 0.0,
            avg_iters=sum(r.iters for r in results) / n,
            avg_prompt_tokens=sum(r.prompt_tokens for r in results) / n,
            avg_completion_tokens=sum(r.completion_tokens for r in results) / n,
            avg_latency_ms=sum(r.latency_ms for r in results) / n,
        )

    @staticmethod
    def render(rows: Dict[str, DimensionResult], system_name: str = "") -> str:
        header = (f"{'dimension':<20}{'n':>5}{'pass':>6}{'rate':>8}"
                  f"{'overExe':>9}{'rejOK':>8}{'iters':>7}{'pTok':>8}{'cTok':>7}{'ms':>8}")
        lines = [f"== SAGE 五维 + 新增维度 · {system_name} ==", header, "-" * len(header)]
        for dim, r in rows.items():
            lines.append(
                f"{dim:<20}{r.total:>5}{r.passed:>6}{r.pass_rate:>8.3f}"
                f"{r.over_execution_rate:>9.3f}{r.correct_rejection_rate:>8.3f}"
                f"{r.avg_iters:>7.2f}{r.avg_prompt_tokens:>8.1f}{r.avg_completion_tokens:>7.1f}"
                f"{r.avg_latency_ms:>8.2f}"
            )
        return "\n".join(lines)
