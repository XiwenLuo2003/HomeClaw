"""Prompt 构建模块（M1 / M6）。

职责：
  1. 加载 smart-home Skill 的 SKILL.md（去除 frontmatter，取正文）；
  2. 将 HomeBench 风格的 home_status / method 序列化为文本（对齐其 chang_json2str）；
  3. 拼装最终 system prompt（Skill 正文 + home_state + device_method）；
  4. 【M6】两级懒加载：支持"先注入摘要 + read_skill 工具，模型用到才拉全文"，
     与 OpenClaw 的 Skill 懒加载卖点真正对齐（省 token）。

两种注入模式：
- 直接注入（lazy_load=False）：一次性把 SKILL 全文放进 system prompt（简单、稳）。
- 两级懒加载（lazy_load=True）：system prompt 只放"最短核心规则 + read_skill 提示"，
  模型若判断需要完整领域策略，则通过 read_skill 工具调用拉取正文并回传，再继续。
  对"格式清晰的简单指令"可跳过全文注入，从而降低 prompt token。
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple


# SKILL 正文中“始终注入”的规则速览标记（介于二者之间的内容属于懒加载可省略的完整策略）
_OVERVIEW_BEGIN = "<!-- OVERVIEW:BEGIN -->"
_OVERVIEW_END = "<!-- OVERVIEW:END -->"


def _default_skill_path(skill_name: str) -> str:
    """包内默认 SKILL.md 路径。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "skills", skill_name, "SKILL.md")


def load_skill_body(skill_path: Optional[str], skill_name: str = "smart-home") -> str:
    """读取 SKILL.md 并剥离 YAML frontmatter，返回正文。"""
    path = skill_path or _default_skill_path(skill_name)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # 去掉开头的 --- frontmatter ---
    m = re.match(r"^---\n.*?\n---\n(.*)$", content, flags=re.S)
    return m.group(1).strip() if m else content.strip()


def load_skill_overview(skill_path: Optional[str], skill_name: str = "smart-home") -> str:
    """【M6】提取 SKILL 正文中 OVERVIEW:BEGIN/END 之间的“规则速览”段。

    该段落是懒加载模式下唯一始终注入 system prompt 的部分，
    包含最短的动作格式与 error_input 规则；完整领域策略需 read_skill 拉取。
    若正文未标注 OVERVIEW 段，则回退为整篇正文（等价于不省 token）。
    """
    body = load_skill_body(skill_path, skill_name)
    m = re.search(
        re.escape(_OVERVIEW_BEGIN) + r"(.*?)" + re.escape(_OVERVIEW_END),
        body,
        flags=re.S,
    )
    return m.group(1).strip() if m else body


def load_skill_summary(skill_path: Optional[str], skill_name: str = "smart-home") -> Dict[str, str]:
    """读取 SKILL.md frontmatter 的 name/description，供两级检索的摘要层使用。"""
    path = skill_path or _default_skill_path(skill_name)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    fm = re.match(r"^---\n(.*?)\n---\n", content, flags=re.S)
    summary = {"name": skill_name, "description": ""}
    if fm:
        for line in fm.group(1).splitlines():
            if line.startswith("name:"):
                summary["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                summary["description"] = line.split(":", 1)[1].strip()
    return summary


def serialize_home_status(state: Dict) -> str:
    """将 home_status 序列化为文本，对齐 HomeBench chang_json2str 的格式。

    格式示例：
        living_room:
          light
            state: on
            brightness: 100 (range: 0 - 100)
            color: (255, 255, 255)
    """
    lines: List[str] = []
    for room, room_val in state.items():
        lines.append(f"{room}:")
        # VacuumRobot 等无 device 层，直接挂 attributes
        if isinstance(room_val, dict) and "attributes" in room_val and "state" in room_val:
            lines.append(f"  state: {room_val['state']}")
            _append_attributes(lines, room_val["attributes"], indent="  ")
            continue
        for device, dev_val in room_val.items():
            if device == "room_name":
                continue
            lines.append(f"  {device}")
            lines.append(f"    state: {dev_val.get('state', 'unknown')}")
            _append_attributes(lines, dev_val.get("attributes", {}), indent="    ")
    return "\n".join(lines)


def _append_attributes(lines: List[str], attributes: Dict, indent: str) -> None:
    for attr, meta in attributes.items():
        value = meta.get("value")
        line = f"{indent}{attr}: {value}"
        if "options" in meta:
            line += f" (options{meta['options']})"
        elif "lowest" in meta and "highest" in meta:
            line += f" (range: {meta['lowest']} - {meta['highest']})"
        lines.append(line)


def serialize_methods(methods: List[Dict]) -> str:
    """将 method 列表序列化为文本，对齐 HomeBench chang_json2str。

    每个 method 形如：
      {"room_name": "living_room", "device_name": "light",
       "operation": "set_brightness", "parameters": [{"name": "brightness", "type": "int"}]}
    输出：living_room.light.set_brightness(brightness:int);
    room_name 为 "None" 时省略房间前缀。
    """
    parts: List[str] = []
    for method in methods:
        room = method.get("room_name", "None")
        prefix = "" if room == "None" else f"{room}."
        head = f"{prefix}{method['device_name']}.{method['operation']}("
        params = method.get("parameters", [])
        if params:
            head += ",".join(f"{p['name']}:{p['type']}" for p in params)
        head += ");"
        parts.append(head)
    return "".join(parts)


def build_system_prompt(
    skill_body: str,
    home_status: Optional[Dict] = None,
    methods: Optional[List[Dict]] = None,
) -> str:
    """拼装最终 system prompt（直接注入全文模式）。

    结构：Skill 正文 + <home_state>…</home_state> + <device_method>…</device_method>
    """
    return _assemble(skill_body, home_status, methods)


# 懒加载模式下 read_skill 工具的使用说明（注入 system prompt 顶部）
_LAZY_SKILL_HINT = (
    "<skill_index>\n"
    "You have access to a domain skill via a tool. Below is only its overview cheat-sheet.\n"
    "If the user instruction is a simple, unambiguous device command that the cheat-sheet\n"
    "already covers, answer directly WITHOUT loading the full skill.\n"
    "If you need the FULL domain strategy (personalization / device disambiguation /\n"
    "multi-step planning / persistence), emit EXACTLY this tool call on its own line:\n"
    "READ_SKILL: smart-home\n"
    "Then wait for the tool result before producing the final machine instructions.\n"
    "</skill_index>"
)


def build_lazy_system_prompt(
    skill_overview: str,
    home_status: Optional[Dict] = None,
    methods: Optional[List[Dict]] = None,
) -> str:
    """【M6】两级懒加载模式的初始 system prompt。

    只注入：read_skill 提示 + SKILL 规则速览段 + home_state + device_method。
    完整领域策略正文不在此注入，模型需要时通过 READ_SKILL 工具拉取。
    """
    head = _LAZY_SKILL_HINT + "\n\n" + skill_overview
    return _assemble(head, home_status, methods)


def _assemble(
    head: str,
    home_status: Optional[Dict],
    methods: Optional[List[Dict]],
) -> str:
    segments = [head]
    if home_status is not None:
        state_str = serialize_home_status(home_status)
        segments.append(
            "<home_state>\n"
            "The following provides the status of all devices in each room, "
            "the adjustable attributes, and the thresholds:\n"
            f"{state_str}\n"
            "</home_state>"
        )
    if methods is not None:
        method_str = serialize_methods(methods)
        segments.append(
            "<device_method>\n"
            "The following provides the methods to control each device:\n"
            f"{method_str}\n"
            "</device_method>"
        )
    return "\n\n".join(segments)


def build_user_prompt(instruction: str) -> str:
    """拼装用户指令段，对齐 HomeBench 的输入格式。"""
    return (
        "Here are the user instructions you need to reply to.\n"
        f"<User instructions:> \n{instruction}\n"
        "<Machine instructions:>"
    )


def split_user_command(command: str) -> Tuple[str, str]:
    """解析 SAGE 风格的 '<user>: <command>' 输入。

    返回 (user_name, instruction)。无冒号时 user_name 为空串。
    """
    if ":" in command:
        user, instruction = command.split(":", 1)
        return user.strip(), instruction.strip()
    return "", command.strip()
