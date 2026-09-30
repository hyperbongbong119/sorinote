import { AudioLines, FileText, LoaderCircle } from 'lucide-react';
import { useState, useId, type ReactNode } from 'react';
import { duration, type Chunk } from './api';

export function Wave({level = 0, large = false}: {level?: number; large?: boolean}) {
  return <div className={`wave ${large ? 'large' : ''}`} aria-hidden="true">{Array.from({length:large ? 5 : 25},(_,i)=><i key={i} style={{height:large ? [20,38,62,38,20][i] : 3 + level * (8 + (Math.sin(i*1.9)+1)*14)}} />)}</div>;
}
export function Empty({type = 'audio', title, children}: {type?: 'audio'|'note'; title?: string; children:ReactNode}) {
  return <div className="empty">{type === 'audio' ? <Wave large/> : <FileText size={52} strokeWidth={1.2}/>} {title && <h3>{title}</h3>}<p>{children}</p></div>;
}
export function PageTitle({title, sub, action}: {title:string;sub?:string;action?:ReactNode}) {
  return <div className="page-heading"><div><h1>{title}</h1>{sub&&<p>{sub}</p>}</div>{action}</div>;
}
export function Loading() { return <div className="loading"><LoaderCircle className="spin" size={22}/> 불러오는 중…</div>; }
export function Brand() { return <div className="brand"><AudioLines size={38} strokeWidth={2}/><div><strong>소리노트</strong><span>SORINOTE</span></div></div>; }
// Only source anchors and emphasis are interpreted; arbitrary HTML/URLs remain plain text.
function SourceLink({chunk,onSource}:{chunk:Chunk;onSource:(c:Chunk)=>void}) {
  const previewId=useId();
  const [position,setPosition]=useState<{left:number;top:number}|null>(null);
  function preview(el:HTMLElement){const r=el.getBoundingClientRect();const width=Math.min(360,window.innerWidth-32);setPosition({left:Math.max(16,Math.min(r.left,window.innerWidth-width-16)),top:Math.max(16,Math.min(r.bottom+8,window.innerHeight-190))});}
  return <span className="source-anchor"><button className="source-link" aria-label={`${duration(chunk.start)} 원문 보기`} aria-describedby={position?previewId:undefined} onMouseEnter={e=>preview(e.currentTarget)} onMouseLeave={()=>setPosition(null)} onFocus={e=>preview(e.currentTarget)} onBlur={()=>setPosition(null)} onKeyDown={e=>{if(e.key==='Escape')setPosition(null);}} onClick={()=>{setPosition(null);onSource(chunk);}}>↗ {duration(chunk.start)}</button>{position&&<span role="tooltip" id={previewId} className="source-tooltip" style={position}><strong>전사 원문 · {duration(chunk.start)}</strong><span>{chunk.text.slice(0,280)}{chunk.text.length>280?'…':''}</span><small>클릭하면 전체 원문을 확인합니다.</small></span>}</span>;
}
export function Markdown({text,chunks=[],onSource}: {text:string;chunks?:Chunk[];onSource?:(c:Chunk)=>void}) {
  const sources=new Map(chunks.map(c=>[c.seq,c]));
  function inline(line:string){return line.split(/(\[[^\]]*\]\(#chunk-\d+\)|\*\*[^*]+\*\*)/g).map((part,i)=>{
    const citation=part.match(/^\[[^\]]*\]\(#chunk-(\d+)\)$/);const chunk=citation?sources.get(Number(citation[1])):undefined;
    if(citation)return chunk&&onSource?<SourceLink key={i} chunk={chunk} onSource={onSource}/>:<small key={i} className="muted"> [근거 확인 필요]</small>;
    if(part.startsWith('**')&&part.endsWith('**'))return <strong key={i}>{part.slice(2,-2)}</strong>;
    return part;
  });}
  return <div className="markdown">{text.split('\n').map((line,i)=>{
    if (line.startsWith('### ')) return <h3 key={i}>{inline(line.slice(4))}</h3>;
    if (line.startsWith('## ')) return <h3 key={i}>{inline(line.slice(3))}</h3>;
    if (line.startsWith('# ')) return <h2 key={i}>{inline(line.slice(2))}</h2>;
    const bullet=line.match(/^(\s*)(?:[-*]|\d+\.) (.*)$/);
    if(bullet)return <div className={`summary-bullet ${bullet[1].length?'nested':''}`} key={i}><span aria-hidden="true">•</span><p>{inline(bullet[2])}</p></div>;
    return line?<p key={i}>{inline(line)}</p>:<div className="paragraph-space" key={i}/>;
  })}</div>;
}
