import { useEffect, useState } from 'react';
import { Clock3, FileText, Mic, Square, Volume2, ArrowUpRight } from 'lucide-react';
import { api, duration, templateLabels, type Meeting, type Notify, type Status } from './api';
import { Empty, PageTitle, Wave } from './components';

export default function Live({status, refresh, notify, open}: {status:Status;refresh:()=>Promise<void>;notify:Notify;open:(id:string)=>void}) {
  const [title,setTitle] = useState('새로운 회의');
  const [template,setTemplate] = useState('meeting');
  const [notion,setNotion] = useState(false);
  const [mid,setMid] = useState<string|null>(status.current_id);
  const [meeting,setMeeting] = useState<Meeting|null>(null);
  const [busy,setBusy] = useState(false);
  const [now,setNow] = useState(Date.now()/1000);
  useEffect(()=>{ if(status.current_id) setMid(status.current_id); },[status.current_id]);
  useEffect(()=>{
    if(!mid) return;
    let alive = true;
    const poll = () => api<Meeting>(`/meetings/${mid}`).then(v=>{if(alive) setMeeting(v);}).catch(()=>{});
    void poll(); const timer=setInterval(poll,1800); return()=>{alive=false;clearInterval(timer);};
  },[mid]);
  useEffect(()=>{const t=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(t);},[]);
  async function toggle() {
    setBusy(true);
    try {
      if(status.recording) { await api('/recording/stop','POST'); notify('녹음이 저장되었습니다. 남은 전사와 회의록 생성을 이어갑니다.'); }
      else { const result = await api<Meeting>('/recording/start','POST',{title,template,notion}); setMid(result.id);setMeeting(result);notify('시스템 오디오 녹음을 시작했습니다.'); }
      await refresh();
    } catch(e) { notify((e as Error).message,true); } finally {setBusy(false);}
  }
  const elapsed = meeting ? (meeting.ended || now)-meeting.created : 0;
  const texts=meeting?.chunks.filter(c=>c.text) || [];
  const keys=meeting?.state.key_points || [];
  return <>
    <PageTitle title="놓치지 않고, 기록하세요." sub="PC에서 재생되는 소리를 회의록으로 남깁니다."/>
    <section className="recording-toolbar" aria-label="녹음 제어">
      <label className="title-field">회의 제목<input value={title} maxLength={200} onChange={e=>setTitle(e.target.value)} disabled={status.recording}/></label>
      <label className="template-field">템플릿<select value={template} onChange={e=>setTemplate(e.target.value)} disabled={status.recording}>{Object.entries(templateLabels).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
      <div className="source-field"><span className="field-label">입력 소스</span><div className="source-control" title={status.device||'Windows 기본 출력 장치를 자동으로 따라갑니다.'}><Volume2 size={18}/><span>시스템 오디오 · 마이크 꺼짐</span></div></div>
      <div className="recording-clock"><strong>{duration(elapsed)}</strong><Wave level={status.recording ? status.level : 0}/></div>
      <button className={`primary record-button ${status.recording?'stop':''}`} disabled={busy||!title.trim()} onClick={toggle}>{status.recording?<Square size={18}/>:<Mic size={21}/>} {busy?'처리 중…':status.recording?'종료 및 요약':'녹음 시작'}</button>
    </section>
    {status.notion_configured && <label className="check-line"><input type="checkbox" checked={notion} disabled={status.recording} onChange={e=>setNotion(e.target.checked)}/> 완료 후 Notion에도 저장</label>}
    {(status.capture_error||meeting?.capture_warning) && <div className="notice warning">{status.capture_error||meeting?.capture_warning}</div>}
    {meeting?.error && <div className="notice warning">{meeting.error} <button onClick={()=>api(`/meetings/${meeting.id}/retry`,'POST').then(()=>notify('재시도를 요청했습니다.')).catch(e=>notify(e.message,true))}>다시 시도</button></div>}
    <div className="live-panels">
      <section className="panel transcript-panel"><div className="panel-heading"><h2>실시간 전사</h2><span><Clock3 size={15}/> 약 30초마다 업데이트</span></div>
        {texts.length ? <div className="transcript-list">{texts.map(c=><article key={c.id}><time>{duration(c.start)}</time><p>{c.text}</p></article>)}</div> : <Empty title={status.recording?'시스템 오디오를 듣고 있어요':'첫 번째 이야기를 기다리고 있어요'}>{status.recording?'첫 전사는 약 20~40초 후 표시됩니다.':'녹음을 시작하면 전사 내용이 여기에 표시됩니다.'}</Empty>}
      </section>
      <section className="panel note-panel"><div className="panel-heading"><h2>핵심 노트</h2>{keys.length>0&&<span>10분 단위 정리</span>}</div>
        {keys.length ? <div className="key-notes">{keys.map((text,i)=><p key={i}><span>{String(i+1).padStart(2,'0')}</span>{text}</p>)}</div> : <Empty type="note">대화가 쌓이면 핵심 내용을 정리합니다.</Empty>}
        {meeting && !status.recording && <button className="note-link" onClick={()=>open(meeting.id)}><FileText size={17}/> 회의록 열기 <ArrowUpRight size={17}/></button>}
      </section>
    </div>
  </>;
}
