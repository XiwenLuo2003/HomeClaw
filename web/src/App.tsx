import { useCallback, useEffect, useRef, useState } from "react";
import "./styles.css";
import type { SceneData, SceneList, DeviceNode, RoomNode } from "./types";
import { fetchScene, fetchSceneList, postAct } from "./lib/api";
import SceneCanvas from "./SceneCanvas";
import DevicePopup from "./DevicePopup";

const POLL_MS = 1000;

export default function App() {
  const [list, setList] = useState<SceneList | null>(null);
  const [source, setSource] = useState<string>("sage");
  const [scene, setScene] = useState<SceneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<{ dev: DeviceNode; room: RoomNode } | null>(null);
  const [pulses, setPulses] = useState<Record<string, number>>({});
  const [manualAction, setManualAction] = useState("");
  const [log, setLog] = useState<string[]>([]);

  // 上一帧各设备有效状态，用于检测「刚刚变化」触发脉冲。
  const prevStates = useRef<Record<string, string | null>>({});

  const detectPulses = useCallback((data: SceneData) => {
    const next: Record<string, number> = {};
    const now = performance.now();
    for (const room of data.rooms) {
      for (const d of room.devices) {
        const key = `${room.name}.${d.name}`;
        const cur = d.live_state ?? d.state;
        if (prevStates.current[key] !== undefined && prevStates.current[key] !== cur) {
          next[key] = now;
        }
        prevStates.current[key] = cur;
      }
    }
    if (Object.keys(next).length) setPulses((p) => ({ ...p, ...next }));
  }, []);

  const load = useCallback(async (src: string) => {
    try {
      const data = await fetchScene(src);
      detectPulses(data);
      setScene(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [detectPulses]);

  // 场景清单
  useEffect(() => {
    fetchSceneList().then((l) => { setList(l); setSource(l.default); }).catch((e) => setError(String(e)));
  }, []);

  // 切换场景时重置状态基线
  useEffect(() => {
    prevStates.current = {};
    setPicked(null);
    load(source);
  }, [source, load]);

  // 1s 轮询实时联动（§6）
  useEffect(() => {
    const t = setInterval(() => load(source), POLL_MS);
    return () => clearInterval(t);
  }, [source, load]);

  const runAction = useCallback(async (action: string) => {
    try {
      const res = await postAct(action, source);
      detectPulses(res.scene);
      setScene(res.scene);
      const ok = (res.result as any)?.status ?? "?";
      setLog((l) => [`${action} → ${ok}`, ...l].slice(0, 8));
      // 同步刷新选中设备
      if (picked) {
        const r = res.scene.rooms.find((x) => x.name === picked.room.name);
        const d = r?.devices.find((x) => x.name === picked.dev.name);
        if (r && d) setPicked({ dev: d, room: r });
      }
    } catch (e) {
      setLog((l) => [`ERR ${action}: ${e}`, ...l].slice(0, 8));
    }
  }, [source, detectPulses, picked]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">HomeClaw · 3D 智能家居场景</div>
        <div className="scene-switch">
          {list?.scenes.map((s) => (
            <button
              key={s.source}
              className={s.source === source ? "active" : ""}
              onClick={() => setSource(s.source)}
              title={`${s.rooms} 房间 · ${s.devices} 设备`}
            >
              {s.name}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="error">后端未连接？{error}（请先启动 uvicorn web.server:app --port 8000）</div>}

      <div className="stage">
        {scene && (
          <SceneCanvas
            scene={scene}
            pulses={pulses}
            onPick={(dev, room) => setPicked({ dev, room })}
          />
        )}

        {/* 指令面板：手动下发动作文本，驱动实时联动 */}
        <div className="cmd">
          <div className="cmd-title">指令面板（source: {source}）</div>
          <div className="cmd-row">
            <input
              value={manualAction}
              placeholder="bedroom.nightstand_light.turn_on()"
              onChange={(e) => setManualAction(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && manualAction.trim()) runAction(manualAction.trim()); }}
            />
            <button onClick={() => manualAction.trim() && runAction(manualAction.trim())}>执行</button>
          </div>
          <div className="cmd-log">
            {log.map((l, i) => <div key={i} className="mono">{l}</div>)}
          </div>
          <div className="legend">
            <span><i className="dot on" /> on / 发光</span>
            <span><i className="dot off" /> off</span>
            <span><i className="dot dim" /> 干扰设备</span>
            <span>● = SAGE 实景</span>
          </div>
        </div>

        <DevicePopup
          device={picked?.dev ?? null}
          roomName={picked?.room.name ?? null}
          onClose={() => setPicked(null)}
          onAct={runAction}
        />
      </div>
    </div>
  );
}
