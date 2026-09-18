"""动作文本解析器（M2）。

将 LLM 产出的动作文本解析为结构化调用要素：
    "balcony.light.set_brightness(40)" → ParsedAction(room, device, op, args)
    "media_player.play()"（无房间前缀，room=None）
    "error_input"                     → None（幻觉拒答标记）

参数类型推断规则：
- 纯数字            → int
- 形如 (r,g,b)      → tuple(int,...)（颜色）
- 其余             → str（去除包裹引号）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


class ActionParseError(ValueError):
    """动作文本无法解析为合法结构时抛出。"""


# room.device.op(args) 或 device.op(args)（无房间）
_ACTION_RE = re.compile(
    r"^\s*(?:(?P<room>[\w ]+)\.)?(?P<device>[\w ]+)\.(?P<op>[\w ]+)\((?P<args>.*)\)\s*$",
    re.S,
)
# 颜色/元组：(a, b, c)
_TUPLE_RE = re.compile(r"^\((.*)\)$")


@dataclass
class ParsedAction:
    room: Optional[str]
    device: str
    op: str
    args: List[object] = field(default_factory=list)
    raw: str = ""


def _coerce_arg(token: str) -> object:
    """把单个参数字符串推断为 int / str。"""
    token = token.strip()
    # 去除包裹引号
    if len(token) >= 2 and token[0] in "\"'" and token[-1] == token[0]:
        return token[1:-1]
    if re.fullmatch(r"[-+]?\d+", token):
        return int(token)
    if re.fullmatch(r"[-+]?\d*\.\d+", token):
        return float(token)
    return token


def _parse_args(arg_str: str) -> List[object]:
    """解析括号内的参数串，支持元组 (r,g,b) 作为单个参数。"""
    arg_str = arg_str.strip()
    if arg_str == "":
        return []

    # 元组参数（颜色）：整个 args 形如 (255,255,255)
    m = _TUPLE_RE.match(arg_str)
    if m:
        inner = m.group(1)
        parts = [p.strip() for p in inner.split(",") if p.strip() != ""]
        return [tuple(_coerce_arg(p) for p in parts)]

    # 普通逗号分隔参数
    return [_coerce_arg(p) for p in arg_str.split(",") if p.strip() != ""]


def parse_action(action: str) -> Optional[ParsedAction]:
    """解析单条动作文本。

    - "error_input"（大小写/空白不敏感）→ 返回 None，代表幻觉拒答；
    - 合法动作 → ParsedAction；
    - 无法解析 → 抛 ActionParseError。
    """
    text = (action or "").strip().strip("{}").strip()
    if text.lower() == "error_input" or text == "":
        return None

    m = _ACTION_RE.match(text)
    if not m:
        raise ActionParseError(f"无法解析动作文本: {action!r}")

    room = m.group("room")
    room = room.strip() if room else None
    device = m.group("device").strip()
    op = m.group("op").strip()
    args = _parse_args(m.group("args"))
    return ParsedAction(room=room, device=device, op=op, args=args, raw=text)
