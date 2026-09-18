"""HomeClaw 本地开源模型下载脚本。

定位：HomeClaw 学术实验以云端完整大模型 API 为主（对齐 SAGE 在线 API 方式，见
run_experiment.py 的 --provider openai / anthropic）。本脚本用于复现：
  1) HomeBench 的"本地部署开源 LLM"实验路径；
  2) **SAGE 多模态设备消歧所需的 CLIP 视觉模型**（device_resolution 维度的关键）；
  3) **SAGE 记忆库向量检索所需的 sentence-transformers 嵌入模型**（personalization 维度）。

下载目标目录（与 homeclaw/data_paths.py、tools/ 的本地加载路径对齐）：

    HomeClaw/models/
      |- llama3-8b-Instruct/                # 文本 LLM
      |- Qwen2.5-7B-Instruct/
      |- Mistral-7B-Instruct-v0.3/
      |- Gemma-7B-Instruct-v0.3/
      |- clip/ViT-B-32.pt                   # CLIP 视觉消歧（DeviceDisambiguationTool）
      |- sentence-transformers/all-MiniLM-L6-v2/   # 向量记忆检索（MemoryBank）

使用步骤：
    hf auth login
    export HF_ENDPOINT=https://hf-mirror.com
    export HF_TOKEN=YOUR_HF_TOKEN

    python download_models.py               # 下载全部（LLM + CLIP + embedding）
    python download_models.py --clip        # 仅下载 CLIP 视觉模型
    python download_models.py --embed       # 仅下载 sentence-transformers 嵌入模型
    python download_models.py --llm         # 仅下载文本 LLM
    python download_models.py --clip --embed  # 只下载 SAGE 工具所需的多模态/向量模型

下载后即可跑真实多模态对比实验（device_resolution 会走真 CLIP，personalization 走真向量检索）：
    python3 run_experiment.py --provider local --model Qwen2.5-7B-Instruct --limit 200
"""
import argparse
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
from huggingface_hub import snapshot_download

# 文本 LLM 列表：{repo_id, 本地 models/ 子目录名}
LLM_MODELS = [
    {"repo_id": "meta-llama/Meta-Llama-3-8B-Instruct", "sub_dir": "llama3-8b-Instruct"},
    {"repo_id": "Qwen/Qwen2.5-7B-Instruct", "sub_dir": "Qwen2.5-7B-Instruct"},
    {"repo_id": "mistralai/Mistral-7B-Instruct-v0.3", "sub_dir": "Mistral-7B-Instruct-v0.3"},
    {"repo_id": "google/gemma-7b-it", "sub_dir": "Gemma-7B-Instruct-v0.3"},
]

# 句向量模型（MemoryBank 真实向量检索用；与 tools/memory_bank.py 默认 all-MiniLM-L6-v2 对齐）
EMBED_MODELS = [
    {"repo_id": "sentence-transformers/all-MiniLM-L6-v2",
     "sub_dir": os.path.join("sentence-transformers", "all-MiniLM-L6-v2")},
]

# CLIP 视觉模型（DeviceDisambiguationTool 真实视觉消歧用；与 open_clip ViT-B-32 对齐）
CLIP_OPEN_CLIP = {
    "model_name": "ViT-B-32",
    "pretrained": "laion2b_s34b_b79k",
    "out_name": "ViT-B-32.pt",
}


def _models_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(script_dir, "models")
    os.makedirs(models_dir, exist_ok=True)
    return models_dir


def _snapshot(models_dir, repo_id, sub_dir):
    local_model_path = os.path.join(models_dir, sub_dir)
    print(f"开始下载: {repo_id} -> {local_model_path}")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_model_path,
            local_dir_use_symlinks=False,
        )
        print(f"成功下载: {repo_id}")
    except Exception as e:
        print(f"下载 {repo_id} 失败: {e}")
        print("请确认已 hf auth login 并设置 HF_TOKEN（尤其 Llama/Gemma 等 gated 模型）。")


def download_llms(models_dir):
    for m in LLM_MODELS:
        _snapshot(models_dir, m["repo_id"], m["sub_dir"])


def download_embeddings(models_dir):
    for m in EMBED_MODELS:
        _snapshot(models_dir, m["repo_id"], m["sub_dir"])


def download_clip(models_dir):
    """下载 open_clip 的 CLIP 权重到 models/clip/ViT-B-32.pt。

    open_clip 会把预训练权重缓存到本地；这里额外把权重文件复制到 data_paths 约定的
    models/clip/<model>.pt，使 DeviceDisambiguationTool 离线可直接加载。
    """
    clip_dir = os.path.join(models_dir, "clip")
    os.makedirs(clip_dir, exist_ok=True)
    try:
        import open_clip
        import torch
    except Exception:
        print("未安装 open_clip_torch / torch，跳过 CLIP 下载。")
        print("  安装：pip install open_clip_torch torch pillow")
        return
    name = CLIP_OPEN_CLIP["model_name"]
    pretrained = CLIP_OPEN_CLIP["pretrained"]
    out_path = os.path.join(clip_dir, CLIP_OPEN_CLIP["out_name"])
    print(f"开始下载 CLIP: {name}/{pretrained} -> {out_path}")
    try:
        model, _, _ = open_clip.create_model_and_transforms(name, pretrained=pretrained)
        torch.save(model.state_dict(), out_path)
        print(f"成功保存 CLIP 权重: {out_path}")
    except Exception as e:
        print(f"下载/保存 CLIP 失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="HomeClaw 模型下载（LLM / CLIP / embedding）")
    parser.add_argument("--llm", action="store_true", help="下载文本 LLM")
    parser.add_argument("--clip", action="store_true", help="下载 CLIP 视觉模型（视觉消歧）")
    parser.add_argument("--embed", action="store_true", help="下载 sentence-transformers 嵌入模型（向量记忆）")
    args = parser.parse_args()

    # 未指定任何开关 → 下载全部
    download_all = not (args.llm or args.clip or args.embed)

    models_dir = _models_dir()
    print(f"models 目录: {models_dir}")

    if download_all or args.llm:
        download_llms(models_dir)
    if download_all or args.embed:
        download_embeddings(models_dir)
    if download_all or args.clip:
        download_clip(models_dir)


if __name__ == "__main__":
    main()
