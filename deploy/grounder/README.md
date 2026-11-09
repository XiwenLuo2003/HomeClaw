# Qwen3-VL-4B Grounder 推理服务

该目录只包含推理部署，不包含数据集、LoRA、GRPO、Optimizer 或任何训练代码。

Grounder 是 `device-disambiguation` Skill 内部工具。Agent 主模型仍是 GPT、Gemini 等在线模型。Host 只在拓扑锚定后仍存在多个视觉候选时调用本服务。

## 部署约束

- 需要具备 NVIDIA Container Toolkit 的 GPU 服务器。
- 模型通过 `GROUNDING_MODEL_ID` 和 `GROUNDING_MODEL_REVISION` 固定；生产环境禁止使用未固定且不可审计的浮动权重。
- `image_uri` 只接受 data URI、`IMAGE_ROOT` 内文件，或 `GROUNDING_ALLOWED_IMAGE_HOSTS` 白名单中的 HTTPS 地址，避免 SSRF。
- `/health` 是 readiness：模型未加载完成或加载失败时返回 503；它不表示一次 Grounding 结果正确。
- `/v1/ground:batch` 接受最多 16 个请求，用于上游批量调度；单进程仍通过模型锁保护显存。
- 构建镜像会在 Docker 内安装依赖；HomeClaw 不会在宿主机自动安装任何包。

示例命令仅供部署人员手工执行：

```powershell
docker compose -f deploy/grounder/compose.yaml build
docker compose -f deploy/grounder/compose.yaml up -d
```
