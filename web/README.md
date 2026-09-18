# HomeClaw · P7 3D 场景可视化（web/）

把 P6 导出的场景（房间/设备/3D 坐标/实时状态）搬上浏览器，用 **Three.js + React Three Fiber** 渲染成可交互 3D 智能家居，并把 SAGE 实景照片消歧作为对比亮点。对应 [`../06-3D场景可视化实施方案.md`](../06-3D场景可视化实施方案.md)。

## 架构

```
浏览器 (R3F)  --/api--> Vite dev proxy --> FastAPI (web/server.py) --> SimulateExecutor(sim)
     ▲                                          │
     └────────── 1s 轮询 /scene ────────────────┘   /images/*.jpg 静态映射 data/sage/images/
```

- 后端：`web/server.py`，10 行级只读接口，复用 P6 的 `scene_to_dict(scene, executor)`，executor 走 `sim`，离线可复现，无需真机/数据库。
- 前端：`src/`，R3F 声明式渲染，状态变化驱动重着色。
- 坐标系：数据侧 Z-up，前端在 `src/lib/toThree.ts` 单点做 `(x,y,z)→(x,z,y)` 转换。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/scene` | 默认（SAGE）场景 + 实时状态的 3D JSON |
| GET | `/scenes` | 场景清单（sage / homebench） |
| GET | `/scenes/{source}` | 指定场景 + 实时状态 |
| POST | `/act` | 下发动作文本 `room.device.op(arg)`，驱动实时联动 |
| GET | `/images/<uuid>.jpg` | SAGE 实景照片（静态映射 `data/sage/images/`） |

## 运行

**1. 后端**
```bash
cd HomeClaw
pip install -r web/requirements.txt
uvicorn web.server:app --reload --port 8000
```

**2. 前端**
```bash
cd HomeClaw/web
npm install
npm run dev      # 打开 http://localhost:5173
```
Vite 已把 `/api`、`/images` 反代到 `127.0.0.1:8000`，前端全走相对路径，无 CORS 问题。

## 交互

- 顶部切换 **SAGE / HomeBench** 两套场景。
- 拖拽旋转 / 滚轮缩放（OrbitControls），右下角坐标 gizmo。
- 点击设备弹浮层：SAGE 设备显示**实景照片 + 空间锚点**（消歧对比亮点）；HomeBench 设备退化为**纯状态卡片**。
- 浮层内快捷动作或左下角指令面板输入动作文本 → `/act` → 1s 内 3D 里颜色变 + 0.3s 高亮脉冲。
- 状态编码：on = 自发光/绿描边；off = 灰；灯亮度 → 发光强度；空调/冰箱温度 → 冷暖色温；`exists=false` 干扰设备灰显线框。

## 降级声明

3D 里展示的是 SAGE **实景照片资产的可视化**；CLIP 图文消歧由后端（或降级实现）完成，前端不在浏览器跑 VLM 推理。

## 目录

```
web/
├── server.py            # FastAPI 只读接口
├── requirements.txt
├── package.json / vite.config.ts / tsconfig.json / index.html
└── src/
    ├── main.tsx / App.tsx / styles.css
    ├── SceneCanvas.tsx  # R3F 画布：相机/光照/控制器
    ├── Room.tsx         # 房间盒子 + 设备布局
    ├── Device.tsx       # 设备图元 + 状态着色 + 脉冲 + badge
    ├── DevicePopup.tsx  # 实景照片 + anchors 浮层（HomeBench 降级）
    ├── types.ts         # 与 to_json 对齐的数据契约
    └── lib/
        ├── toThree.ts   # Z-up → Y-up 单点转换
        ├── api.ts       # 后端接口封装
        └── visual.ts    # 状态 → 材质视觉映射
```
