/**
 * 设备详情浮层（06 方案 §4.2）：
 *  - SAGE 设备（有 image/anchors）→ 实景照片 + 空间锚点，直观展示「靠实景+锚点消歧」；
 *  - HomeBench 设备（无 image/anchors）→ 自然退化为纯状态卡片。
 * 降级声明：这里展示的是 SAGE 实景资产的可视化，CLIP 图文消歧由后端完成，
 * 前端并未在浏览器跑 VLM 推理（§4.2 诚实标注）。
 */
import type { DeviceNode } from "./types";
import { imageUrl } from "./lib/api";
import { effectiveState } from "./lib/visual";

interface Props {
  device: DeviceNode | null;
  roomName: string | null;
  onClose: () => void;
  onAct: (action: string) => void;
}

/** 依设备类型给几个可点的常用动作，驱动 /act 演示实时联动。 */
function quickActions(room: string, d: DeviceNode): { label: string; action: string }[] {
  const full = `${room}.${d.name}`;
  const on = effectiveState(d) === "on";
  switch (d.type) {
    case "light":
      return [
        { label: on ? "关灯" : "开灯", action: `${full}.${on ? "turn_off" : "turn_on"}()` },
        { label: "亮度 80", action: `${full}.set_brightness(80)` },
      ];
    case "tv":
    case "frame_tv":
      return [{ label: on ? "关闭" : "打开", action: `${full}.${on ? "turn_off" : "turn_on"}()` }];
    case "dishwasher":
      return [{ label: on ? "停止" : "启动", action: `${full}.${on ? "turn_off" : "turn_on"}()` }];
    default:
      return [{ label: on ? "关闭" : "打开", action: `${full}.${on ? "turn_off" : "turn_on"}()` }];
  }
}

export default function DevicePopup({ device, roomName, onClose, onAct }: Props) {
  if (!device || !roomName) return null;
  const st = effectiveState(device);
  const isSage = !!device.image;

  return (
    <div className="popup">
      <div className="popup-head">
        <span>{roomName}.{device.name}</span>
        <button className="popup-close" onClick={onClose}>×</button>
      </div>

      {isSage ? (
        <>
          <img className="popup-img" src={imageUrl(device.image!)} alt={device.name} />
          <div className="popup-tag sage">SAGE 实景消歧</div>
        </>
      ) : (
        <div className="popup-tag plain">HomeBench · 无实景（纯状态卡片）</div>
      )}

      <dl className="popup-meta">
        <dt>类型</dt><dd>{device.type}</dd>
        <dt>状态</dt><dd>{st ?? "—"}</dd>
        {device.exists ? null : <><dt>存在</dt><dd>否（HomeBench 干扰设备）</dd></>}
        {device.device_uuid && (<><dt>UUID</dt><dd className="mono">{device.device_uuid}</dd></>)}
        {device.anchors.length > 0 && (
          <><dt>空间锚点</dt><dd>{device.anchors.join(" · ")}</dd></>
        )}
        {device.live_attributes && Object.keys(device.live_attributes).length > 0 && (
          <><dt>属性</dt><dd className="mono">{JSON.stringify(device.live_attributes)}</dd></>
        )}
      </dl>

      {device.exists && (
        <div className="popup-actions">
          {quickActions(roomName, device).map((a) => (
            <button key={a.action} onClick={() => onAct(a.action)}>{a.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
