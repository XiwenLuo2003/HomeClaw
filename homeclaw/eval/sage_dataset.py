"""SAGE 数据加载层（P1）：从包内 data/sage 读取用户画像与记忆库。

职责（数据自包含，零跨项目引用）：
  1. 读取 SAGE 用户偏好 user_preferences.jsonl（个性化维度的真实依据）；
  2. 读取 SAGE 记忆库 memory_bank.json（历史对话 + profile）；
  3. 归一化为 HomeClaw 内部结构，供 UserProfileTool / MemoryBank（P3）使用。

注意：SAGE 原始断言依赖 SmartThings/MongoDB，本层只抽取"画像/记忆"这类
与执行后端无关的纯数据；用例的状态断言在 sage_cases.py 中统一走 SimulateExecutor。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from homeclaw import data_paths


def load_user_preferences(user):
    """读取某用户的偏好（user_preferences.jsonl 的首行 JSON）。找不到返回 {}。"""
    path = data_paths.sage_user_preferences_file(user)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                return json.loads(line)
    return {}


def load_memory_bank(large=False):
    """读取 SAGE 记忆库（memory_bank.json 或 large_memory_bank.json）。"""
    path = data_paths.SAGE_LARGE_MEMORY_BANK if large else data_paths.SAGE_MEMORY_BANK
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_manual_memories():
    """读取人工整理的记忆条目 manual_memories.json。"""
    path = data_paths.SAGE_MANUAL_MEMORIES
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_user_profile(user):
    """汇总某用户画像：偏好 JSON + 记忆库 profile/history（若存在）。

    返回 {"preferences": {...}, "profile": {...}, "history": {...}}。
    """
    prefs = load_user_preferences(user)
    mem = load_memory_bank()
    entry = mem.get(user, {}) if isinstance(mem, dict) else {}
    profile = {}
    raw_profile = entry.get("profile")
    if isinstance(raw_profile, str):
        try:
            profile = json.loads(raw_profile)
        except Exception:
            profile = {}
    elif isinstance(raw_profile, dict):
        profile = raw_profile
    return {
        "preferences": prefs,
        "profile": profile,
        "history": entry.get("history", {}),
    }


def list_users():
    """列出所有已收录的 SAGE 用户。"""
    return data_paths.list_sage_users()
