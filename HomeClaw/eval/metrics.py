"""评测指标（M3）。

严格对齐 HomeBench code/eval.py 的 compute_accuracy 算法：
  - 归一化：去空格/换行、提取 {} 内内容、按逗号切分、去空项；
  - EM       : 生成与期望的 multiset（Counter）完全相等的比例；
  - Precision: tp / all_pre
  - Recall   : tp / all_gold
  - F1       : 2PR/(P+R)
其中 tp = sum((generated_counter & expected_counter).elements())

同时提供 HomeClaw 新增的评测维度（新增维度评测板块，见设计文档 03 §3）：
  - error_input 准确率（对非法项正确拒答）
  - 过度执行率 / 正确拒答率
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List


_BRACE_RE = re.compile(r"\{(.*?)\}")


def normalize_output(text: str) -> List[str]:
    """把一条模型输出/期望输出归一化为动作 token 列表。

    对齐 HomeBench：去空格/换行 → 提取 {} 内内容（多个则逗号连接）→ split(',') → 去空。
    对期望输出额外去除 ''' 包裹。
    """
    if text is None:
        text = ""
    text = text.replace("'''", "")
    text = text.replace(" ", "").replace("\n", "")

    matches = _BRACE_RE.findall(text)
    if len(matches) > 1:
        body = ",".join(matches)
    elif len(matches) == 1:
        body = matches[0]
    else:
        # 无花括号：直接用清洗后的整串（期望输出通常无花括号）
        body = text
    items = [x for x in body.split(",") if x != ""]
    return items


@dataclass
class MetricResult:
    """一组样本的评测指标。"""

    n: int = 0
    em: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    # 新增维度
    error_input_accuracy: float = 0.0   # 对非法项(error_input)正确输出的比例
    over_execution_rate: float = 0.0     # 过度执行率：生成中多于期望的动作占比
    correct_rejection_rate: float = 0.0  # 正确拒答率：应拒答且拒答的比例

    def as_dict(self) -> Dict[str, float]:
        return {
            "n": self.n, "em": self.em, "precision": self.precision,
            "recall": self.recall, "f1": self.f1,
            "error_input_accuracy": self.error_input_accuracy,
            "over_execution_rate": self.over_execution_rate,
            "correct_rejection_rate": self.correct_rejection_rate,
        }


def compute_metrics(generated_texts: List[str], expected_texts: List[str]) -> MetricResult:
    """计算 EM/P/R/F1 + 新增维度。generated/expected 为原始文本列表。"""
    if not generated_texts:
        return MetricResult()

    correct_num = 0
    tp = 0
    all_pre = 0
    all_gold = 0

    # 新增维度累计
    gold_error_total = 0     # 期望中 error_input 的总数
    gold_error_hit = 0       # 其中被正确输出 error_input 的数
    over_exec_cases = 0      # 生成动作数 > 期望动作数 的样本数
    reject_needed = 0        # 期望里含 error_input 的样本数
    reject_correct = 0       # 其中生成也含（足量）error_input 的样本数

    for gen, exp in zip(generated_texts, expected_texts):
        g = normalize_output(gen)
        e = normalize_output(exp)
        gc, ec = Counter(g), Counter(e)

        if gc == ec:
            correct_num += 1
        inter = gc & ec
        tp += sum(inter.values())
        all_pre += len(g)
        all_gold += len(e)

        # error_input 维度
        gold_err = ec.get("error_input", 0)
        gen_err = gc.get("error_input", 0)
        gold_error_total += gold_err
        gold_error_hit += min(gold_err, gen_err)

        # 过度执行
        if len(g) > len(e):
            over_exec_cases += 1

        # 拒答
        if gold_err > 0:
            reject_needed += 1
            if gen_err >= gold_err:
                reject_correct += 1

    n = len(generated_texts)
    precision = tp / all_pre if all_pre else 0.0
    recall = tp / all_gold if all_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return MetricResult(
        n=n,
        em=correct_num / n,
        precision=precision,
        recall=recall,
        f1=f1,
        error_input_accuracy=(gold_error_hit / gold_error_total) if gold_error_total else 0.0,
        over_execution_rate=over_exec_cases / n,
        correct_rejection_rate=(reject_correct / reject_needed) if reject_needed else 0.0,
    )


def format_metric_table(rows: Dict[str, MetricResult], title: str = "") -> str:
    """把 {系统名或类型名: MetricResult} 渲染为对齐的文本表。"""
    header = f"{'name':<20}{'n':>6}{'EM':>8}{'P':>8}{'R':>8}{'F1':>8}{'errAcc':>8}{'overExe':>9}{'rejOK':>8}"
    lines = []
    if title:
        lines.append(f"== {title} ==")
    lines.append(header)
    lines.append("-" * len(header))
    for name, m in rows.items():
        lines.append(
            f"{name:<20}{m.n:>6}{m.em:>8.3f}{m.precision:>8.3f}{m.recall:>8.3f}"
            f"{m.f1:>8.3f}{m.error_input_accuracy:>8.3f}{m.over_execution_rate:>9.3f}"
            f"{m.correct_rejection_rate:>8.3f}"
        )
    return "\n".join(lines)
