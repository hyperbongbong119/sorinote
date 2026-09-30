import { useCallback, useEffect, useState } from 'react';
import { AudioLines, Database, FileText, Link2, Settings2, ShieldCheck, X } from 'lucide-react';
import { api, connect, type Status } from './api';
import { Brand, Loading } from './components';
import Live from './Live';
import Library from './Library';
import Detail from './Detail';
import Settings from './Settings';

export default function App() {
  const [page,setPage]=useState('live');const [detail,setDetail]=useState<string|null>(null);
  const [status,setStatus]=useState<Status|null>(null);const [failure,setFailure]=useState('');
  const [toast,setToast]=useState<{message:string;error:boolean}|null>(null);
  const notify=useCallback((message:string,error=false)=>setToast({message,error}),[]);
  const refresh=useCallback(async()=>{setStatus(await api<Status>('/status'));setFailure('');},[]);
  useEffect(()=>{let active=true;let timer:ReturnType<typeof setInterval>;void connect().then(async()=>{if(!active)return;await refresh();timer=setInterval(()=>refresh().catch(()=>setFailure('로컬 엔진과 연결이 끊겼습니다. 앱을 다시 실행하세요.')),1500);}).catch(e=>setFailure(e.message));return()=>{active=false;clearInterval(timer);};},[refresh]);
  useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(null),6500);return()=>clearTimeout(timer);},[toast]);
  const open=(id:string)=>{setDetail(id);setPage('library');};
  const nav=[{id:'live',name:'라이브 전사',icon:AudioLines},{id:'library',name:'회의록 라이브러리',icon:FileText},{id:'settings',name:'설정',icon:Settings2}];
  return <div className="app-shell">
    <aside className="sidebar"><Brand/><nav aria-label="주 메뉴">{nav.map(({id,name,icon:Icon})=><button key={id} aria-label={name} className={page===id?'active':''} onClick={()=>{setPage(id);setDetail(null);}}><Icon size={21}/><span>{name}</span>{id==='live'&&status?.recording&&<i className="record-dot"/>}</button>)}</nav></aside>
    <div className="main-shell"><header className="topbar"><span>워크스페이스 <b>/</b> <strong>{detail?'회의록 상세':nav.find(n=>n.id===page)?.name}</strong></span><span className="connection"><i className={status?.ai_configured?'online':''}/>{status?.ai_configured?'API 키 저장됨':'API 연결 필요'}</span></header>
      <main>{(failure||status?.worker_error)&&<div className="notice warning" role="alert">{failure||status?.worker_error}</div>}{!status?<Loading/>:page==='live'?<Live status={status} refresh={refresh} notify={notify} open={open}/>:page==='settings'?<Settings status={status} refresh={refresh} notify={notify}/>:detail?<Detail key={detail} id={detail} back={()=>setDetail(null)} notify={notify}/>:<Library open={open} notify={notify}/>}</main>
      <footer className="statusbar"><span><Database size={15}/> 대기 중인 오디오 {status?.queued||0}개</span><button onClick={()=>{setPage('settings');setDetail(null);}}><Link2 size={15}/>{status?.notion_configured?'Notion 연결 설정됨':'Notion 선택적 연결'}</button></footer>
    </div>
    {toast&&<div className={`toast ${toast.error?'error':''}`} role={toast.error?'alert':'status'}><ShieldCheck size={18}/><span>{toast.message}</span><button className="icon-button" aria-label="알림 닫기" onClick={()=>setToast(null)}><X size={16}/></button></div>}
  </div>;
}
