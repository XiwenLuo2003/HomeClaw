/**
 * 状态 → 视觉编码（06 方案 §5）。把设备的 live_state / live_attributes / exists
 * 映射为 three 材质的颜色、发光色与发光强度，实现「状态变化驱动 3D」。
 */
import type { DeviceNode } from "../types";

export interface DeviceVisual {
  color: string;        // 基础色
  emissive: string;     // 自发光色
  emissiveIntensity: number;
  opacity: number;
  outline: string | null; // 描边色（on 时绿色描边）
  dimmed: boolean;        // 干扰设备（exists=false）灰显
}

/** 有效状态：优先实时 live_state，回退初始 state。 */
export function effectiveState(d: DeviceNode): string | null {
  return d.live_state ?? d.state;
}

function num(attrs: Record<string, unknown> | null, key: string): number | null {
  if (!attrs) return null;
  const v = attrs[key];
  if (typeof v === "number") return v;
  // 后端 get_status 的 attributes 为 {key: {value: ...}} 嵌套结构，取其 value。
  if (v && typeof v === "object" && typeof (v as { value?: unknown }).value === "number") {
    return (v as { value: number }).value;
  }
  return null;
}

/** 温度属性键名：空调用 temperature，冰箱用 fridge_temperature。 */
function tempKey(type: string): string | null {
  if (type === "air_conditioner") return "temperature";
  if (type === "fridge") return "fridge_temperature";
  return null;
}

/** 温度 → 冷暖色温：低温偏蓝、高温偏橙（线性插值）。 */
function tempColor(t: number): string {
  const lo = 16, hi = 30;
  const k = Math.max(0, Math.min(1, (t - lo) / (hi - lo)));
  const r = Math.round(80 + k * 175);
  const g = Math.round(140 + k * 40);
  const b = Math.round(255 - k * 195);
  return `rgb(${r},${g},${b})`;
}

export function deviceVisual(d: DeviceNode): DeviceVisual {
  // 干扰设备（HomeBench exists=false）：灰色半透明，明确「不存在」。
  if (!d.exists) {
    return {
      color: "#6b7280", emissive: "#000000", emissiveIntensity: 0,
      opacity: 0.28, outline: null, dimmed: true,
    };
  }

  const st = effectiveState(d);
  const on = st === "on" || st === "open" || st === "playing" || st === "cleaning";
  const attrs = d.live_attributes;

  if (!on) {
    return {
      color: "#4b5563", emissive: "#111827", emissiveIntensity: 0.02,
      opacity: 0.9, outline: null, dimmed: false,
    };
  }

  // on：自发光 + 绿色描边
  let emissive = "#22c55e";
  let intensity = 0.6;

  // 灯亮度 → 发光强度线性映射（0~100 → 0.3~1.4）
  const brightness = num(attrs, "brightness");
  if (d.type === "light" && brightness !== null) {
    intensity = 0.3 + (Math.max(0, Math.min(100, brightness)) / 100) * 1.1;
    emissive = "#fbbf24"; // 灯用暖黄发光
  }

  // 空调/冰箱温度 → 冷暖色温（按设备类型取对应温度键）
  const tk = tempKey(d.type);
  const temperature = tk ? num(attrs, tk) : null;
  if (temperature !== null) {
    emissive = tempColor(temperature);
    intensity = 0.7;
  }

  return {
    color: "#e5e7eb", emissive, emissiveIntensity: intensity,
    opacity: 1, outline: "#22c55e", dimmed: false,
  };
}

/** 供上方 badge 显示的数值型属性（音量/亮度/温度/香薰强度）。 */
export function deviceBadge(d: DeviceNode): string | null {
  const a = d.live_attributes;
  if (!a) return null;
  const vol = num(a, "volume");
  if (vol !== null) return `vol ${vol}`;
  const intensity = num(a, "intensity");
  if (intensity !== null) return `lv ${intensity}`;
  const tk = tempKey(d.type);
  const temp = tk ? num(a, tk) : null;
  if (temp !== null) return `${temp}°`;
  const bright = num(a, "brightness");
  if (bright !== null) return `${bright}%`;
  return null;
}
