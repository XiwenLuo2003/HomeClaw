/** 后端只读接口封装（全部走相对路径，dev 由 vite 反代到 FastAPI）。 */
import type { SceneData, SceneList, ActResult } from "../types";

const BASE = "/api";

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return (await r.json()) as T;
}

export function fetchSceneList(): Promise<SceneList> {
  return getJson<SceneList>(`${BASE}/scenes`);
}

export function fetchScene(source?: string): Promise<SceneData> {
  return source ? getJson<SceneData>(`${BASE}/scenes/${source}`)
                : getJson<SceneData>(`${BASE}/scene`);
}

export async function postAct(action: string, source: string): Promise<ActResult> {
  const r = await fetch(`${BASE}/act`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, source }),
  });
  if (!r.ok) throw new Error(`/act -> HTTP ${r.status}`);
  return (await r.json()) as ActResult;
}

/** SAGE 实景照片 URL：image 为 "sage/images/<uuid>.jpg"，后端静态映射到 /images/<uuid>.jpg。 */
export function imageUrl(image: string): string {
  const file = image.split("/").pop();
  return `/images/${file}`;
}
