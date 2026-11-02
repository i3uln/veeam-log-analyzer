# Veeam Log Analyzer

Veeam Backup & Replication 작업 로그에서 오류·경고 부분을 추려 Claude API로 보내고,
**원인과 조치 방법을 한국어 리포트로** 받아보는 도구입니다.

수백 MB짜리 로그를 직접 뒤지는 대신, 문제 구간만 골라 분석해서 장애 대응 시간을 줄이는 것이 목표입니다.

## 동작 방식

1. 로그 파일을 읽습니다.
2. `Error`, `Failed`, `Warning`, `Exception` 등이 들어간 줄과 앞뒤 3줄만 추립니다. (비용 절감 + 핵심 집중)
3. 너무 길면 끝부분(최근 기록)만 남깁니다.
4. Veeam 지원 엔지니어 역할의 시스템 프롬프트와 함께 Claude API(Messages API)를 호출합니다.
5. 요약 / 오류 표 / 추정 원인 / 조치 방법 / 추가 확인 사항 형식으로 결과를 출력합니다.

## 설치

```powershell
pip install -r requirements.txt
```

## API 키 설정

[Anthropic Console](https://console.anthropic.com)에서 API 키를 발급하고 환경 변수로 등록하세요.
**코드나 GitHub에 키를 직접 넣지 마세요.**

```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
```

`setx` 후에는 PowerShell 창을 새로 열어야 적용됩니다.

## 사용법

```powershell
# 예제 로그로 테스트
python analyze.py samples/sample_job.log

# 실제 Veeam 로그 (기본 위치: C:\ProgramData\Veeam\Backup\<작업 이름>\)
python analyze.py "C:\ProgramData\Veeam\Backup\Daily-VM-Backup\Job.Daily-VM-Backup.Backup.log"

# 오류 추출 없이 로그 끝부분을 그대로 분석
python analyze.py <로그 파일> --full
```

## 앞으로 할 일

- [ ] 여러 로그 파일(작업 로그 + 에이전트 로그)을 한 번에 분석
- [ ] 자주 보는 Veeam 오류 사례와 KB를 함께 넣어 정확도 높이기
- [ ] Veeam REST API를 MCP 서버로 연결해 "어젯밤 실패한 작업 알려줘" 같은 질문에 직접 조회해서 답하기
