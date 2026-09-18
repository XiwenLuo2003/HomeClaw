"""eval 包（M3）：评测指标 + 双适配器。"""
from homeclaw.eval.metrics import (
    compute_metrics,
    normalize_output,
    MetricResult,
    format_metric_table,
)
from homeclaw.eval.homebench_adapter import (
    HomeBenchEvalAdapter,
    HomeBenchEvalResult,
    load_homebench_dataset,
    classify_type,
    SIX_TYPES,
)
from homeclaw.eval.sage_adapter import (
    SageEvalAdapter,
    DimensionResult,
    TestCaseResult,
    register,
    get_tests,
    TEST_REGISTER,
)
# 触发五维用例注册（M6：从 SAGE 官方 testcases 迁移的多用例集）
from homeclaw.eval import sage_cases as _sage_cases  # noqa: F401

__all__ = [
    "compute_metrics", "normalize_output", "MetricResult", "format_metric_table",
    "HomeBenchEvalAdapter", "HomeBenchEvalResult", "load_homebench_dataset",
    "classify_type", "SIX_TYPES",
    "SageEvalAdapter", "DimensionResult", "TestCaseResult",
    "register", "get_tests", "TEST_REGISTER",
]
