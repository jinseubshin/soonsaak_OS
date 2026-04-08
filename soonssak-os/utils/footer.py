import streamlit as st


def show_legal_warning():
    st.divider()
    st.markdown(
        """
        <div style="
            background-color: #fff0f0;
            border: 2px solid #cc0000;
            border-radius: 8px;
            padding: 14px 18px;
            margin-top: 16px;
        ">
            <p style="color: #cc0000; font-weight: bold; font-size: 14px; margin: 0 0 6px 0; text-align: center;">
                ⛔ 법인폰 외 개인 소통 및 우회 거래 시 즉시 계약 해지 및 손해배상 청구 (계약서 제7조)
            </p>
            <p style="color: #880000; font-size: 12px; margin: 0; text-align: center;">
                📌 법인폰 로그는 회사의 자산이며 상시 모니터링 대상입니다 · 모든 소통은 기록됩니다 &nbsp;|&nbsp;
                💳 본사 공식 계좌 외 기사 직접 송금 시 서비스 보장 불가
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
