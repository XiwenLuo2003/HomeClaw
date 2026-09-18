/** 房间：半透明盒子 + 地板 + 房间名标签（06 方案 §3：room.pos/size → Y-up）。 */
import { Edges, Text } from "@react-three/drei";
import type { RoomNode } from "./types";
import { toThreePos, toThreeSize } from "./lib/toThree";
import Device from "./Device";
import type { DeviceNode } from "./types";

interface Props {
  room: RoomNode;
  onPick: (d: DeviceNode, room: RoomNode) => void;
  pulses: Record<string, number>;
}

export default function Room({ room, onPick, pulses }: Props) {
  const [rx, ry, rz] = toThreePos(room.pos);
  const [w, h, d] = toThreeSize(room.size);
  // 盒子几何以中心为原点，房间原点在角落，故整体平移半个尺寸把角对齐到 room.pos。
  const cx = rx + w / 2;
  const cy = ry + h / 2;
  const cz = rz + d / 2;

  return (
    <group>
      {/* 房间外壳：半透明盒子 + 描边 */}
      <mesh position={[cx, cy, cz]}>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color="#1f2a44" transparent opacity={0.08} depthWrite={false} />
        <Edges color="#3b4d78" />
      </mesh>

      {/* 地板 */}
      <mesh position={[cx, ry + 0.01, cz]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color="#141b2e" transparent opacity={0.55} />
      </mesh>

      {/* 房间名 */}
      <Text
        position={[cx, ry + h + 0.25, cz]}
        fontSize={0.32}
        color="#93a4c8"
        anchorX="center"
        anchorY="bottom"
      >
        {room.name}
      </Text>

      {/* 房间内设备：设备局部 pos 叠加到房间原点 */}
      {room.devices.map((dev) => (
        <Device
          key={dev.name}
          device={dev}
          origin={[rx, ry, rz]}
          onPick={() => onPick(dev, room)}
          pulse={pulses[`${room.name}.${dev.name}`] ?? 0}
        />
      ))}
    </group>
  );
}
