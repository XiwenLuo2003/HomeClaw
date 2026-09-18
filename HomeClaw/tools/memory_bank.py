"""MemoryBank（P3，最高优先）：SAGE 记忆库的离线可跑重建。

SAGE 原实现依赖向量库（sentence-transformers 嵌入 + 相似度检索，经 LangChain retriever）。
这里把"检索打分"抽象成可插拔的 Retriever 接口，默认提供**零依赖的关键词重叠检索版**，
同时预留一个**语义向量检索版**（BYO embedding 函数），从而：

  - 离线/CI/无网络环境：用 KeywordRetriever，零第三方依赖、结果确定可复现；
  - 正式论文实验：注入 embedding 函数（如 sentence-transformers / OpenAI embeddings /
    本地 vLLM embedding 端点）即可切到 EmbeddingRetriever，与 SAGE 原始向量库对齐。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【检索后端与实验对比须知】
  MemoryBank 默认走 auto 策略：**若安装了 sentence-transformers，则自动启用真实向量
  语义检索**（与 SAGE 原始向量库对齐）；只有在缺该依赖时才回退 KeywordRetriever
  关键词重叠（降级版，无语义泛化能力）。

    * 要与 SAGE 在 personalization 维度做公平对比 → 安装 sentence-transformers
      （见 download_models.py / requirements），MemoryBank 会自动用向量检索，
      is_semantic == True；
    * 若日志显示 retriever_kind == "keyword" / is_semantic == False → 当前为
      关键词降级版，其个性化召回结果不可与 SAGE 真实向量检索直接比较，须在方法学中
      如实标注；
    * 也可显式指定：MemoryBank.with_embedding(embed_fn) 注入自定义 embedding，
      或构造时传 retriever=KeywordRetriever() 强制降级（用于消融实验）。
  接口不变：切换检索器不影响 UserProfileTool 及五维用例的调用方式。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

数据来源：从 data/sage/memory 读取历史对话 + profile（经 sage_dataset 归一化）。
"""
from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from homeclaw.eval import sage_dataset


# embedding 函数签名：接收一批文本，返回等长的向量列表。
EmbedFn = Callable[[Sequence[str]], Sequence[Sequence[float]]]


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


# ---------------------------------------------------------------------------- #
# 可插拔检索器接口
# ---------------------------------------------------------------------------- #
class Retriever:
    """检索器基类：给定 query 与候选文本，返回按相关度降序的 (score, index) 列表。"""

    #: 检索器类型标识（用于报告/日志中如实标注是否为降级实现）
    kind: str = "base"
    #: 是否语义级（True=向量检索；False=词面降级）
    semantic: bool = False

    def index(self, texts: Sequence[str]) -> None:
        """（可选）预建索引。默认无操作。"""

    def rank(self, query: str, texts: Sequence[str]) -> List[Tuple[float, int]]:
        raise NotImplementedError


class KeywordRetriever(Retriever):
    """零依赖关键词重叠检索（SAGE 向量检索的**降级实现**）。

    打分：query 与候选的 token 交集大小，按候选长度平方根归一，抑制长文本占优。
    确定性、可复现，但无语义泛化能力。
    """

    kind = "keyword"
    semantic = False

    @staticmethod
    def _score(query_tokens: List[str], text: str) -> float:
        toks = _tokenize(text)
        if not toks:
            return 0.0
        q = set(query_tokens)
        overlap = sum(1 for t in toks if t in q)
        return overlap / (len(toks) ** 0.5)

    def rank(self, query: str, texts: Sequence[str]) -> List[Tuple[float, int]]:
        qt = _tokenize(query)
        scored = [(self._score(qt, t), i) for i, t in enumerate(texts)]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored


class EmbeddingRetriever(Retriever):
    """语义向量检索（与 SAGE 原始向量库对齐）。

    由调用方注入 embed_fn（把文本批量转成向量），本类用余弦相似度排序。
    embed_fn 可来自 sentence-transformers / OpenAI embeddings / 本地 vLLM embedding。
    候选向量在 index() 时缓存，避免每次查询重复编码。
    """

    kind = "embedding"
    semantic = True

    def __init__(self, embed_fn: EmbedFn):
        self._embed = embed_fn
        self._texts: List[str] = []
        self._vecs: List[List[float]] = []

    def index(self, texts: Sequence[str]) -> None:
        self._texts = list(texts)
        self._vecs = [list(v) for v in self._embed(self._texts)] if self._texts else []

    @staticmethod
    def _cos(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def rank(self, query: str, texts: Sequence[str]) -> List[Tuple[float, int]]:
        # 若外部传入的 texts 与已建索引不一致，则临时重建
        if list(texts) != self._texts:
            self.index(texts)
        if not self._vecs:
            return []
        qv = list(self._embed([query])[0])
        scored = [(self._cos(qv, v), i) for i, v in enumerate(self._vecs)]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored


# ---------------------------------------------------------------------------- #
# 内置真实 embedding：sentence-transformers（与 SAGE 向量库对齐）
# ---------------------------------------------------------------------------- #
_ST_MODEL_CACHE: Dict[str, object] = {}


def default_sentence_transformer_embed_fn(
    model_name: str = "all-MiniLM-L6-v2",
) -> Optional[EmbedFn]:
    """构造基于 sentence-transformers 的 embed_fn；缺依赖时返回 None。

    权重优先从本地 data_paths.MODELS_DIR/sentence-transformers/<model_name> 加载
    （download_models.py 下载），否则联网从 HF 拉取。进程内按 model_name 缓存模型，
    避免重复加载。
    """
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None

    def _load():
        if model_name in _ST_MODEL_CACHE:
            return _ST_MODEL_CACHE[model_name]
        import os
        from homeclaw import data_paths
        local = os.path.join(data_paths.MODELS_DIR, "sentence-transformers", model_name)
        src = local if os.path.isdir(local) else model_name
        model = SentenceTransformer(src)
        _ST_MODEL_CACHE[model_name] = model
        return model

    def _embed(texts: Sequence[str]) -> Sequence[Sequence[float]]:
        model = _load()
        vecs = model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]

    return _embed


def build_default_retriever() -> Retriever:
    """auto 策略：有 sentence-transformers 则用真实向量检索，否则关键词降级。"""
    embed_fn = default_sentence_transformer_embed_fn()
    if embed_fn is not None:
        return EmbeddingRetriever(embed_fn)
    return KeywordRetriever()


# ---------------------------------------------------------------------------- #
# 记忆库
# ---------------------------------------------------------------------------- #
class MemoryBank:
    """SAGE 记忆库（离线可跑，检索器可插拔）。

    默认 auto 策略（build_default_retriever）：有 sentence-transformers 则自动用真实
    向量语义检索（与 SAGE 对齐），无依赖时回退 KeywordRetriever（降级、零依赖）。
    也可显式传 retriever=EmbeddingRetriever(embed_fn) 或用 MemoryBank.with_embedding。
    """

    def __init__(self, user: str = "amal", retriever: Optional[Retriever] = None):
        self.user = user
        self._entries: List[Dict] = []   # [{"date":.., "text":..}]
        self.retriever: Retriever = retriever or build_default_retriever()
        self._load(user)
        self._reindex()

    # --- 便捷构造：真实向量检索版（论文对比用） ------------------------------ #
    @classmethod
    def with_embedding(cls, embed_fn: EmbedFn, user: str = "amal") -> "MemoryBank":
        """用注入的 embedding 函数构建语义向量检索版记忆库。"""
        return cls(user=user, retriever=EmbeddingRetriever(embed_fn))

    def _load(self, user: str) -> None:
        prof = sage_dataset.get_user_profile(user)
        history = prof.get("history", {}) or {}
        for date, msgs in history.items():
            for m in msgs:
                self._entries.append({"date": date, "text": m})

    def _reindex(self) -> None:
        self.retriever.index([e["text"] for e in self._entries])

    def add(self, text: str, date: str = "runtime") -> None:
        """追加一条运行期记忆（并刷新检索索引）。"""
        self._entries.append({"date": date, "text": text})
        self._reindex()

    @property
    def is_semantic(self) -> bool:
        """当前检索器是否为语义向量检索（False=关键词降级）。"""
        return self.retriever.semantic

    @property
    def retriever_kind(self) -> str:
        return self.retriever.kind

    def retrieve(self, query: str, k: int = 3) -> List[Dict]:
        """返回与 query 最相关的 k 条记忆（检索器由 self.retriever 决定）。"""
        texts = [e["text"] for e in self._entries]
        ranked = self.retriever.rank(query, texts)
        return [self._entries[i] for _, i in ranked[:k]]

    def all_entries(self) -> List[Dict]:
        return list(self._entries)


__all__ = [
    "MemoryBank", "Retriever", "KeywordRetriever", "EmbeddingRetriever", "EmbedFn",
    "default_sentence_transformer_embed_fn", "build_default_retriever",
]
