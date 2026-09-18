/** 与后端 scene_to_dict / Scene.to_json 严格对齐的数据契约（06 方案 §3）。 */

export type Vec3 = [number, number, number];

/** 单个设备节点（对应 schema.py to_json 的每个 device）。 */
export interface DeviceNode {
  name: string;
  type: string;
  exists: boolean;
  state: string | null;
  pos: Vec3;                 // 房间局部坐标，Z-up
  yaw: number;               // 朝向（度）
  model: string | null;
  anchors: string[];         // SAGE 空间锚点；HomeBench 为 []
  image: string | null;      // SAGE 实景照片相对路径 sage/images/<uuid>.jpg
  device_uuid: string | null;
  live_state: string | null; // executor 实时 state
  live_attributes: Record<string, unknown> | null;
}

export interface RoomNode {
  name: string;
  pos: Vec3;                 // 楼层平面位置，Z-up
  size: Vec3;                // (w, d, h)
  devices: DeviceNode[];
}

export interface SceneData {
  name: string;
  source: string;            // sage / homebench
  rooms: RoomNode[];
}

export interface SceneListItem {
  source: string;
  name: string;
  rooms: number;
  devices: number;
}

export interface SceneList {
  default: string;
  scenes: SceneListItem[];
}

export interface ActResult {
  result: Record<string, unknown>;
  scene: SceneData;
}
