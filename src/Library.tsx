import { useEffect, useState } from 'react';
import { ArrowUpRight, Search, Star, Link2, Pencil, Check, X } from 'lucide-react';
import { api, duration, statusLabels, templateLabels, type Meeting, type Notify } from './api';
import { Empty, Loading, PageTitle } from './components';

export default function Library({open,notify}: {open:(id:string)=>void;notify:Notify}) {
  const [renameId,setRenameId]=useState<string|null>(null);const [draft,setDraft]=useState('');const [saving,setSaving]=useState(false);
  const [q,setQ]=useState('');const [favorite,setFavorite]=useState(false);
  const [list,setList]=useState<Meeting[]>([]);const [loading,setLoading]=useState(true);
  useEffect(()=>{
    let alive=true;
    const load=()=>api<Meeting[]>(`/meetings?q=${encodeURIComponent(q)}&favorite=${favorite}`).then(v=>{if(alive){setList(v);setLoading(false);}}).catch(e=>{if(alive){notify(e.message,true);setLoading(false);}});
    const debounce=setTimeout(load,200);const timer=setInterval(load,5000);
    return()=>{alive=false;clearTimeout(debounce);clearInterval(timer);};
  },[q,favorite,notify]);
  async function star(m:Meeting) {try{await api(`/meetings/${m.id}`,'PATCH',{favorite:!m.favorite});setList(list.map(v=>v.id===m.id?{...v,favorite:m.favorite?0:1}:v));}catch(e){notify((e as Error).message,true);}}
  async function rename(m:Meeting){if(!draft.trim()||saving)return;setSaving(true);try{await api(`/meetings/${m.id}`,'PATCH',{title:draft.trim()});setList(v=>v.map(row=>row.id===m.id?{...row,title:draft.trim()}:row));setRenameId(null);notify('제목을 변경했습니다.');}catch(e){notify((e as Error).message,true);}finally{setSaving(false);}}
  return <>
    <PageTitle title="회의록 라이브러리"/>
    <div className="library-tools"><div className="search"><Search size={19}/><input aria-label="회의록 검색" placeholder="제목, 내용, 전사 또는 태그 검색" value={q} onChange={e=>setQ(e.target.value)}/></div><button className={favorite?'selected':''} onClick={()=>setFavorite(!favorite)}><Star size={17}/> 즐겨찾기</button><span className="muted">{list.length}개의 기록</span></div>
    {loading?<Loading/>:list.length===0?<div className="library-empty"><Empty type="note" title={q?'검색 결과가 없습니다':'아직 기록된 회의가 없어요'}>{q?'다른 검색어로 찾아보세요.':'라이브 전사에서 첫 번째 녹음을 시작하세요.'}</Empty></div>:<div className="meeting-table"><div className="table-heading"><span>회의록</span><span>날짜 / 길이</span><span>상태</span><span>연결</span><span/></div>{list.map(m=><div className="meeting-row" key={m.id}>
      <div className="meeting-name"><button className="icon-button" aria-label={`${m.title} 즐겨찾기`} onClick={()=>star(m)}><Star size={17} fill={m.favorite?'#237a69':'none'} color={m.favorite?'#237a69':'currentColor'}/></button>{renameId===m.id?<form className="inline-rename" onSubmit={e=>{e.preventDefault();void rename(m);}}><input autoFocus aria-label="새 회의록 제목" value={draft} maxLength={200} disabled={saving} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'&&!saving)setRenameId(null);if(e.key==='Enter'&&e.nativeEvent.isComposing)e.preventDefault();}}/><button className="icon-button" aria-label="제목 저장" disabled={saving||!draft.trim()}><Check size={17}/></button><button type="button" className="icon-button" aria-label="제목 변경 취소" disabled={saving} onClick={()=>setRenameId(null)}><X size={17}/></button></form>:<><button className="title-link" onClick={()=>open(m.id)}><strong>{m.title}</strong><span>{templateLabels[m.template]} {m.tags&&` · ${m.tags}`}</span></button><button className="icon-button rename-button" aria-label={`${m.title} 제목 변경`} onClick={()=>{setDraft(m.title);setRenameId(m.id);}}><Pencil size={15}/></button></>}</div>
      <div className="date-cell">{new Date(m.created*1000).toLocaleDateString('ko-KR')}<small>{duration((m.ended||Date.now()/1000)-m.created)}</small></div>
      <div><span className={`status-label ${m.status==='complete'?'done':''}`}><i/>{statusLabels[m.status]||m.status}</span>{m.pending>0&&<small className="muted">대기 {m.pending}개</small>}</div>
      <span className="muted">{m.notion_url?<><Link2 size={17}/> Notion</>:'—'}</span><button className="icon-button" aria-label={`${m.title} 열기`} onClick={()=>open(m.id)}><ArrowUpRight size={18}/></button>
    </div>)}</div>}
  </>;
}
