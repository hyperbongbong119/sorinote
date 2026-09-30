# 소리노트 · Sorinote

Windows 시스템 오디오를 전사하고, 원문 링크가 있는 AI 회의록을 만드는 데스크톱 앱입니다.

## 주요 기능

- 시스템 오디오 녹음과 약 20~40초 단위 전사 (마이크 혼합 미지원)
- 주제별 요약, 원문 미리보기와 구간 열기
- 회의록 제목 수정, 검색, 즐겨찾기, 메모, Markdown/JSON 내보내기
- 전사: OpenAI / Groq
- 요약: OpenAI / Claude / Gemini / Groq / OpenRouter
- 선택적 Notion 페이지 전송
- SQLite 작업 큐와 중단된 처리 복구

전사에는 오디오가, 요약에는 전사 텍스트가 선택한 API 서비스로 전송됩니다. 각 서비스의 API 키와 사용 요금이 필요합니다. 키는 설치 파일과 분리된 `.env.local`에서 관리합니다.

## Windows 설치

배포 ZIP을 모두 압축 해제한 뒤 `install.cmd`를 실행합니다. 바탕화면의 **Sorinote**로 실행하고 설정에서 API 키와 모델을 지정하세요. Microsoft Edge WebView2 Runtime이 필요합니다.

[설치·환경변수 안내](docs/desktop.md) · [API 서비스 설정](docs/api-providers.md)

## 소스에서 실행

Windows, Python 3.11, Node.js가 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
npm ci
npm run build
Copy-Item .env.example .env.local
.\.venv\Scripts\python.exe run.py
```

브라우저에서 `http://127.0.0.1:18765`를 엽니다. 기존 `.env.local`이 있으면 복사 단계를 건너뛰세요. UI 개발은 백엔드 실행 후 `npm run dev`를 사용합니다.

## 테스트 및 패키징

```powershell
# 실제 키나 회의 자료를 사용하지 않는 회귀 테스트
.\.venv\Scripts\python.exe tools\acceptance.py

# Windows EXE와 설치 ZIP 빌드
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
powershell -ExecutionPolicy Bypass -File tools\build-desktop.ps1
```

자동 테스트 37개에는 작업 큐 복구, API 인증 분리, 제목 편집, 원문 링크, 출력 한도 재시도, 모의 네트워크·장치 장애가 포함됩니다. 실제 장시간 녹음, Bluetooth 전환, Notion 전송과 다른 API 제공자의 실서비스 연결은 별도 검증이 필요합니다.

## 데이터와 제한

- 개발 실행 데이터는 `data/`, 설치 앱의 기본 데이터는 `%LOCALAPPDATA%\Sorinote\data`에 저장됩니다.
- API 키, 녹음, 회의록, SQLite, 로그와 임시 백업은 Git에서 제외됩니다.
- PC 종료·절전 중에는 녹음되지 않습니다. 재실행 시 저장된 처리 작업을 복구합니다.
- 시간 링크는 전사 구간 기준이며 단어별 타임스탬프나 화자 분리는 지원하지 않습니다.
- 원문 링크와 요약은 AI가 생성하므로 내용과 근거를 직접 확인하세요.
- 현재 Windows 빌드는 코드 서명과 자동 업데이트를 제공하지 않습니다.
