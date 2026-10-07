import { useEffect, useState } from 'react';
import { api, type Notify } from './api';

type Source={id:string;name:string;kind:string};
type Result={device:string;duration:number;peak:number;rms:number;has_signal:boolean;audio:string;transcript?:string;api_error?:string};

export default function AudioInput({source,onChange,disabled,canTranscribe,notify}:{source:string;onChange:(source:string)=>void;disabled:boolean;canTranscribe:boolean;notify:Notify}) {
  const [sources,setSources]=useState<Source[]>([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState<Result|null>(null);
  async function load(){try{const r=await api<{sources:Source[]}>('/audio/sources');setSources(r.sources);setError('');}catch(e){setError((e as Error).message);}}
  useEffect(()=>{void load();},[]);
  async function test(transcribe:boolean){setBusy(true);setResult(null);try{setResult(await api<Result>('/audio/test','POST',{source,transcribe}));}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}}
  return <div className="settings-fields">
    <label>입력 소스<select value={source} disabled={disabled||busy} onChange={e=>{setResult(null);onChange(e.target.value);}}>
      {!sources.some(s=>s.id===source)&&<option value={source}>{source==='default'?'시스템 기본 출력 · 자동 전환':'저장된 장치 · 연결 확인 필요'}</option>}
      {sources.map(s=><option key={s.id} value={s.id}>{s.kind==='microphone'?'마이크':'시스템 소리'} · {s.name}</option>)}
    </select></label>
    <div className="audio-test-actions"><button disabled={busy||disabled} onClick={()=>void load()}>장치 목록 새로고침</button><button disabled={busy||disabled} onClick={()=>void test(false)}>5초 입력 테스트</button><button disabled={busy||disabled||!canTranscribe} onClick={()=>void test(true)}>5초 전사 API 테스트 · 소액 API 사용</button></div>
    <p className="field-hint">시스템 소리는 선택한 스피커·헤드폰에서 재생되는 소리를, 마이크는 주변 목소리를 녹음합니다. 테스트 중 소리를 재생하거나 말하세요. 전사 테스트는 저장된 전사 모델을 사용합니다.</p>
    {error&&<p role="alert">{error}</p>}
    {busy&&<p role="status">5초간 입력을 확인합니다. 전사 테스트는 API 응답까지 기다려 주세요.</p>}
    {result&&<div className="audio-test-result" role="status"><strong>{result.has_signal?'소리 입력 확인':'소리가 감지되지 않았습니다'}</strong><p>{result.device} · 수신 {result.duration.toFixed(1)}초 · 최대 음량 {Math.round(result.peak*100)}%</p><meter min={0} max={1} value={result.peak} aria-label="테스트 최대 음량"/><audio controls src={result.audio} aria-label="테스트 녹음 듣기"/>{result.transcript!==undefined&&<p><strong>전사 결과</strong><br/>{result.transcript||'인식된 발화가 없습니다.'}</p>}{result.api_error&&<p role="alert">{result.api_error}</p>}{!result.has_signal&&<p>입력 장치, 재생 음량, 마이크 권한을 확인한 뒤 다시 테스트하세요.</p>}</div>}
  </div>;
}
