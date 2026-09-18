/** R3F 画布：光照 + 相机 + 轨道控制器 + 渲染所有房间/设备。 */
import { Canvas } from "@react-three/fiber";
import { OrbitControls, GizmoHelper, GizmoViewport, Grid } from "@react-three/drei";
import type { SceneData, DeviceNode, RoomNode } from "./types";
import Room from "./Room";

interface Props {
  scene: SceneData;
  onPick: (d: DeviceNode, room: RoomNode) => void;
  pulses: Record<string, number>;
}

export default function SceneCanvas({ scene, onPick, pulses }: Props) {
  return (
    <Canvas camera={{ position: [8, 9, 14], fov: 45 }} shadows>
      <color attach="background" args={["#0d1117"]} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 18, 8]} intensity={1.1} castShadow />
      <hemisphereLight args={["#8899cc", "#111827", 0.4]} />

      <Grid
        args={[60, 60]}
        cellColor="#233150"
        sectionColor="#2f4472"
        infiniteGrid
        fadeDistance={45}
        position={[0, 0, 0]}
      />

      {scene.rooms.map((room) => (
        <Room key={room.name} room={room} onPick={onPick} pulses={pulses} />
      ))}

      <OrbitControls makeDefault enableDamping target={[6, 1, 3]} />
      <GizmoHelper alignment="bottom-right" margin={[70, 70]}>
        <GizmoViewport axisColors={["#f87171", "#4ade80", "#60a5fa"]} labelColor="white" />
      </GizmoHelper>
    </Canvas>
  );
}
