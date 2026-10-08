import { useEffect, useState, useRef } from 'react';
import { ArrowLeft, Copy, Download, ExternalLink, FolderOpen, Save, Send, Star, Video, RotateCw, Trash2 } from 'lucide-react';
import { api, download, duration, statusLabels, type Meeting, type Notify, type Chunk } from './api';
import { Loading, Markdown } from './components';

export default function Detail({id,back,notify}: {id:string;back:()=>void;notify:Notify}) {
  const [m,setM]=useState<Meeting|null>(null);const [tab,setTab]=useState('summary');const [edit,setEdit]=useState(false);
  const [title,setTitle]=useState('');const [summary,setSummary]=useState('');const [notes,setNotes]=useState('');const [tags,setTags]=useState('');const [video,setVideo]=useState('');
  const [targetSeq,setTargetSeq]=useState<number|null>(null);const transcriptRefs=useRef<Record<number,HTMLElement|null>>({});
  useEffect(()=>{if(tab==='transcript'&&targetSeq!==null){const el=transcriptRefs.current[targetSeq];el?.scrollIntoView({behavior:'smooth',block:'center'});el?.focus({preventScroll:true});}},[tab,targetSeq]);
  const [busy,setBusy]=useState(false);const [source,setSource]=useState<Chunk|null>(null);
  useEffect(()=>{if(!source)return;function close(e:KeyboardEvent){if(e.key==='Escape')setSource(null);}window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close);},[source]);
  function accept(v:Meeting){setM(v);setTitle(v.title);setSummary(v.summary);setNotes(v.notes);setTags(v.tags);setVideo(v.video_path);}
  useEffect(()=>{let active=true;void api<Meeting>(`/meetings/${id}`).then(v=>{if(active)accept(v);}).catch(e=>notify(e.message,true));return()=>{active=false;};},[id,notify]);
  useEffect(()=>{
    if(!m||m.status==='complete'||edit)return;
    const timer=setInterval(()=>api<Meeting>(`/meetings/${id}`).then(v=>{setM(v);setSummary(v.summary);}).catch(()=>{}),2000);return()=>clearInterval(timer);
  },[id,m?.status,edit]);
  async function run(fn:()=>Promise<unknown>,success:string){setBusy(true);try{await fn();notify(success);if(!edit)accept(await api<Meeting>(`/meetings/${id}`));}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}}
  if(!m)return <Loading/>;
  function jump(chapter:string){
    const ref=chapter.match(/#chunk-(\d+)/);const time=chapter.match(/\[(\d+):(\d+):(\d+)\]/);
    const seconds=time?Number(time[1])*3600+Number(time[2])*60+Number(time[3]):0;
    const byId=ref?m!.chunks.find(c=>c.seq===Number(ref[1])):undefined;
    const chunk=byId||m!.chunks.filter(c=>c.start<=seconds).slice(-1)[0]||m!.chunks[0];
    if(chunk){setTargetSeq(chunk.seq);setTab('transcript');setSource(null);}
  }
  const allText=`# ${m.title}\n\n작성일: ${new Date(m.created*1000).toLocaleString('ko-KR')}\n\n${m.summary}\n\n## 메모\n${m.notes}\n\n## 전사 원문\n${m.transcript}`;
  return <>
    <button className="back-link" onClick={back}><ArrowLeft size={17}/> 라이브러리로</button>
    <div className="detail-heading"><div>{edit?<input className="title-editor" aria-label="회의록 제목" value={title} onChange={e=>setTitle(e.target.value)}/>:<h1>{m.title}</h1>}<p>{new Date(m.created*1000).toLocaleString('ko-KR')}<span>·</span>{duration((m.ended||Date.now()/1000)-m.created)}<span>·</span>{statusLabels[m.status]}</p></div><button className="icon-button" aria-label="즐겨찾기" onClick={()=>run(()=>api(`/meetings/${id}`,'PATCH',{favorite:!m.favorite}),'즐겨찾기를 변경했습니다.')}><Star fill={m.favorite?'#237a69':'none'}/></button></div>
    <div className="detail-actions"><button disabled={busy||edit||m.status!=='complete'} onClick={()=>{if(window.confirm('저장된 전사로 주제별 요약과 원문 링크를 다시 생성합니다. API 비용이 발생하며 기존 요약은 백업됩니다. 진행할까요?'))void run(()=>api(`/meetings/${id}/regenerate`,'POST'),'새 형식으로 요약을 생성합니다.');}}><RotateCw size={16}/> 원문 연결 요약 만들기</button><button disabled={busy} onClick={()=>run(()=>navigator.clipboard.writeText(allText),'AI용 전체 내용을 복사했습니다.')}><Copy size={16}/> AI용 전체 복사</button><button disabled={busy} onClick={()=>run(()=>download(id,'md'),'Markdown 파일을 내보냈습니다.')}><Download size={16}/> Markdown</button><button disabled={busy} onClick={()=>run(()=>download(id,'txt'),'TXT 파일을 내보냈습니다.')}>TXT</button><button disabled={busy} onClick={()=>run(()=>download(id,'json'),'JSON 파일을 내보냈습니다.')}>JSON</button><button disabled={busy||!m.summary} onClick={()=>run(()=>api(`/meetings/${id}/notion`,'POST'),'Notion 전송을 예약했습니다.')}><Send size={16}/> {m.notion_url?'Notion 재전송':'Notion 전송'}</button>{m.notion_url&&<a className="button" href={m.notion_url} target="_blank" rel="noreferrer"><ExternalLink size={16}/> Notion 열기</a>}<button disabled={busy} onClick={()=>run(()=>api(`/meetings/${id}/open-folder`,'POST'),'로컬 폴더를 열었습니다.')}><FolderOpen size={16}/><span>폴더</span></button></div>
    {m.capture_warning&&<div className="notice warning">{m.capture_warning}</div>}
    {(m.error||m.chunks.some(c=>c.error))&&<div className="notice warning">{m.error||m.chunks.find(c=>c.error)?.error}<button onClick={()=>run(()=>api(`/meetings/${id}/retry`,'POST'),'재시도를 요청했습니다.')}><RotateCw size={15}/> 다시 시도</button></div>}
    <div className="detail-tabs" role="tablist">{[['summary','요약'],['chapters','챕터'],['transcript','전사 원문'],['notes','메모']].map(([key,name])=><button role="tab" aria-selected={tab===key} className={tab===key?'active':''} key={key} onClick={()=>setTab(key)}>{name}</button>)}<div className="tab-spacer"/>{edit?<><button onClick={()=>{accept(m);setEdit(false);}}>취소</button><button className="save-button" disabled={busy||!title.trim()} onClick={()=>run(async()=>{const result=await api<Meeting>(`/meetings/${id}`,'PATCH',{title,summary,notes,tags,video_path:video});accept(result);setEdit(false);},'변경 내용을 저장했습니다.')}><Save size={16}/> 저장</button></>:<button disabled={m.status!=='complete'} onClick={()=>setEdit(true)}>편집</button>}</div>
    {source&&<aside className="source-panel" role="region" aria-label="선택한 전사 원문"><div><strong>전사 원문 · {duration(source.start)}–{duration(source.start+source.duration)}</strong><button aria-label="원문 닫기" onClick={()=>setSource(null)}>닫기</button></div><p>{source.text}</p><small>저장된 음성 전사입니다. 이름·수치 등에는 음성 인식 오류가 있을 수 있습니다.</small></aside>}
    <div className="detail-content">
      {tab==='summary'&&(edit?<textarea className="document-editor" aria-label="요약 편집" value={summary} onChange={e=>setSummary(e.target.value)}/>:m.summary?<Markdown text={m.summary} chunks={m.chunks} onSource={setSource}/>:<p className="muted">전사 큐가 완료되면 AI 회의록을 생성합니다. API 오류가 있다면 설정과 잔액을 확인하세요.</p>)}
      {tab==='chapters'&&<div className="chapters">{(m.state.chapters||[]).length?(m.state.chapters||[]).map((chapter,i)=><button className="chapter-link" key={i} onClick={()=>jump(chapter)}>{chapter.replace(/\s*\[[^\]]*\]\(#chunk-\d+\)/g,'')}</button>):<p className="muted">핵심 노트가 생성되면 챕터가 표시됩니다.</p>}</div>}
      {tab==='transcript'&&<div className="transcript-list">{m.chunks.length?m.chunks.map(c=><article key={c.id} ref={el=>{transcriptRefs.current[c.seq]=el;}} tabIndex={-1} className={targetSeq===c.seq?'transcript-target':''}><time>{duration(c.start)}</time><p>{c.text||({done:'무음 구간',pending:'전사 대기 중',uploading:'전사 중',capturing:'녹음 중',failed:'복구 확인 필요'}[c.status]||c.status)}</p></article>):<p className="muted">저장된 오디오가 없습니다.</p>}</div>}
      {tab==='notes'&&(edit?<textarea className="document-editor" aria-label="메모 편집" placeholder="나만의 메모를 남기세요." value={notes} onChange={e=>setNotes(e.target.value)}/>:<p className="preserve">{m.notes||'편집 버튼을 눌러 메모를 남기세요.'}</p>)}
    </div>
    <div className="detail-meta"><label>태그{edit?<input value={tags} onChange={e=>setTags(e.target.value)} placeholder="쉼표로 구분"/>:<span>{m.tags||'태그 없음'}</span>}</label><label>원본 영상{edit?<input value={video} onChange={e=>setVideo(e.target.value)} placeholder="D:\Recordings\meeting.mp4"/>:<span>{m.video_path||'연결된 영상 없음'}</span>}</label>{m.video_path&&<button onClick={()=>run(()=>api(`/meetings/${id}/open-video`,'POST'),'원본 영상을 열었습니다.')}><Video size={16}/> 영상 열기</button>}</div>
    <div className="storage-foot"><span>{m.cleaned?'임시 오디오 정리 완료':'임시 오디오 보관 중'}</span>{!m.cleaned&&m.status==='complete'&&<button onClick={()=>{if(window.confirm('영구 보관된 회의록과 전사는 유지하고 임시 오디오만 삭제할까요?'))void run(()=>api(`/meetings/${id}/cleanup`,'POST'),'임시 오디오를 정리했습니다.');}}><Trash2 size={14}/> 오디오 정리</button>}</div>
  </>;
}
