"""DeviceDisambiguationTool（P3）：SAGE 的 VLM 图像设备消歧，真实实现 + 文本兜底。

SAGE 原版在多个同名/邻近设备间消歧时，会用 CLIP/VLM 结合每台设备的实景环境图片打分。
本模块默认走真实 CLIP 图文相似度（CLIPVisionMatcher），只有在缺少 torch/open_clip
依赖或取不到设备图片时，才回退到文本相似度兜底：

  * 有依赖 + 有实景图（data/sage/images/<uuid>.jpg）-> 真·多模态视觉消歧（与 SAGE 对齐）；
  * 无依赖 / 无图 -> 文本兜底，离线可跑、结果确定，但会明确标注为降级。

【实验对比须知】
  要与 SAGE 官方在 device_resolution 维度做公平对比，必须启用 CLIP 视觉消歧：
    - 安装依赖：pip install open_clip_torch torch pillow
    - 预下载权重：python download_models.py --clip
  若日志显示 backend == "text"，说明当前跑的是文本降级版，结果不可与 SAGE 直接比较。
"""
from __future__ import annotations

import difflib
import os
import threading
from typing import Callable, Dict, List, Optional, Sequence

from homeclaw import data_paths


# vlm_fn 签名：(image_obj_or_path, candidates, phrase) -> 选中的 candidate 名
VlmFn = Callable[[object, List[str], str], Optional[str]]


def _candidate_image_map(
    candidates: Sequence[str],
    device_images: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """把候选 room.device 映射到其实景图片的绝对路径。"""
    out: Dict[str, str] = {}
    if not device_images:
        return out
    for c in candidates:
        rel = device_images.get(c)
        if not rel:
            continue
        path = rel if os.path.isabs(rel) else os.path.join(data_paths.DATA_DIR, rel)
        if os.path.isfile(path):
            out[c] = path
    return out


class CLIPVisionMatcher:
    """基于 open_clip 的 CLIP 图文相似度设备消歧器（惰性单例）。"""

    _instance: Optional["CLIPVisionMatcher"] = None
    _lock = threading.Lock()

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k"):
        import open_clip  # 延迟导入：无依赖时由外层捕获
        import torch

        self._torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # 本地权重目录（download_models.py --clip 下载到此）优先
        local_ckpt = os.path.join(data_paths.MODELS_DIR, "clip", f"{model_name}.pt")
        pretrained_arg = local_ckpt if os.path.isfile(local_ckpt) else pretrained

        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained_arg
        )
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.model_name = model_name

    @classmethod
    def instance(cls) -> "CLIPVisionMatcher":
        """获取进程内单例（首次调用加载权重，可能较慢/需联网）。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def match(self, phrase: str, cand_images: Dict[str, str],
              cand_texts: Optional[Dict[str, str]] = None) -> Optional[str]:
        """在 {candidate -> image_path} 中选与 phrase 最相符的候选。

        采用 SAGE 的 text-query x image 检索形式，但为保留锚点判别力，改为**逐候选成对
        打分**：每个候选用「用户短语 + 该候选自己的 anchors 富描述」构造独立 query，与
        该候选自己的实景图算相似度，最后取相似度最高的候选。这样锚点对每个候选是独立上下
        文（而非合并成对所有候选公共的字符串），装了 open_clip 后锚点才真正参与判别。
        """
        from PIL import Image

        torch = self._torch
        if not cand_images:
            return None

        names = list(cand_images.keys())
        cand_texts = cand_texts or {}
        with torch.no_grad():
            # --- 图像侧：N 张候选实景图 ---
            imgs = []
            for n in names:
                img = Image.open(cand_images[n]).convert("RGB")
                imgs.append(self.preprocess(img))
            image_input = torch.stack(imgs).to(self.device)
            image_features = self.model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)

            # --- 文本侧：逐候选构造带自身锚点的 query（保持独立判别）---
            queries = []
            for n in names:
                anchor = cand_texts.get(n) or ""
                anchor_ctx = f" ({anchor})" if anchor else ""
                queries.append(f"a photo of the device the user means: {phrase}{anchor_ctx}")
            text_input = self.tokenizer(queries).to(self.device)
            text_features = self.model.encode_text(text_input)
            text_features /= text_features.norm(dim=-1, keepdim=True)

            # 成对打分：第 i 个 query 只与第 i 张图算相似度（对角线），取最大
            sims = (text_features * image_features).sum(dim=-1)
            best_idx = int(sims.argmax().item())
        return names[best_idx]


def _default_clip_vlm_fn(
    device_texts: Optional[Dict[str, str]] = None,
) -> VlmFn:
    """构造一个基于 CLIP 单例的 vlm_fn。device_texts: {candidate -> 富描述(含 anchors)}。

    device_images / device_texts 均以闭包属性形式对称注入（由 Tool 在事后注入），
    避免"只注入图、不注入文本"导致后期修改 device_texts 时闭包不同步的陷阱。
    """

    def _fn(_image, candidates: List[str], phrase: str) -> Optional[str]:
        # _image 参数保留以兼容旧签名；真实实现按候选各自的实景图消歧。
        cand_images = _candidate_image_map(candidates, _fn.device_images)  # type: ignore[attr-defined]
        if not cand_images:
            return None
        matcher = CLIPVisionMatcher.instance()
        return matcher.match(phrase, cand_images, _fn.device_texts)  # type: ignore[attr-defined]

    _fn.device_images = {}  # type: ignore[attr-defined]  # 由 Tool 注入
    _fn.device_texts = dict(device_texts or {})  # type: ignore[attr-defined]  # 由 Tool 注入
    return _fn


class DeviceDisambiguationTool:
    """在多个候选设备间选出用户所指的那个（默认 CLIP 视觉消歧，缺依赖时文本兜底）。

    参数：
      device_images: {room.device -> image 路径}（一般来自场景 DeviceSlot.image）；
      device_texts : {room.device -> 富文本描述}（一般为 anchors 拼接），增强图文对齐；
      vlm_fn       : 显式注入的 VLM 函数；不传则在有依赖+有图时自动构建 CLIP vlm_fn；
      prefer_vlm   : True（默认）优先视觉；设 False 可强制走文本（用于消融实验）。
    """

    def __init__(
        self,
        device_images: Optional[Dict[str, str]] = None,
        device_texts: Optional[Dict[str, str]] = None,
        vlm_fn: Optional[VlmFn] = None,
        prefer_vlm: bool = True,
    ):
        self.device_images: Dict[str, str] = dict(device_images or {})
        self.device_texts: Dict[str, str] = dict(device_texts or {})
        self.prefer_vlm = prefer_vlm
        self.backend = "text"  # 实际使用的后端标识，供实验日志如实标注

        self.vlm_fn: Optional[VlmFn] = None
        if vlm_fn is not None:
            self.vlm_fn = vlm_fn
        elif prefer_vlm:
            self.vlm_fn = self._build_clip_vlm_fn()

        # 若成功建立 CLIP 通道，把设备图与富文本描述对称注入闭包
        if self.vlm_fn is not None:
            try:
                self.vlm_fn.device_images = self.device_images  # type: ignore[attr-defined]
                self.vlm_fn.device_texts = self.device_texts  # type: ignore[attr-defined]
            except Exception:
                pass

    @classmethod
    def from_scene(cls, scene, prefer_vlm: bool = True) -> "DeviceDisambiguationTool":
        """从 Scene 直接构建：抽取每台设备的 image 与 anchors 富描述。"""
        images: Dict[str, str] = {}
        texts: Dict[str, str] = {}
        for room in scene.rooms:
            for slot in room.existing_slots():
                full = f"{room.name}.{slot.slot_name()}"
                img = getattr(slot, "image", None)
                if img:
                    images[full] = img
                anchors = getattr(slot, "anchors", None) or []
                desc = slot.slot_name().replace("_", " ")
                if anchors:
                    desc = f"{desc} ({', '.join(anchors)})"
                texts[full] = desc
        return cls(device_images=images, device_texts=texts, prefer_vlm=prefer_vlm)

    def _build_clip_vlm_fn(self) -> Optional[VlmFn]:
        """尝试构建真实 CLIP vlm_fn；缺依赖时返回 None（后续走文本兜底）。"""
        try:
            import open_clip  # noqa: F401
            import torch       # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            return None
        return _default_clip_vlm_fn(self.device_texts)

    def disambiguate(self, phrase: str, candidates: List[str],
                     image: Optional[object] = None) -> Optional[str]:
        """从 candidates（形如 "living_room.tv"）中选最匹配 phrase 的一个。

        优先真实 CLIP 视觉消歧（当候选有实景图且依赖可用）；否则文本兜底。
        self.backend 记录本次实际使用的后端（"clip" / "text"）。
        """
        if not candidates:
            self.backend = "text"
            return None

        # —— 首选：真实 VLM 视觉消歧 ——
        if self.prefer_vlm and self.vlm_fn is not None:
            try:
                picked = self.vlm_fn(image, candidates, phrase)
                if picked is not None:
                    self.backend = "clip"
                    return picked
            except Exception:
                # 视觉链路异常不致命，落到文本兜底（并如实标注）
                pass

        # —— 兜底：文本相似度消歧（利用 anchors 描述，提升降级版质量）——
        self.backend = "text"
        return self._text_disambiguate(phrase, candidates, self.device_texts)

    @staticmethod
    def _text_disambiguate(phrase: str, candidates: List[str],
                           device_texts: Optional[Dict[str, str]] = None) -> Optional[str]:
        """文本相似度兜底：设备名 + anchors 描述 -> 房间名 -> difflib。"""
        low = phrase.lower()
        device_texts = device_texts or {}

        best = None
        best_score = 0
        for c in candidates:
            device_part = c.split(".")[-1]
            toks = [t for t in device_part.lower().replace("_", " ").split() if len(t) >= 2]
            desc = device_texts.get(c, "")
            anchor_toks = [t for t in desc.lower().replace("_", " ")
                           .replace("(", " ").replace(")", " ").replace(",", " ").split()
                           if len(t) >= 3]
            score = sum(1 for tok in toks if tok in low)
            score += 2 * sum(1 for tok in set(anchor_toks) if tok in low)
            if score > best_score:
                best_score = score
                best = c
        if best is not None and best_score > 0:
            return best

        for c in candidates:
            room_part = c.split(".")[0] if "." in c else ""
            tokens = [t for t in room_part.lower().replace("_", " ").split()
                      if len(t) >= 2]
            score = sum(1 for tok in tokens if tok in low)
            if score > best_score:
                best_score = score
                best = c
        if best is not None and best_score > 0:
            return best
        match = difflib.get_close_matches(low, [c.lower() for c in candidates], n=1, cutoff=0.3)
        if match:
            for c in candidates:
                if c.lower() == match[0]:
                    return c
        return candidates[0]


__all__ = ["DeviceDisambiguationTool", "CLIPVisionMatcher", "VlmFn"]
