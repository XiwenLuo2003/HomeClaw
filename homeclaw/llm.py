"""LLM 抽象层（Provider 无关）。

M1 目标：让单主循环内核不绑定任何具体厂商 SDK，便于：
  1. 冒烟测试时用 MockLLMClient（无需真实 API）；
  2. M3 接入 openai / anthropic 时只需新增一个 Client 实现。

统一消息结构使用 OpenAI 风格的 role/content 字典：
  {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from homeclaw.config import LLMConfig


@dataclass
class LLMResponse:
    """一次 LLM 调用的结果。

    text        : 助手输出的文本内容
    tool_calls  : 结构化工具调用（Function-Calling）；M1 内核主要走文本动作，
                  但保留该字段以支持"read SKILL 正文"等工具调用语义。
    usage       : token 统计，用于"平均 token 成本"评测维度
    """

    text: str = ""
    tool_calls: List[dict] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类。"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def chat(self, messages: List[Dict]) -> LLMResponse:
        """输入消息列表，返回一次响应。"""
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    """离线 Mock 客户端，用于冒烟/CI，无需真实 API。

    ⚠️ 重要声明：这是**规则驱动**的模拟器，不是真正的意图识别。它的作用是验证
    "内核循环 → 动作提取 → 执行落地 → 评测统计" 的链路可跑通，并为四系统对比提供
    一个**可复现的下界**。用它跑出的评测数字仅为链路验证值，**不能作为模型效果写进
    论文**；真实模型效果需用 provider="openai"/"anthropic" 跑 run_experiment.py。

    相较最初的"单动作正则"，此版本做了增强以让链路更真实：
      1. 从 <device_method> 精确解析每个 room.device 支持的 operation 集合；
      2. 从 <home_state> 解析房间/设备存在性，做 error_input 幻觉判断；
      3. 支持多子句指令（按 " and " / ", " 切分）→ 多动作输出；
      4. 支持 turn on/off、set brightness、air conditioner on/off 等常见操作；
      5. 懒加载：命中 <skill_index> 且遇到"复杂"指令时，会先发 READ_SKILL 再作答，
         以驱动两级懒加载链路（简单指令则直接作答，体现省 token）。
    """

    def chat(self, messages: List[Dict]) -> LLMResponse:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        user = "\n".join(m["content"] for m in messages if m["role"] == "user")
        tool_msgs = [m["content"] for m in messages if m["role"] == "tool"]

        # 懒加载：若 system 仅有 skill 索引（未含速览之外的完整策略），
        # 且指令为多子句复杂指令、且尚未加载过技能，则先请求加载全文。
        already_loaded = any("<skill" in t for t in tool_msgs)
        if "<skill_index>" in system and not already_loaded and self._is_complex(user):
            text = "READ_SKILL: smart-home"
            return LLMResponse(text=text, usage=self._usage(system, user, text))

        methods = self._parse_methods(system)
        available = self._parse_available_devices(system)
        actions = self._plan_actions(user, methods, available)
        body = ", ".join(actions) if actions else "error_input"
        text = "{" + body + "}"
        return LLMResponse(text=text, usage=self._usage(system, user, text))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _usage(system: str, user: str, text: str) -> Dict[str, int]:
        return {
            "prompt_tokens": len(system.split()) + len(user.split()),
            "completion_tokens": len(text.split()),
        }

    @staticmethod
    def _is_complex(user: str) -> bool:
        """粗略判断指令是否"复杂"（多子句/含条件/含个性化），用于懒加载触发。"""
        u = user.lower()
        return (" and " in u or u.count(",") >= 1
                or any(k in u for k in ("when", "whenever", "if ", "favourite", "favorite",
                                        "cozy", "sleep", "dinner", "match")))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_methods(system: str) -> Dict[str, set]:
        """从 <device_method> 解析 {"room.device": {op,...}}（op 名，不含参数）。"""
        methods: Dict[str, set] = {}
        m = re.search(r"<device_method>(.*?)</device_method>", system, re.S)
        if not m:
            return methods
        body = m.group(1)
        # 形如 living_room.light.turn_off(); balcony.light.set_brightness(brightness:int);
        for entry in re.findall(r"([\w ]+\.[\w ]+\.[\w ]+)\(", body):
            parts = entry.split(".")
            if len(parts) == 3:
                key = f"{parts[0].strip()}.{parts[1].strip()}"
                methods.setdefault(key, set()).add(parts[2].strip())
            elif len(parts) == 2:  # 无房间前缀
                key = parts[0].strip()
                methods.setdefault(key, set()).add(parts[1].strip())
        return methods

    @staticmethod
    def _parse_available_devices(system: str) -> Dict[str, set]:
        """从 <home_state> 解析 {room: {device,...}}。"""
        devices: Dict[str, set] = {}
        m = re.search(r"<home_state>(.*?)</home_state>", system, re.S)
        if not m:
            return devices
        room = None
        for line in m.group(1).splitlines():
            if not line.strip():
                continue
            # 房间行：顶格且以冒号结尾
            if not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
                room = line.rstrip()[:-1].strip()
                devices.setdefault(room, set())
            elif room is not None and (line.startswith("  ") and not line.startswith("    ")):
                dev = line.strip()
                # 设备行：不是 state:/属性行
                if ":" not in dev:
                    devices[room].add(dev)
        return devices

    # ------------------------------------------------------------------ #
    def _plan_actions(self, user: str, methods: Dict[str, set],
                      available: Dict[str, set]) -> List[str]:
        """把用户指令拆成子句，逐句生成动作或 error_input。"""
        clauses = re.split(r"\s+and\s+|,\s*", user, flags=re.I)
        out: List[str] = []
        for clause in clauses:
            c = clause.strip()
            if not c:
                continue
            act = self._plan_one(c, methods, available)
            if act:
                out.append(act)
        # 去重保序
        seen, uniq = set(), []
        for a in out:
            if a not in seen:
                seen.add(a); uniq.append(a)
        return uniq

    def _plan_one(self, clause: str, methods: Dict[str, set],
                 available: Dict[str, set]) -> Optional[str]:
        low = clause.lower()
        # 定位房间
        room = None
        for r in available:
            if r.replace("_", " ").lower() in low:
                room = r
                break
        # 定位设备类型（按关键词）
        device = None
        if "air conditioner" in low or " ac " in f" {low} " or "air_conditioner" in low:
            device = "air_conditioner"
        elif "light" in low or "lamp" in low:
            device = "light"
        elif "media" in low or "volume" in low or "player" in low:
            device = "media_player"
        elif "garage" in low and "door" in low:
            device = "garage_door"

        # 房间/设备存在性校验（幻觉判断）
        if device is None:
            return "error_input"
        if room is None:
            # 尝试全局唯一定位
            hosts = [r for r, ds in available.items() if device in ds]
            if len(hosts) == 1:
                room = hosts[0]
            else:
                return "error_input"
        if room not in available or device not in available.get(room, set()):
            return "error_input"

        key = f"{room}.{device}"
        ops = methods.get(key, set())

        # 选择操作
        if "turn off" in low or "switch off" in low or ("off" in low and "on" not in low):
            op = "turn_off"
        elif "turn on" in low or "switch on" in low or "on" in low:
            op = "turn_on"
        elif "brightness" in low or "dim" in low or "bright" in low:
            mnum = re.search(r"(\d+)", low)
            if "set_brightness" in ops and mnum:
                return f"{room}.{device}.set_brightness({mnum.group(1)})"
            op = "turn_on"
        elif "volume" in low:
            mnum = re.search(r"(\d+)", low)
            if "set_volume" in ops and mnum:
                return f"{room}.{device}.set_volume({mnum.group(1)})"
            op = "turn_on"
        else:
            op = "turn_on"

        # 若解析出的 op 不在方法清单中，但方法清单非空，则视为不可执行
        if ops and op not in ops:
            return "error_input"
        return f"{room}.{device}.{op}()"


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容的 Chat Completions 客户端（用标准库 urllib 实现，零第三方依赖）。

    也可通过 base_url 指向任意 OpenAI 兼容端点（如本地 vLLM / DeepSeek / 通义等）。
    api_key 优先取 config.api_key，否则读环境变量 OPENAI_API_KEY。
    """

    api_key_environment = "OPENAI_API_KEY"
    default_base_url = "https://api.openai.com/v1"

    def chat(self, messages: List[Dict]) -> LLMResponse:
        import json
        import os
        import urllib.error
        import urllib.request

        api_key = self.config.api_key or os.getenv(self.api_key_environment)
        if not api_key:
            raise RuntimeError(
                f"缺少 API Key：请设置 config.api_key 或环境变量 {self.api_key_environment}"
            )
        base_url = (self.config.base_url or self.default_base_url).rstrip("/")

        payload = {
            "model": self.config.model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (408, 429, 500, 502, 503, 504):
                raise ConnectionError(f"LLM provider HTTP {exc.code}") from exc
            raise ValueError(f"LLM provider rejected request with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"LLM provider unavailable: {exc.reason}") from exc

        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
        )


class GeminiCompatibleClient(OpenAICompatibleClient):
    """Gemini official OpenAI-compatible endpoint for the online main model."""

    api_key_environment = "GEMINI_API_KEY"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"


class AnthropicClient(BaseLLMClient):
    """Anthropic Messages API 客户端（urllib 实现，零第三方依赖）。

    api_key 优先取 config.api_key，否则读环境变量 ANTHROPIC_API_KEY。
    system 消息会被抽出到顶层 system 字段（Anthropic 规范）。
    """

    def chat(self, messages: List[Dict]) -> LLMResponse:
        import json
        import os
        import urllib.error
        import urllib.request

        api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 API Key：请设置 config.api_key 或环境变量 ANTHROPIC_API_KEY")
        base_url = (self.config.base_url or "https://api.anthropic.com/v1").rstrip("/")

        system_text = "\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [
            {"role": ("assistant" if m["role"] == "assistant" else "user"),
             "content": m["content"]}
            for m in messages if m["role"] in ("user", "assistant", "tool")
        ]
        payload = {
            "model": self.config.model,
            "system": system_text,
            "messages": convo,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        req = urllib.request.Request(
            f"{base_url}/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (408, 429, 500, 502, 503, 504):
                raise ConnectionError(f"Anthropic HTTP {exc.code}") from exc
            raise ValueError(f"Anthropic rejected request with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Anthropic unavailable: {exc.reason}") from exc

        # Anthropic 返回 content 是 block 列表
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            },
        )


class LocalHFClient(BaseLLMClient):
    """本地 HuggingFace transformers 客户端（P4）：进程内加载权重做推理。

    对齐 HomeBench code/model_test.py 的"本地权重直接 load 进显存"入口，
    用于论文里复现本地开源模型（Llama / Qwen / Mistral 等）的对比。

    - 依赖 transformers + torch，为**可选**依赖：仅在 provider=local 时才 import，
      未安装时给出清晰报错，不影响其它 provider。
    - config.model 可为：① download_models.py 下载的 sub_dir 名（如 "Qwen2.5-7B-Instruct"）
      → 自动解析到 HomeClaw/models/<sub_dir>；② 本地权重绝对/相对目录；
      ③ HF repo id（如 "Qwen/Qwen2.5-7B-Instruct"）→ 联网加载（走 HF_ENDPOINT 镜像）。
    - config.base_url 无意义（本地无 URL）。
    - 按"解析后的路径"实例级缓存：换模型会重新加载，不会串用旧权重。

    若不想进程内加载权重，也可用 vLLM/Ollama 起 OpenAI 兼容服务，然后用
    provider=openai_compatible + base_url 指向它（见 create_llm_client 说明）。
    """

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._model = None
        self._tokenizer = None
        self._loaded_path = None

    def _resolve_model_path(self) -> str:
        """把 config.model 解析为本地权重目录（优先 models/<sub_dir>）或 HF repo id。"""
        from homeclaw import data_paths
        return data_paths.local_model_path(self.config.model)

    def _ensure_loaded(self):
        resolved = self._resolve_model_path()
        if self._model is not None and self._loaded_path == resolved:
            return
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                "provider=local 需要安装 transformers 与 torch：\n"
                "  pip install torch transformers accelerate\n"
                f"（原始错误：{e}）"
            )
        self._tokenizer = AutoTokenizer.from_pretrained(resolved)
        self._model = AutoModelForCausalLM.from_pretrained(
            resolved, torch_dtype="auto", device_map="auto",
        )
        self._loaded_path = resolved

    def chat(self, messages: List[Dict]) -> LLMResponse:
        self._ensure_loaded()
        tok = self._tokenizer
        model = self._model

        # 优先用 chat template（多数 instruct 模型支持）；否则手动拼接。
        try:
            prompt = tok.apply_chat_template(
                [{"role": m["role"], "content": m["content"]} for m in messages],
                tokenize=False, add_generation_prompt=True,
            )
        except Exception:
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"

        inputs = tok(prompt, return_tensors="pt").to(model.device)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        gen = model.generate(
            **inputs,
            max_new_tokens=self.config.max_tokens,
            do_sample=self.config.temperature > 0,
            temperature=max(self.config.temperature, 1e-5),
        )
        out_ids = gen[0][prompt_tokens:]
        text = tok.decode(out_ids, skip_special_tokens=True)
        return LLMResponse(
            text=text,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": int(out_ids.shape[-1]),
            },
        )


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """LLM 客户端工厂。

    支持的 provider：
      - "mock"                : 离线规则匹配（冒烟/CI，无需 API）
      - "openai" / "openai_compatible" : OpenAI 兼容端点（含本地 vLLM/Ollama/DeepSeek 等）
      - "gemini"              : Gemini 官方 OpenAI 兼容端点（读取 GEMINI_API_KEY）
      - "anthropic"           : Anthropic Messages API
      - "local"               : 本地 HuggingFace transformers 进程内加载权重（P4，需 torch/transformers）

    本地部署两种方式（论文实验可任选）：
      1) provider=local          → 进程内 transformers 加载权重（对齐 HomeBench）；
      2) provider=openai_compatible + base_url=http://localhost:xxxx/v1
                                 → 连本地 vLLM/Ollama 的 OpenAI 兼容服务（更省显存管理成本）。
    """
    provider = config.provider
    if provider == "mock":
        return MockLLMClient(config)
    if provider in ("openai", "openai_compatible"):
        return OpenAICompatibleClient(config)
    if provider == "gemini":
        return GeminiCompatibleClient(config)
    if provider == "anthropic":
        return AnthropicClient(config)
    if provider == "local":
        return LocalHFClient(config)
    raise NotImplementedError(f"未知 provider: {provider!r}")
