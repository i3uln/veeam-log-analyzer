"""
Veeam 로그 분석기 (1단계 기본 버전)

Veeam 작업 로그 파일을 읽어서, 오류와 경고가 있는 부분만 골라낸 뒤
Claude API에 보내 원인과 조치 방법을 한국어로 정리해 받는 스크립트입니다.

사용법:
    python analyze.py samples/sample_job.log
    python analyze.py C:\\ProgramData\\Veeam\\Backup\\MyJob\\Job.MyJob.Backup.log --full
"""

import argparse
import os
import re
import sys

import anthropic  # Anthropic 공식 Python SDK (pip install anthropic)

# 사용할 모델. 환경 변수 CLAUDE_MODEL로 바꿀 수 있어요.
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

# Claude에게 보낼 최대 글자 수. Veeam 로그는 수백 MB가 되기도 해서 잘라서 보냅니다.
MAX_CHARS = 150_000

# 오류로 판단할 키워드. Veeam 로그에서 자주 보이는 단어들이에요.
ERROR_PATTERN = re.compile(
    r"\b(Error|Failed|Failure|Warning|Exception|Timeout|Access is denied)\b",
    re.IGNORECASE,
)

# Claude에게 "어떤 역할로, 어떤 형식으로 답할지" 알려주는 시스템 프롬프트.
SYSTEM_PROMPT = """당신은 Veeam Backup & Replication 기술지원 엔지니어입니다.
사용자가 보낸 Veeam 로그를 분석해서 아래 형식으로 한국어로 답하세요.

## 요약
작업이 성공/경고/실패 중 무엇인지와 핵심 문제를 2~3문장으로.

## 발견된 오류
| 시각 | 메시지(요약) | 심각도 |
표로 정리하세요. 같은 오류가 반복되면 한 줄로 묶고 횟수를 적으세요.

## 추정 원인
가능성이 높은 순서대로. 로그에 근거가 있는 내용과 추측을 구분하세요.

## 조치 방법
우선순위 순서로 번호를 매기고, 확인 명령이나 설정 위치를 구체적으로 적으세요.

## 추가로 확인할 것
판단에 필요한데 이 로그에는 없는 정보(다른 로그 파일, 설정 등).

로그에 근거가 없는 내용을 사실처럼 단정하지 마세요."""


def read_log(path: str) -> str:
    """로그 파일을 읽습니다. 인코딩이 깨진 글자는 대체 문자로 바꿔서 읽어요."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_relevant(text: str, context: int = 3) -> str:
    """오류·경고가 있는 줄과 그 앞뒤 context 줄만 골라냅니다.

    로그 전체를 보내면 비용이 커지고 핵심이 묻히기 때문에,
    문제가 있는 부분 주변만 추려서 보냅니다.
    """
    lines = text.splitlines()
    keep = set()
    for i, line in enumerate(lines):
        if ERROR_PATTERN.search(line):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            keep.update(range(start, end))

    if not keep:
        return ""

    result = []
    prev = -1
    for i in sorted(keep):
        if i != prev + 1:
            result.append("...")  # 건너뛴 구간 표시
        result.append(lines[i])
        prev = i
    return "\n".join(result)


def analyze(log_text: str, filename: str, model: str) -> str:
    """Claude API를 호출해서 분석 결과를 받아옵니다."""
    # API 키는 환경 변수 ANTHROPIC_API_KEY에서 자동으로 읽어요.
    # 코드 안에 키를 직접 쓰지 마세요.
    client = anthropic.Anthropic()

    message = client.messages.create(
        model=model,
        max_tokens=8000,  # 응답 최대 길이. 너무 작으면 답변이 중간에 잘려요.
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"로그 파일 이름: {filename}\n\n<log>\n{log_text}\n</log>",
            }
        ],
    )
    # 응답이 왜 끝났는지(stop_reason)와 사용한 토큰 수를 보여줍니다. 문제 진단에 유용해요.
    #   end_turn   = 정상 종료
    #   max_tokens = 길이 한도에 걸려서 잘림
    print(
        f"[stop_reason={message.stop_reason}, "
        f"입력 토큰={message.usage.input_tokens}, 출력 토큰={message.usage.output_tokens}]"
    )
    if message.stop_reason == "max_tokens":
        print("경고: 응답이 길이 한도에 걸려 잘렸어요. max_tokens 값을 늘려보세요.")

    # 응답은 여러 블록으로 올 수 있어서, 텍스트 블록만 모아서 돌려줍니다.
    text = "".join(block.text for block in message.content if block.type == "text")
    if not text:
        types = [block.type for block in message.content]
        print(f"경고: 텍스트 응답이 없어요. 받은 블록 종류: {types}")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Veeam 로그를 Claude로 분석합니다.")
    parser.add_argument("logfile", help="분석할 Veeam 로그 파일 경로")
    parser.add_argument(
        "--full",
        action="store_true",
        help="오류 주변만 추리지 않고 로그 끝부분을 그대로 보냅니다.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="사용할 Claude 모델")
    parser.add_argument("--out", help="리포트를 저장할 파일 경로 (예: reports\\case1.md)")
    args = parser.parse_args()

    if not os.path.isfile(args.logfile):
        sys.exit(f"파일을 찾을 수 없어요: {args.logfile}")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY 환경 변수가 없어요.\n"
            "setx로 등록했다면 PowerShell 창을 새로 열거나, 지금 창에서 아래를 실행하세요:\n"
            '$env:ANTHROPIC_API_KEY = [Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY","User")'
        )

    text = read_log(args.logfile)

    if args.full:
        body = text
    else:
        body = extract_relevant(text)
        if not body:
            print("오류나 경고로 보이는 줄이 없어요. 전체를 보려면 --full 옵션을 쓰세요.")
            return

    # 너무 길면 끝부분만 보냅니다. 장애 원인은 보통 로그 마지막 쪽에 있어요.
    if len(body) > MAX_CHARS:
        body = "...(앞부분 생략)...\n" + body[-MAX_CHARS:]

    print(f"분석 중... (보내는 분량: {len(body):,}자, 모델: {args.model})\n")

    try:
        result = analyze(body, os.path.basename(args.logfile), args.model)
    except anthropic.AuthenticationError:
        sys.exit("API 키가 올바르지 않아요. ANTHROPIC_API_KEY 환경 변수를 확인하세요.")
    except anthropic.APIStatusError as e:
        sys.exit(f"API 오류 ({e.status_code}): {e.message}\n크레딧 잔액이 부족한 경우에도 이 오류가 나요.")
    except anthropic.APIConnectionError:
        sys.exit("Anthropic API에 연결하지 못했어요. 인터넷 연결을 확인하세요.")

    if args.out:
        # 리포트를 UTF-8 파일로 저장합니다. 폴더가 없으면 만들어요.
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"리포트를 저장했어요: {args.out}")
    else:
        print(result)


if __name__ == "__main__":
    main()
