# Gemini 전사 및 추가 요약 API

설정에서 전사 서비스로 **Google Gemini**를 선택하면 Gemini 키 하나로 전사와 요약을 모두 사용할 수 있습니다. 기본 모델은 3.5 Flash-Lite입니다. 2.5 Flash-Lite는 신규 사용자에게 제공되지 않을 수 있으며 목록에 표시되어도 실제 생성이 거절될 수 있습니다. 짧은 오디오 구간을 16kHz 모노 WAV로 변환해 Google generateContent API로 보내며, 응답이 잘리거나 차단되면 원본을 보존하고 재시도합니다.

요약 서비스에는 **DeepSeek, Mistral, Grok (xAI)**도 추가되었습니다. 각각 `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`를 사용하며 공식 서비스 주소로만 전송합니다. OpenRouter를 이용하면 다른 회사의 모델도 모델 ID로 선택할 수 있습니다.

사용 순서: 서비스 선택 → 해당 API 키 입력 → 설정 저장 → 모델 목록 조회 → 요약 테스트. 모델의 제공 여부는 계정별로 다를 수 있습니다. 변경한 전사 모델은 새 녹음에 적용됩니다.

2026-10-07 Gemini 실제 키로 한국어 오디오 전사와 JSON 상태 생성, 한국어 요약을 검증했습니다. 다른 추가 서비스는 모의 응답으로 검증했습니다. 자동 테스트에서는 오디오 변환, Gemini 정상/차단/불완전 응답, API 키 분리, 설정 저장을 확인했습니다. Gemini 전사 사용량은 현재 회의록의 요약 토큰 누계에 포함하지 않습니다.

공식 API 문서: [Gemini](https://ai.google.dev/api/generate-content), [DeepSeek](https://api-docs.deepseek.com/api/create-chat-completion/), [Mistral](https://docs.mistral.ai/api/endpoint/chat), [Grok](https://docs.x.ai/developers/model-capabilities/legacy/chat-completions).

---

# API 선택과 연결

2026-09-30 공식 API 문서 기준으로 지원 방식을 검토했다. 아래는 한국어 품질 벤치마크 순위가 아니라 기능·비용·연결 방식에 따른 비교다. 계정별 제공 모델과 실제 생성 가능 여부는 설정의 조회/테스트로 확인한다.

| 용도 | 서비스·모델 후보 | 선택 기준 |
|---|---|---|
| 전사 | OpenAI GPT-4o Transcribe / Mini | 기존 구성 유지. Mini는 비용 절감 후보. |
| 전사 | Groq Whisper Large V3 / Turbo | 공식 기준 V3 $0.111/시간, Turbo $0.04/시간. 10초 최소 청구가 있으나 앱은 주로 20~40초 청크 사용. 한국어 인식 정확도는 같은 실제 녹음으로 비교할 것. |
| 요약 | OpenAI GPT-5.6 Luna | 기존 요약과 비교할 기준 모델. |
| 요약 | Claude Haiku 4.5 / Sonnet 5.5 | Haiku로 시작하고 복잡한 강의 정리를 Sonnet과 비교. Claude Messages API를 직접 사용. |
| 요약 | Gemini Flash | Flash 계열 후보와 모델 목록 제공. Google generateContent API 사용. |
| 요약 | Groq Llama 3.3 70B / GPT-OSS | 전사와 요약을 같은 Groq 계정으로 운영하거나 공개 가중치 계열 비교. |
| 요약 | OpenRouter | 회사/모델 ID로 여러 요약 모델 비교. OpenRouter가 모델 운영사로 요청을 전달하는 중개 서비스임을 고려. |

## 사용 방법

1. 설정에서 전사 서비스/모델과 요약 서비스/모델을 선택한다.
2. 해당 서비스의 API 키를 입력하고 **설정 저장**을 누른다. 빈 키 입력은 기존 키를 유지한다.
3. **모델 목록 조회**로 저장된 키 인증과 목록을 확인한다. 요약 모델 ID는 직접 입력하거나 조회된 목록에서 선택할 수 있다.
4. **저장된 요약 모델 테스트**는 짧은 가상 문장으로 JSON 생성을 검증하며 소액 비용이 발생한다. 실제 녹음 내용은 이 테스트에 사용하지 않는다.
5. 새 녹음은 저장된 선택을 사용한다. 진행 중인 기록은 녹음 시작 시 선택을 유지한다. 기존 기록에서 **원문 연결 요약 만들기**를 선택하면 현재 요약 서비스/모델로 다시 생성한다.

전사에는 음성, 요약에는 전사된 텍스트가 선택한 서비스로 전송된다. 자동으로 다른 서비스로 전환하지 않는다. 서비스 오류·JSON 형식 오류·응답 잘림은 작업 실패로 남기고 원문을 유지한다. 모델 목록에는 텍스트 요약에 맞지 않는 모델도 있을 수 있으므로 실제 요약 테스트를 함께 사용한다.

키는 별도 `.env.local`의 `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`에 저장한다. 사용자 환경변수가 같은 이름으로 설정되어 있으면 해당 값이 우선한다. 임의 API 서버 URL, Azure/Bedrock 인증, 로컬 Ollama는 이번 지원 범위에 포함하지 않는다.

## 구현과 검증 범위

공통 프롬프트·원문 근거 처리·작업 큐는 유지하고, 서비스별 인증/요청/응답만 `backend/providers.py`로 분리했다. OpenAI Responses API, OpenAI 호환 Chat Completions(Groq/OpenRouter), Claude Messages, Gemini generateContent 네 방식을 사용한다. 추가 SDK 설치는 없다.

서비스별 요청 형식·인증 분리·응답 토큰 정규화·기존 DB 마이그레이션·작업별 모델 고정은 자동 테스트로 검증했다. Gemini는 실제 녹음 복구로 검증했으며 다른 추가 서비스는 모의 응답으로 검증했다. 다른 서비스의 실서비스 연결이나 동일 강의의 모델 간 품질/비용 비교는 완료하지 않았다. 서로 다른 모델로 재요약한 누적 토큰은 단일 모델 단가로 계산하면 안 된다.

## 공식 근거

- [Groq 음성 전사와 요금](https://console.groq.com/docs/speech-to-text)
- [Groq 모델 목록](https://console.groq.com/docs/models)
- [Claude 모델](https://platform.claude.com/docs/en/models/overview)
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Gemini OpenAI 호환 API](https://ai.google.dev/gemini-api/docs/openai)
- [OpenRouter API](https://openrouter.ai/docs/quickstart)

Gemini 한국어 전사는 시스템 지시로 한글 받아쓰기를 명시합니다. 긴 영문 응답은 문맥을 제거해 한 번 재시도하고, 계속 언어가 맞지 않으면 저장하지 않고 오디오를 보존합니다. 실제 영어 발화가 긴 구간은 언어 설정을 자동으로 변경해야 할 수 있습니다. 요약은 JSON 스키마를 사용하며 출력 한도 초과 시 최대 20,000 토큰까지 재시도합니다.
