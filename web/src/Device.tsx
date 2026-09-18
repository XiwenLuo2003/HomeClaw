/**
 * 设备图元：状态着色（§5）+ 点击选中 + 动作瞬间 0.3s 高亮脉冲 + 数值 badge。
 * 无 glTF 资源时退化为按设备类型选形的基础图元（§9 风险应对）。
 */
import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Text, Billboard, Edges } from "@react-three/drei";
import type { Mesh } from "three";
import type { DeviceNode, Vec3 } from "./types";
import { toThreePos, yawToThree } from "./lib/toThree";
import { deviceVisual, deviceBadge, effectiveState } from "./lib/visual";

interface Props {
  device: DeviceNode;
  origin: [number, number, number]; // 房间原点（已 Y-up）
  onPick: () => void;
  pulse: number;                    // 上次动作触发的时间戳（用于脉冲动画）
}

/** 按设备类型选基础几何尺寸（无模型时的退化图元）。 */
function geomFor(type: string): [number, number, number] {
  switch (type) {
    case "light": return [0.28, 0.28, 0.28];
    case "tv":
    case "frame_tv": return [0.9, 0.5, 0.12];
    case "fridge": return [0.7, 1.4, 0.7];
    case "dishwasher": return [0.6, 0.8, 0.6];
    case "air_conditioner": return [0.8, 0.3, 0.25];
    default: return [0.4, 0.4, 0.4];
  }
}

export default function Device({ device, origin, onPick, pulse }: Props) {
  const meshRef = useRef<Mesh>(null);
  const localPos = toThreePos(device.pos as Vec3);
  const pos: [number, number, number] = [
    origin[0] + localPos[0],
    origin[1] + localPos[1] + 0.3, // 抬离地面
    origin[2] + localPos[2],
  ];
  const v = deviceVisual(device);
  const [gw, gh, gd] = geomFor(device.type);
  const badge = deviceBadge(device);
  const st = effectiveState(device);

  // 0.3s 高亮脉冲：动作触发后发光强度短暂拉高再回落。
  useFrame(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const mat = mesh.material as any;
    let boost = 0;
    if (pulse > 0) {
      const dt = (performance.now() - pulse) / 300; // 0.3s
      if (dt >= 0 && dt <= 1) boost = (1 - dt) * 1.5;
    }
    mat.emissiveIntensity = v.emissiveIntensity + boost;
  });

  return (
    <group position={pos} rotation={[0, yawToThree(device.yaw), 0]}>
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onPick(); }}
        onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { document.body.style.cursor = "auto"; }}
      >
        <boxGeometry args={[gw, gh, gd]} />
        <meshStandardMaterial
          color={v.color}
          emissive={v.emissive}
          emissiveIntensity={v.emissiveIntensity}
          transparent
          opacity={v.opacity}
          wireframe={v.dimmed}
        />
        {/* on 状态：绿色描边（§5，与 visual.ts 的 outline 对齐） */}
        {v.outline && <Edges scale={1.02} threshold={15} color={v.outline} />}
      </mesh>

      {/* 设备名 + 状态 + 多模态标记（有 image 的 SAGE 设备标 ●） */}
      <Billboard position={[0, gh / 2 + 0.22, 0]}>
        <Text fontSize={0.16} color="#cbd5e1" anchorX="center" anchorY="bottom">
          {device.image ? "● " : ""}{device.name}
          {st ? `  [${st}]` : ""}
        </Text>
      </Billboard>

      {/* 数值 badge（音量/亮度/温度） */}
      {badge && (
        <Billboard position={[0, gh / 2 + 0.45, 0]}>
          <Text fontSize={0.14} color="#fbbf24" anchorX="center" anchorY="bottom">
            {badge}
          </Text>
        </Billboard>
      )}
    </group>
  );
}
