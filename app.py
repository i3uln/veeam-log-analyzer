"""
Veeam 로그 분석기 - 웹 화면 (Streamlit)

로그 파일을 업로드하면 Claude가 분석한 리포트를 보여주고, .md 파일로 내려받을 수 있습니다.
분석 로직은 analyze.py의 함수를 그대로 재사용합니다.

실행:
    streamlit run app.py
"""

import datetime
import os

import anthropic
import streamlit as st

from analyze import DEFAULT_MODEL, MAX_CHARS, analyze, extract_relevant

st.set_page_config(page_title="Veeam 로그 분석기", page_icon="🛠️", layout="wide")
st.title("🛠️ Veeam 로그 분석기")
st.caption("Veeam 작업 로그를 올리면 Claude가 오류 원인과 조치 방법을 정리해 드립니다.")

# API 키가 없으면 분석을 막고 안내합니다. (키는 서버 환경 변수에서만 읽어요)
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("서버에 ANTHROPIC_API_KEY 환경 변수가 설정되지 않았어요. 관리자에게 문의하세요.")
    st.stop()

# 보안 안내: 고객 정보가 외부 API로 전송된다는 점을 사용자에게 분명히 알립니다.
st.warning(
    "업로드한 로그의 일부가 분석을 위해 외부 API(Anthropic)로 전송됩니다. "
    "고객사 정책상 외부 반출이 금지된 로그는 올리지 마세요."
)

# 옵션은 왼쪽 사이드바에 둡니다.
with st.sidebar:
    st.header("옵션")
    full = st.checkbox("오류 추리기 없이 전체 보내기", value=False,
                       help="기본은 오류·경고 주변만 보내서 비용을 줄이고 핵심에 집중해요.")
    model = st.text_input("모델", value=DEFAULT_MODEL)
    context_info = st.text_area(
        "환경 정보 (선택)",
        placeholder="예: VBR 12.3, vSphere 8.0, 리포지토리 Windows ReFS",
        help="버전과 환경을 알려주면 분석 정확도가 올라가요.",
    )

uploaded = st.file_uploader("Veeam 로그 파일 (.log, .txt)", type=["log", "txt"])

if uploaded is not None:
    # 업로드된 파일은 메모리에서만 처리하고 서버 디스크에 저장하지 않아요.
    text = uploaded.getvalue().decode("utf-8", errors="replace")
    body = text if full else extract_relevant(text)

    if not body:
        st.info("오류나 경고로 보이는 줄이 없어요. 전체를 보내려면 왼쪽 옵션을 켜세요.")
        st.stop()

    if len(body) > MAX_CHARS:
        body = "...(앞부분 생략)...\n" + body[-MAX_CHARS:]

    with st.expander(f"Claude에게 보낼 내용 미리보기 ({len(body):,}자)"):
        st.code(body, language="log")

    if st.button("분석하기", type="primary"):
        payload = body
        if context_info.strip():
            payload = f"[환경 정보]\n{context_info.strip()}\n\n{body}"

        with st.spinner("Claude가 로그를 분석하고 있어요..."):
            try:
                report = analyze(payload, uploaded.name, model)
            except anthropic.AuthenticationError:
                st.error("API 키 인증에 실패했어요. 관리자에게 문의하세요.")
                st.stop()
            except anthropic.APIStatusError as e:
                st.error(f"API 오류 ({e.status_code}): {e.message}")
                st.stop()
            except anthropic.APIConnectionError:
                st.error("Anthropic API에 연결하지 못했어요. 서버의 인터넷(프록시·방화벽) 설정을 확인하세요.")
                st.stop()

        if not report:
            st.error("리포트가 비어 있어요. 서버 콘솔의 stop_reason 메시지를 확인하세요.")
            st.stop()

        st.markdown(report)

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        base = os.path.splitext(uploaded.name)[0]
        st.download_button(
            "리포트 내려받기 (.md)",
            data=report.encode("utf-8"),
            file_name=f"report_{base}_{stamp}.md",
            mime="text/markdown",
        )
