"""HomeBench 幻觉评测适配器（M3）。

职责：
  1. 加载 HomeBench 数据集（test_data.jsonl + home_status_method.jsonl），去硬编码路径；
  2. 按 home_id 关联 home_status / method；
  3. 驱动任一 Coordinator 的 predict_actions() 产出动作文本；
  4. 按六型（normal / unexist_device / unexist_attribute / *_normal / *_error / *_mix）
     分型统计 EM/P/R/F1 + 新增维度。

对齐 HomeBench code/eval.py 的 dif_type 分型逻辑与 compute_accuracy 指标。
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from homeclaw import data_paths
from homeclaw.eval.metrics import compute_metrics, MetricResult, format_metric_table


# HomeBench 数据集默认位置：统一走 data_paths（包内 data/homebench），
# 彻底去除跨项目 ../HomeBench 引用。可被 dataset_dir 参数或环境变量覆盖。
_DEFAULT_DATASET_DIR = data_paths.HOMEBENCH_DIR


def classify_type(raw_type: str) -> str:
    """把数据集的 type 字段映射为六型标签。

    - "normal"              → normal_single
    - "unexist_device"      → unexist_device
    - "unexist_attribute"   → unexist_attribute
    - "multiN_normal"       → normal_multi
    - "multiN_error"        → error_multi
    - "multiN_mix"          → mix_multi
    """
    if raw_type == "normal":
        return "normal_single"
    if raw_type in ("unexist_device", "unexist_attribute"):
        return raw_type
    tail = raw_type.split("_")[-1]
    if tail == "mix":
        return "mix_multi"
    if tail == "normal":
        return "normal_multi"
    return "error_multi"


SIX_TYPES = [
    "normal_single", "unexist_device", "unexist_attribute",
    "normal_multi", "error_multi", "mix_multi",
]


@dataclass
class HomeBenchSample:
    id: str
    instruction: str
    gold_output: str
    home_id: int
    type6: str


def load_homebench_dataset(
    dataset_dir: Optional[str] = None,
    split: str = "test",
    limit: Optional[int] = None,
    sample: Optional[int] = None,
    seed: int = 42,
) -> "tuple[List[HomeBenchSample], Dict[int, Dict]]":
    """加载 HomeBench 数据集。

    参数：
      split  : 数据划分（test / valid / train_part1 / train_part2）。
      limit  : 顺序截断——只取前 N 条（None=全部）。
      sample : 随机抽样——从全量随机抽 N 条（数据集庞大时快速看效果）。
      seed   : 随机抽样种子，保证可复现。
      注：limit 与 sample 同时给出时，以 sample（随机抽样）优先。

    返回 (samples, home_index)，home_index[home_id] = {"home_status":..., "method":...}
    """
    # dataset_dir=None：走 data_paths 包内路径（数据自包含）；
    # 传入 dataset_dir 时：兼容旧调用，从该目录取 {split}_data.jsonl 与 home_status_method.jsonl。
    if dataset_dir is None:
        data_file = data_paths.homebench_split_file(split)
        home_file = data_paths.HOMEBENCH_HOME_STATUS_METHOD
    else:
        data_file = os.path.join(dataset_dir, f"{split}_data.jsonl")
        home_file = os.path.join(dataset_dir, "home_status_method.jsonl")

    home_index: Dict[int, Dict] = {}
    with open(home_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            home_index[d["home_id"]] = {
                "home_status": d["home_status"],
                "method": d["method"],
            }

    # sample（随机抽样）优先：需先读全量再抽；否则 limit 边读边截断省内存。
    all_rows: List[HomeBenchSample] = []
    with open(data_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if sample is None and limit is not None and i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            all_rows.append(HomeBenchSample(
                id=d["id"],
                instruction=d["input"],
                gold_output=d["output"],
                home_id=d["home_id"],
                type6=classify_type(d["type"]),
            ))

    if sample is not None and sample < len(all_rows):
        rng = random.Random(seed)
        samples = rng.sample(all_rows, sample)
    else:
        samples = all_rows
    return samples, home_index


@dataclass
class HomeBenchEvalResult:
    system_name: str = ""
    overall: MetricResult = field(default_factory=MetricResult)
    by_type: Dict[str, MetricResult] = field(default_factory=dict)
    raw: List[Dict] = field(default_factory=list)  # 每条 {id, type, generated, gold}


class HomeBenchEvalAdapter:
    """驱动某个 Coordinator 在 HomeBench 数据集上做幻觉评测。"""

    def __init__(
        self,
        dataset_dir: Optional[str] = None,
        split: str = "test",
        limit: Optional[int] = None,
        sample: Optional[int] = None,
        seed: int = 42,
    ):
        self.samples, self.home_index = load_homebench_dataset(
            dataset_dir, split, limit, sample=sample, seed=seed,
        )

    def evaluate(self, coordinator, system_name: str = "") -> HomeBenchEvalResult:
        """coordinator 需实现 predict_actions(home_status, instruction, methods)。"""
        buckets: Dict[str, Dict[str, List[str]]] = {
            t: {"gen": [], "gold": []} for t in SIX_TYPES
        }
        all_gen: List[str] = []
        all_gold: List[str] = []
        raw: List[Dict] = []

        for s in self.samples:
            home = self.home_index.get(s.home_id, {})
            generated = coordinator.predict_actions(
                home.get("home_status", {}), s.instruction, home.get("method"),
            )
            buckets[s.type6]["gen"].append(generated)
            buckets[s.type6]["gold"].append(s.gold_output)
            all_gen.append(generated)
            all_gold.append(s.gold_output)
            raw.append({"id": s.id, "type": s.type6, "generated": generated, "gold": s.gold_output})

        by_type = {
            t: compute_metrics(b["gen"], b["gold"])
            for t, b in buckets.items() if b["gen"]
        }
        overall = compute_metrics(all_gen, all_gold)
        return HomeBenchEvalResult(system_name=system_name, overall=overall,
                                   by_type=by_type, raw=raw)

    @staticmethod
    def render(result: HomeBenchEvalResult) -> str:
        rows = {"OVERALL": result.overall}
        rows.update(result.by_type)
        return format_metric_table(rows, title=f"HomeBench 幻觉评测 · {result.system_name}")
