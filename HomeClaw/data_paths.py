"""HomeClaw 数据路径统一配置模块（P1）。

设计目标：杜绝任何硬编码路径与跨项目 ../HomeBench、../SAGE 引用。
所有数据文件都已拷贝进 HomeClaw 包内的 data/ 目录，实现独立项目、数据自包含。

任何模块（homebench_adapter / sage_cases / sage_dataset / run_experiment /
cloud_adapter 等）需要读数据文件时，一律 import 本模块的常量或函数。

环境变量覆盖（可选）：
    HOMECLAW_DATA_DIR / HOMECLAW_HOMEBENCH_DIR / HOMECLAW_SAGE_DIR / HOMECLAW_RUNTIME_DIR
"""
from __future__ import annotations

import os

# 根目录锚点：本文件位于 HomeClaw/homeclaw/data_paths.py
PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_ROOT)


def _env_or(default, *env_keys):
    """若任一环境变量已设置则用之，否则用 default。"""
    for k in env_keys:
        v = os.getenv(k)
        if v:
            return v
    return default


# 数据根目录
DATA_DIR = _env_or(os.path.join(PROJECT_ROOT, "data"), "HOMECLAW_DATA_DIR")
HOMEBENCH_DIR = _env_or(os.path.join(DATA_DIR, "homebench"), "HOMECLAW_HOMEBENCH_DIR")
SAGE_DIR = _env_or(os.path.join(DATA_DIR, "sage"), "HOMECLAW_SAGE_DIR")
SAGE_USER_INFO_DIR = os.path.join(SAGE_DIR, "user_info")
SAGE_MEMORY_DIR = os.path.join(SAGE_DIR, "memory")
RUNTIME_DIR = _env_or(os.path.join(PROJECT_ROOT, "runtime"), "HOMECLAW_RUNTIME_DIR")

# 本地开源模型权重目录（download_models.py 下载到此；对齐 HomeBench 本地部署路径）
MODELS_DIR = _env_or(os.path.join(PROJECT_ROOT, "models"), "HOMECLAW_MODELS_DIR")


def local_model_path(name_or_path):
    """把 --model 值解析为可加载的本地权重路径或 HF repo id。

 解析优先级（对齐 download_models.py 的 sub_dir 布局）：
      1) 若是已存在的目录（绝对/相对路径）→ 原样返回；
      2) 若 models/<name> 存在（download_models.py 下载的 sub_dir）→ 返回该本地目录；
      3) 否则原样返回（视为 HF repo id，如 "Qwen/Qwen2.5-7B-Instruct"，联网加载）。
    """
    if not name_or_path:
        return name_or_path
    if os.path.isdir(name_or_path):
        return name_or_path
    candidate = os.path.join(MODELS_DIR, name_or_path)
    if os.path.isdir(candidate):
        return candidate
    return name_or_path

# HomeBench 数据集文件
HOMEBENCH_HOME_STATUS_METHOD = os.path.join(HOMEBENCH_DIR, "home_status_method.jsonl")


def homebench_split_file(split="test"):
    """返回 HomeBench 某个 split 的数据文件路径。"""
    mapping = {
        "test": "test_data.jsonl",
        "valid": "valid_data.jsonl",
        "train_part1": "train_data_part1.jsonl",
        "train_part2": "train_data_part2.jsonl",
    }
    fname = mapping.get(split, "%s_data.jsonl" % split)
    return os.path.join(HOMEBENCH_DIR, fname)


# SAGE 数据文件
SAGE_MEMORY_BANK = os.path.join(SAGE_MEMORY_DIR, "memory_bank.json")
SAGE_LARGE_MEMORY_BANK = os.path.join(SAGE_MEMORY_DIR, "large_memory_bank.json")
SAGE_MANUAL_MEMORIES = os.path.join(SAGE_MEMORY_DIR, "manual_memories.json")


def sage_user_preferences_file(user):
    """返回某个 SAGE 用户的偏好文件路径（如 amal / abhisek / dmitriy）。"""
    return os.path.join(SAGE_USER_INFO_DIR, user, "user_preferences.jsonl")


def list_sage_users():
    """列出 data/sage/user_info 下所有已收录的用户名。"""
    if not os.path.isdir(SAGE_USER_INFO_DIR):
        return []
    return sorted(
        d for d in os.listdir(SAGE_USER_INFO_DIR)
        if os.path.isdir(os.path.join(SAGE_USER_INFO_DIR, d))
    )


# 设备映射默认落盘文件（SmartThingsAdapter 的 room.device -> device_id 映射）
DEVICE_MAP_FILE = os.path.join(RUNTIME_DIR, "device_map.json")


def runtime_path(*parts):
    """拼接运行期落盘路径，并确保其父目录存在。"""
    p = os.path.join(RUNTIME_DIR, *parts)
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return p


def ensure_dirs():
    """确保所有数据/运行期目录存在。"""
    for d in (DATA_DIR, HOMEBENCH_DIR, SAGE_DIR, SAGE_USER_INFO_DIR,
              SAGE_MEMORY_DIR, RUNTIME_DIR):
        os.makedirs(d, exist_ok=True)


def describe():
    """返回一段人类可读的路径清单（用于自检/日志）。"""
    lines = [
        "HomeClaw 数据路径配置：",
        "  PROJECT_ROOT       = %s" % PROJECT_ROOT,
        "  DATA_DIR           = %s" % DATA_DIR,
        "  HOMEBENCH_DIR      = %s" % HOMEBENCH_DIR,
        "  SAGE_DIR           = %s" % SAGE_DIR,
        "  SAGE_USER_INFO_DIR = %s" % SAGE_USER_INFO_DIR,
        "  SAGE_MEMORY_DIR    = %s" % SAGE_MEMORY_DIR,
        "  RUNTIME_DIR        = %s" % RUNTIME_DIR,
        "  SAGE users         = %s" % list_sage_users(),
    ]
    return "\n".join(lines)
