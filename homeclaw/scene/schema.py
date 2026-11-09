"""场景数据结构 schema（P2 + P6）。

一次设计到位：房间拓扑 + 设备清单 + 3D 字段（坐标位/朝向/尺寸），
这样 P2 建场景与 P6 导出 3D JSON 复用同一结构，避免返工。

层级：Scene -> Room[] -> DeviceSlot[]
  - Scene    ：一套完整智能家居场景（来源 homebench / sage）
  - Room     ：房间，含 3D 位置(pos)、尺寸(size)、以及该房间的设备槽位
  - DeviceSlot：房间内某设备的槽位，含设备类型、初始 state/attributes、3D 位置，
   以及 exists 标记（False = HomeBench 风格的"干扰/不存在设备"）

to_home_status() 把 Scene 转成 SimulateExecutor 可直接消费的 home_status 字典；
to_json() 导出含 3D 坐标的完整结构，供前端 3D 可视化（P6）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


Vec3 = Tuple[float, float, float]


@dataclass
class DeviceSlot:
    """房间内一个设备槽位。"""

    device_type: str                         # 设备类型（须在 device_map 中）
    name: Optional[str] = None               # 槽位名（默认取 device_type）
    state: Optional[str] = None              # 初始 state
    attributes: Optional[Dict[str, Any]] = None  # 初始 attributes（None=用设备默认）
    exists: bool = True   # False=HomeBench 风格干扰设备（不进 home_status）
    # 3D 字段（P6）：相对房间局部坐标
    pos: Vec3 = (0.0, 0.0, 0.0)              # 局部坐标 (x,y,z)，米
    yaw: float = 0.0                         # 朝向（度）
    model: Optional[str] = None              # 3D 模型标识（前端资源名，可选）
    # SAGE 实景空间锚点（如 "by the credenza" / "by the fireplace" / "by the plant"）：
    # SAGE 的 device_resolution 维度靠这些自然语言锚点定位具体设备，HomeBench 无此概念。
    anchors: Optional[List[str]] = None
    # SAGE 多模态字段（P7）：实景照片 + 真实设备 UUID。
    # SAGE 用 CLIP 做「口语空间描述 ↔ 实景照片」图文消歧，图片文件名即设备 UUID。
    # 仅需消歧的同类多实例设备（4 灯 + 2 电视）配图；fridge/dishwasher 无需消歧故留空。
    # HomeBench 场景无此二字段（None），3D 浮层自然退化为纯状态卡片。
    image: Optional[str] = None          # 实景照片相对路径，如 "sage/images/<uuid>.jpg"
    device_uuid: Optional[str] = None    # 对齐 SAGE testcases 的真实设备 UUID

    def slot_name(self) -> str:
        return self.name or self.device_type


@dataclass
class Room:
    """一个房间。"""

    name: str
    slots: List[DeviceSlot] = field(default_factory=list)
    # 3D 字段（P6）：房间在楼层平面中的位置与尺寸
    pos: Vec3 = (0.0, 0.0, 0.0)              # 房间原点 (x,y,z)，米
    size: Vec3 = (4.0, 3.0, 2.8)             # 长宽高 (w,d,h)，米

    def add(self, slot: DeviceSlot) -> "Room":
        self.slots.append(slot)
        return self

    def existing_slots(self) -> List[DeviceSlot]:
        return [s for s in self.slots if s.exists]


@dataclass
class Scene:
    """一套完整场景。"""

    name: str
    source: str = "custom"                   # homebench / sage / custom
    rooms: List[Room] = field(default_factory=list)

    def add_room(self, room: Room) -> "Room":
        self.rooms.append(room)
        return room

    def get_room(self, name: str) -> Optional[Room]:
        for r in self.rooms:
            if r.name == name:
                return r
        return None

    # ---------------------------------------------------------------- #
    # 转换为 SimulateExecutor 可消费的 home_status（只含 exists=True 的设备）
    # ---------------------------------------------------------------- #
    def to_home_status(self) -> Dict[str, Any]:
        """导出 HomeBench 风格 home_status 字典（供 SimulateExecutor 构建）。"""
        from homeclaw.devices.device import device_map
        home: Dict[str, Any] = {}
        for room in self.rooms:
            rd: Dict[str, Any] = {"room_name": room.name}
            for slot in room.existing_slots():
                if slot.device_type not in device_map:
                    continue
                # 用设备默认实例拿到 state/attributes，再按槽位覆盖
                cls = device_map[slot.device_type]
                try:
                    obj = cls(slot.state) if slot.state is not None else cls()
                except TypeError:
                    obj = cls()
                attrs = slot.attributes if slot.attributes is not None else obj.attributes
                rd[slot.slot_name()] = {
                    # device_type 让执行器按"类型"实例化，而非按 slot 名——
                    # SAGE 同类多实例（nightstand_light/fireplace_light… 均为 light）靠此正确构建。
                    "device_type": slot.device_type,
                    "state": slot.state if slot.state is not None else getattr(obj, "state", None),
                    "attributes": attrs,
                }
            home[room.name] = rd
        return home

    def to_methods(self) -> List[Dict[str, Any]]:
        """导出 method 清单（每个存在设备的 operations 签名），供注入 prompt。"""
        import inspect
        from homeclaw.devices.device import device_map
        methods: List[Dict[str, Any]] = []
        for room in self.rooms:
            for slot in room.existing_slots():
                if slot.device_type not in device_map:
                    continue
                obj = device_map[slot.device_type]()
                for op_name, fn in getattr(obj, "operations", {}).items():
                    params = []
                    try:
                        sig = inspect.signature(fn)
                        for pname, p in sig.parameters.items():
                            ann = p.annotation
                            ptype = ann.__name__ if isinstance(ann, type) else str(ann)
                            params.append({"name": pname, "type": ptype})
                    except (ValueError, TypeError):
                        pass
                    methods.append({
                        "room_name": room.name,
                        "device_name": slot.slot_name(),
                        "operation": op_name,
                        "parameters": params,
                    })
        return methods

    # ---------------------------------------------------------------- #
    # 导出 3D 可视化 JSON（P6）
    # ---------------------------------------------------------------- #
    def to_json(self, live_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """导出含 3D 坐标的完整场景结构（供前端 3D 渲染 / P7）。

        live_status：可选，传入 executor.snapshot() 的实时状态字典
        （{room:{device:{state, attributes}}}）。若提供，则设备节点会附带
        实时 state/attributes（live_state / live_attributes），供 3D 场景
        动态渲染"真实设备动作"（P7 演示）。
        """
        def _live(room_name, dev_name):
            if not live_status:
                return None, None
            entry = (live_status.get(room_name, {}) or {}).get(dev_name)
            if not isinstance(entry, dict):
                return None, None
            return entry.get("state"), entry.get("attributes")

        rooms_out = []
        for room in self.rooms:
            devs = []
            for s in room.slots:
                live_state, live_attrs = _live(room.name, s.slot_name())
                devs.append({
                    "name": s.slot_name(),
                    "type": s.device_type,
                    "exists": s.exists,
                    "state": s.state,
                    "pos": list(s.pos),
                    "yaw": s.yaw,
                    "model": s.model,
                    "anchors": list(s.anchors) if s.anchors else [],
                    "image": s.image,
                    "device_uuid": s.device_uuid,
                    "live_state": live_state,
                    "live_attributes": live_attrs,
                })
            rooms_out.append({
                "name": room.name,
                "pos": list(room.pos),
                "size": list(room.size),
                "devices": devs,
            })
        return {"name": self.name, "source": self.source, "rooms": rooms_out}
