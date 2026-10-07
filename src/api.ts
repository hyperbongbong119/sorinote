let token = '';
export async function connect() {
  const response = await fetch('/api/bootstrap');
  if (!response.ok) throw new Error('로컬 엔진에 연결할 수 없습니다.');
  token = (await response.json()).token;
}
export async function request(path: string, init: RequestInit = {}) {
  const response = await fetch('/api' + path, { ...init, headers: { 'Content-Type': 'application/json', 'X-Sorinote-Token': token, ...init.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : '입력 내용을 확인해 주세요.');
  }
  return response;
}
export async function api<T = unknown>(path: string, method = 'GET', body?: unknown): Promise<T> {
  return (await request(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })).json();
}
export async function download(mid: string, kind: string) {
  const response = await request(`/meetings/${mid}/export/${kind}`);
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a'); a.href = url; a.download = `sorinote-${mid.slice(0,8)}.${kind}`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export type Provider = 'openai'|'groq'|'gemini'|'anthropic'|'openrouter'|'deepseek'|'mistral'|'xai';
export type SettingsData = { audio_source:string; stt_provider:'openai'|'groq'|'gemini';summary_provider:Provider; stt_model: string; summary_model: string; language: string; glossary: string; retention: string; notion_parent: string; monthly_budget: string };
export type Status = { recording: boolean; current_id: string | null; level: number; device: string; capture_error: string; worker_error: string; queued: number; openai_configured: boolean; ai_configured:boolean; providers_configured:Record<Provider,boolean>; notion_configured: boolean; data_dir: string; settings: SettingsData };
export type Chunk = { id: number; seq: number; start: number; duration: number; status: string; text: string; error: string; attempts: number };
export type Meeting = { id: string; title: string; template: string; created: number; ended: number | null; status: string; summary: string; notes: string; tags: string; favorite: number; video_path: string; notion_requested: number; notion_status: string; notion_url: string; state: Record<string,string[]>; error: string; capture_warning: string; cleaned: number; chunks: Chunk[]; transcript: string; local_path: string; pending: number };
export const statusLabels: Record<string,string> = {recording:'녹음 중', processing:'처리 중', interrupted:'복구됨', summarizing:'요약 중', complete:'완료'};
export const templateLabels: Record<string,string> = {meeting:'회의', lecture:'강의 · Webinar', interview:'인터뷰', general:'일반'};
export function duration(seconds: number) { const s = Math.max(0, Math.floor(seconds)); return [Math.floor(s/3600),Math.floor(s/60)%60,s%60].map(v=>String(v).padStart(2,'0')).join(':'); }
export type Notify = (message: string, error?: boolean) => void;
