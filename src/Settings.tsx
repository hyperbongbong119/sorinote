import { useState } from 'react';
import { Link2, Save, ShieldCheck } from 'lucide-react';
import { api, type Status, type Notify, type Provider } from './api';
import { PageTitle } from './components';

const names:Record<Provider,string>={openai:'OpenAI',groq:'Groq',gemini:'Google Gemini',anthropic:'Anthropic Claude',openrouter:'OpenRouter',deepseek:'DeepSeek',mistral:'Mistral',xai:'Grok (xAI)'};
const defaults:Record<Provider,string>={openai:'gpt-5.6-luna',groq:'llama-3.3-70b-versatile',gemini:'gemini-2.5-flash-lite',anthropic:'claude-haiku-4-5',openrouter:'openai/gpt-4.1-mini',deepseek:'deepseek-flash',mistral:'mistral-small-latest',xai:'grok-4.7'};
const suggestions:Record<Provider,string[]>={openai:['gpt-5.6-luna'],groq:['llama-3.3-70b-versatile','openai/gpt-oss-120b'],gemini:['gemini-2.5-flash-lite','gemini-3.1-flash-lite','gemini-3.5-flash-lite','gemini-3.8-flash'],anthropic:['claude-haiku-4-5','claude-sonnet-5-5'],openrouter:['openai/gpt-4.1-mini'],deepseek:['deepseek-flash','deepseek-v4-pro'],mistral:['mistral-small-latest','mistral-large-latest'],xai:['grok-4.7']};
const emptyKeys={openai_key:'',groq_key:'',gemini_key:'',anthropic_key:'',openrouter_key:'',deepseek_key:'',mistral_key:'',xai_key:'',notion_token:''};
const hints:Record<Provider,string>={openai:'기존 전사·요약을 그대로 사용할 때',groq:'Whisper 전사 또는 Llama·GPT-OSS 요약을 사용할 때',gemini:'하나의 Gemini 키로 음성 전사와 요약을 사용할 때',anthropic:'Haiku로 시작하거나 Sonnet으로 요약 품질을 비교할 때',openrouter:'여러 회사의 요약 모델을 하나의 API로 비교할 때',deepseek:'DeepSeek 모델로 요약할 때',mistral:'Mistral Small·Large로 요약할 때',xai:'Grok 모델로 요약할 때'};

const sttModels={openai:['gpt-4o-transcribe','gpt-4o-mini-transcribe'],groq:['whisper-large-v3-turbo','whisper-large-v3'],gemini:suggestions.gemini};

export default function Settings({status,refresh,notify}: {status:Status;refresh:()=>Promise<void>;notify:Notify}) {
  const [form,setForm]=useState({...status.settings,...emptyKeys});
  const [busy,setBusy]=useState(false);const [check,setCheck]=useState<Partial<Record<Provider,string>>>({});
  const [models,setModels]=useState<Partial<Record<Provider,string[]>>>({});
  const field=(name:keyof typeof form,value:string)=>setForm({...form,[name]:value});
  async function save(){setBusy(true);try{await api('/settings','PUT',form);setForm({...form,...emptyKeys});await refresh();notify('설정을 저장했습니다.');}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}}
  async function loadModels(provider:Provider){setBusy(true);try{const result=await api<{models:string[]}>(`/settings/models/${provider}`,'POST');setModels(v=>({...v,[provider]:result.models}));setCheck(v=>({...v,[provider]:`키 인증·모델 목록 조회 완료 (${result.models.length}개). 생성 가능 여부는 요약 테스트로 확인하세요.`}));}catch(e){setCheck(v=>({...v,[provider]:(e as Error).message}));}finally{setBusy(false);}}
  async function testSummary(){setBusy(true);try{await api('/settings/test-summary','POST');notify('저장된 요약 모델의 생성·JSON 응답을 확인했습니다.');}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}}
  return <>
    <PageTitle title="설정" sub="전사와 요약에 사용할 서비스를 선택하세요." action={<button className="primary" disabled={busy} onClick={save}><Save size={17}/> 설정 저장</button>}/>
    <div className="settings-page">
      <section className="settings-section"><div><h2>전사·요약 모델</h2><p>서로 다른 서비스를 조합할 수 있습니다.</p></div><div className="settings-fields">
        <div className="field-pair"><label>전사 서비스<select value={form.stt_provider} onChange={e=>{const p=e.target.value as keyof typeof sttModels;setForm({...form,stt_provider:p,stt_model:sttModels[p][0]});}}><option value="openai">OpenAI</option><option value="groq">Groq</option><option value="gemini">Google Gemini</option></select></label><label>전사 모델<select value={form.stt_model} onChange={e=>field('stt_model',e.target.value)}>{sttModels[form.stt_provider].map(model=><option key={model}>{model}</option>)}</select></label></div>
        <div className="field-pair"><label>요약 서비스<select value={form.summary_provider} onChange={e=>{const p=e.target.value as Provider;setForm({...form,summary_provider:p,summary_model:defaults[p]});}}>{Object.entries(names).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><label>요약 모델 ID<input list="summary-models" value={form.summary_model} onChange={e=>field('summary_model',e.target.value)} maxLength={160}/><datalist id="summary-models">{(models[form.summary_provider]||suggestions[form.summary_provider]).map(model=><option key={model} value={model}/>)}</datalist></label></div>
        <p className="field-hint">음성은 전사 서비스로, 전사된 글은 요약 서비스로 전송됩니다. 변경은 새 녹음과 요약 재생성부터 적용됩니다.</p>
        <button disabled={busy||!status.providers_configured[status.settings.summary_provider]} onClick={testSummary}>저장된 요약 모델 테스트 · 소액 API 사용</button>
      </div></section>
      <section className="settings-section"><div><h2>API 키</h2><p>사용할 서비스의 키만 입력하세요.<br/>기존 키는 비워 두면 유지됩니다.</p></div><div className="provider-cards">{(Object.keys(names) as Provider[]).map(provider=><div className="provider-key" key={provider}>
        <div><strong>{names[provider]} <span className="inline-status">{status.providers_configured[provider]?'저장됨':'미설정'}</span></strong><button disabled={busy||!status.providers_configured[provider]} onClick={()=>loadModels(provider)}><Link2 size={14}/> 모델 목록 조회</button></div>
        <label>{names[provider]} API 키<input type="password" autoComplete="off" value={form[`${provider}_key`]} onChange={e=>field(`${provider}_key`,e.target.value)} placeholder="새 키 또는 변경할 키"/></label><p className="provider-hint">{hints[provider]}</p>{check[provider]&&<p role="status" className="model-result">{check[provider]}</p>}
      </div>)}</div></section>
      <section className="settings-section"><div><h2>전사 품질</h2><p>한국어와 전문 용어를<br/>더 정확하게 기록합니다.</p></div><div className="settings-fields"><label>기본 언어<select value={form.language} onChange={e=>field('language',e.target.value)}><option value="ko">한국어</option><option value="en">영어</option><option value="ja">일본어</option><option value="">자동 감지</option></select></label><label>용어사전<textarea rows={4} value={form.glossary} onChange={e=>field('glossary',e.target.value)} placeholder="사람 이름, 회사명, 제품명, 전문 용어를 입력하세요." maxLength={1500}/></label><p className="field-hint">시스템 오디오만 녹음합니다. 발화 종료를 감지해 20~40초 단위로 전사합니다.</p></div></section>
      <section className="settings-section"><div><h2>파일 관리</h2></div><div className="settings-fields"><label>저장 위치<div className="path-display">{status.data_dir}\MeetingNotes</div></label><label>임시 오디오 정리<select value={form.retention} onChange={e=>field('retention',e.target.value)}><option value="immediate">모든 처리 완료 후 즉시</option><option value="day">완료 후 24시간 보관</option><option value="week">완료 후 7일 보관</option><option value="manual">직접 정리</option></select></label><p className="field-hint"><ShieldCheck size={16}/> 실패한 전사 또는 Notion 전송이 있으면 임시 오디오는 삭제하지 않습니다.</p></div></section>
      <section className="settings-section"><div><h2>Notion 연결 <span className="optional">선택</span></h2><p>원하는 회의록만 Notion에 전송합니다.<br/>Notion AI 구독은 필요하지 않습니다.</p></div><div className="settings-fields"><label>Integration 토큰<input type="password" autoComplete="off" value={form.notion_token} onChange={e=>field('notion_token',e.target.value)} placeholder={status.notion_configured?'연결 정보 저장됨 · 변경 시 입력':'Notion Integration 토큰'}/></label><label>상위 페이지 링크 또는 ID<input value={form.notion_parent} onChange={e=>field('notion_parent',e.target.value)} placeholder="https://www.notion.so/..."/></label><p className="field-hint">Notion에서 해당 페이지의 연결 메뉴에 Integration을 추가하세요. 이 앱의 연결은 ChatGPT의 Notion 연결과 별개입니다.</p></div></section>
    </div>
  </>;
}
