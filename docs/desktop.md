# Windows 설치 및 환경변수

ZIP을 모두 압축 해제하고 `install.cmd`를 실행합니다. 설치 후 바탕화면의 Sorinote를 실행합니다. Microsoft Edge WebView2 Runtime이 필요합니다.

| 항목 | 기본 경로 |
|---|---|
| 프로그램 | `%LOCALAPPDATA%\Programs\Sorinote` |
| API 키 | `%LOCALAPPDATA%\Sorinote\.env.local` |
| 회의록 | `%LOCALAPPDATA%\Sorinote\data` |
| 로그 | `%LOCALAPPDATA%\Sorinote\desktop.log` |

앱 설정에서 필요한 API 키를 입력합니다. `.env.example`에는 지원하는 환경변수 이름만 들어 있습니다. 키 파일은 일반 텍스트이므로 공개 저장소에 추가하지 마세요. API 서비스 설정은 [별도 안내](api-providers.md)를 참고하세요.

업데이트할 때 앱을 닫고 같은 설치 스크립트를 실행합니다. 기존 키와 회의록은 유지됩니다.

기존 개발 폴더를 사용하려면 다음과 같이 설치합니다.

```powershell
.\install.ps1 -ExistingHome "C:\path\to\sorinote"
```

업데이트할 때도 같은 인수를 사용합니다. 같은 데이터 폴더에 개발 서버와 설치 앱을 동시에 실행할 수 없습니다.

고급 설정은 `SORINOTE_HOME`, `SORINOTE_ENV_FILE`, `SORINOTE_DATA_DIR` 환경변수를 사용합니다. 설치 앱의 기본 포트는 18767, 개발 서버는 18765이며 로컬 컴퓨터에서만 연결됩니다. 녹음을 종료한 뒤 창을 닫으세요. 미완료 작업은 다음 실행 때 복구합니다.

## 요약과 원문 연결

요약 링크에 마우스를 올리면 원문 일부를 보고, 클릭하면 해당 구간 전체를 볼 수 있습니다. 기존 회의록의 **원문 연결 요약 만들기**는 현재 선택한 요약 모델로 다시 생성하며 API 비용이 발생합니다. 이전 요약은 회의록 폴더에 백업됩니다.

## 검증

`Sorinote.exe --self-test`는 실제 키나 회의 자료 없이 회귀 테스트를 실행하며 사용자 데이터 폴더의 상위에 `verification.json`을 만듭니다.

`Sorinote.exe --soak-seconds 14400`은 실제 시스템 오디오의 4시간 캡처 시험입니다. 테스트 중 다른 소리노트 녹음을 종료하세요. 이 시험은 API에 오디오를 보내지 않습니다. 장치 변경은 Windows에서 직접 수행해야 합니다.

기본 회귀 테스트의 4시간 큐·네트워크 장애·장치 전환 검증은 모의 테스트이며 실환경 장시간 녹음 검증과 다릅니다. Notion 전송도 기본 테스트에서는 모의합니다.

현재 빌드는 코드 서명, 자동 업데이트 및 일반 설치 마법사를 포함하지 않습니다.
