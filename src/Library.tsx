import { useEffect, useState } from 'react';
import { ArrowUpRight, Search, Star, Link2, Pencil, Check, X, Trash2, RotateCcw } from 'lucide-react';
import { api, duration, statusLabels, templateLabels, type Meeting, type Notify } from './api';
import { Empty, Loading, PageTitle } from './components';

export default function Library({open,notify}: {open:(id:string)=>void;notify:Notify}) {
  const [renameId,setRenameId]=useState<string|null>(null);const [draft,setDraft]=useState('');const [saving,setSaving]=useState(false);
  const [deleteTarget,setDeleteTarget]=useState<Meeting|null>(null);const [deleting,setDeleting]=useState(false);
  const [deleted,setDeleted]=useState(false);
  const [q,setQ]=useState('');const [favorite,setFavorite]=useState(false);
  const [list,setList]=useState<Meeting[]>([]);const [loading,setLoading]=useState(true);
  useEffect(()=>{
    let alive=true;
    const load=()=>api<Meeting[]>(`/meetings?q=${encodeURIComponent(q)}&favorite=${favorite}&deleted=${deleted}`).then(v=>{if(alive){setList(v);setLoading(false);}}).catch(e=>{if(alive){notify(e.message,true);setLoading(false);}});
    const debounce=setTimeout(load,200);const timer=setInterval(load,5000);
    return()=>{alive=false;clearTimeout(debounce);clearInterval(timer);};
  },[q,favorite,deleted,notify]);
  async function star(m:Meeting) {try{await api(`/meetings/${m.id}`,'PATCH',{favorite:!m.favorite});setList(list.map(v=>v.id===m.id?{...v,favorite:m.favorite?0:1}:v));}catch(e){notify((e as Error).message,true);}}
  async function rename(m:Meeting){if(!draft.trim()||saving)return;setSaving(true);try{await api(`/meetings/${m.id}`,'PATCH',{title:draft.trim()});setList(v=>v.map(row=>row.id===m.id?{...row,title:draft.trim()}:row));setRenameId(null);notify('제목을 변경했습니다.');}catch(e){notify((e as Error).message,true);}finally{setSaving(false);}}
  async function remove(m:Meeting){setDeleting(true);try{await api(`/meetings/${m.id}`,'DELETE');setList(v=>v.filter(row=>row.id!==m.id));setDeleteTarget(null);notify('회의록을 삭제했습니다.');}catch(e){notify((e as Error).message,true);}finally{setDeleting(false);}}
  async function restore(m:Meeting){try{await api(`/meetings/${m.id}/restore`,'POST');setList(v=>v.filter(row=>row.id!==m.id));notify('회의록을 복원했습니다.');}catch(e){notify((e as Error).message,true);}}
  return <>
    <PageTitle title="회의록 라이브러리"/>
    <div className="library-tools"><div className="search"><Search size={19}/><input aria-label="회의록 검색" placeholder="제목, 내용, 전사 또는 태그 검색" value={q} onChange={e=>setQ(e.target.value)}/></div><button className={favorite?'selected':''} onClick={()=>setFavorite(!favorite)}><Star size={17}/> 즐겨찾기</button><button className={deleted?'selected':''} onClick={()=>{setDeleted(!deleted);setRenameId(null);}}>삭제된 회의록</button><span className="muted">{list.length}개의 기록</span></div>
    {loading?<Loading/>:list.length===0?<div className="library-empty"><Empty type="note" title={q?'검색 결과가 없습니다':'아직 기록된 회의가 없어요'}>{q?'다른 검색어로 찾아보세요.':'라이브 전사에서 첫 번째 녹음을 시작하세요.'}</Empty></div>:<div className="meeting-table"><div className="table-heading"><span>회의록</span><span>날짜 / 길이</span><span>상태</span><span>연결</span><span/></div>{list.map(m=><div className="meeting-row" key={m.id}>
      <div className="meeting-name"><button className="icon-button" aria-label={`${m.title} 즐겨찾기`} onClick={()=>star(m)}><Star size={17} fill={m.favorite?'#237a69':'none'} color={m.favorite?'#237a69':'currentColor'}/></button>{renameId===m.id?<form className="inline-rename" onSubmit={e=>{e.preventDefault();void rename(m);}}><input autoFocus aria-label="새 회의록 제목" value={draft} maxLength={200} disabled={saving} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'&&!saving)setRenameId(null);if(e.key==='Enter'&&e.nativeEvent.isComposing)e.preventDefault();}}/><button className="icon-button" aria-label="제목 저장" disabled={saving||!draft.trim()}><Check size={17}/></button><button type="button" className="icon-button" aria-label="제목 변경 취소" disabled={saving} onClick={()=>setRenameId(null)}><X size={17}/></button></form>:<><div className="library-title"><button className="title-text" disabled={deleted} onClick={()=>{setDraft(m.title);setRenameId(m.id);}} title="클릭해서 제목 변경"><strong>{m.title}</strong></button><span>{templateLabels[m.template]} {m.tags&&` · ${m.tags}`}</span></div><button className="icon-button rename-button" disabled={deleted} aria-label={`${m.title} 제목 변경`} onClick={()=>{setDraft(m.title);setRenameId(m.id);}}><Pencil size={15}/></button></>}</div>
      <div className="date-cell">{new Date(m.created*1000).toLocaleDateString('ko-KR')}<small>{duration((m.ended||Date.now()/1000)-m.created)}</small></div>
      <div><span className={`status-label ${m.status==='complete'?'done':''}`}><i/>{statusLabels[m.status]||m.status}</span>{m.pending>0&&<small className="muted">대기 {m.pending}개</small>}</div>
      <span className="muted">{m.notion_url?<><Link2 size={17}/> Notion</>:'—'}</span><div className="row-actions">{deleted?<button className="icon-button" aria-label={`${m.title} 복원`} onClick={()=>void restore(m)}><RotateCcw size={18}/></button>:<><button className="icon-button" aria-label={`${m.title} 열기`} onClick={()=>open(m.id)}><ArrowUpRight size={18}/></button><button className="icon-button" disabled={m.status==='recording'} aria-label={`${m.title} 삭제`} onClick={()=>setDeleteTarget(m)}><Trash2 size={17}/></button></>}</div>
    </div>)}</div>}
    {deleteTarget&&<div className="dialog-backdrop" onKeyDown={e=>{if(e.key==='Escape'&&!deleting)setDeleteTarget(null);}}><section className="delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-heading" aria-describedby="delete-description"><h2 id="delete-heading">회의록을 삭제할까요?</h2><p id="delete-description">“{deleteTarget.title}”<br/>삭제된 회의록에서 다시 복원할 수 있습니다.</p><div><button autoFocus disabled={deleting} onClick={()=>setDeleteTarget(null)}>취소</button><button className="primary" disabled={deleting} onClick={()=>void remove(deleteTarget)}>{deleting?'삭제 중…':'삭제'}</button></div></section></div>}
  </>;
}
