/**
 * 坐标系单点转换：数据侧 Z-up（schema.py 的 size=(w,d,h)、pos=(x,y,z)，z 为高度），
 * Three.js 默认 Y-up。全前端只在这一个文件里做 (x, y, z) → (x, z, y) 转换，
 * 杜绝「3D 摆出来躺平」（对齐 06 方案 §3.1 / §9 的坐标风险单点收敛）。
 */
import type { Vec3 } from "../types";

/** 位置：Z-up → Y-up。数据 (x, y, z) → three [x, z, y]。 */
export function toThreePos(p: Vec3): [number, number, number] {
  const [x, y, z] = p;
  return [x, z, y];
}

/**
 * 尺寸：数据 size=(w, d, h)（宽/进深/高，Z-up）→ three BoxGeometry args [w, h, d]。
 * three 的 Box args 顺序是 (width=x, height=y, depth=z)，故高 h 放中间。
 */
export function toThreeSize(s: Vec3): [number, number, number] {
  const [w, d, h] = s;
  return [w, h, d];
}

/** yaw（绕竖直轴）：数据里的度 → three 里绕 Y 轴的弧度。 */
export function yawToThree(yawDeg: number): number {
  return (-yawDeg * Math.PI) / 180;
}
