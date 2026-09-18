"""scene 包（P2 + P6）：场景数据结构 + HomeBench/SAGE 两套场景 + 3D JSON 导出。"""
from homeclaw.scene.schema import Scene, Room, DeviceSlot
from homeclaw.scene.homebench_scene import build_homebench_scene, ALL_ROOMS
from homeclaw.scene.sage_scene import (
    build_sage_scene,
    coverage_report,
    assert_full_coverage,
    scene_device_fullnames,
    SAGE_REQUIRED_DEVICES,
)
from homeclaw.scene.export import (
    export_scene_json,
    export_scene_with_live,
    scene_to_dict,
)

__all__ = [
    "Scene", "Room", "DeviceSlot",
    "build_homebench_scene", "ALL_ROOMS", "build_sage_scene",
    "coverage_report", "assert_full_coverage", "scene_device_fullnames",
    "SAGE_REQUIRED_DEVICES",
    "export_scene_json", "export_scene_with_live", "scene_to_dict",
]
