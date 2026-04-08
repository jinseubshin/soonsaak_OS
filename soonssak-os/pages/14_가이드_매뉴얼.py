"""
순삭 OS — 역할별 가이드/매뉴얼
- 로그인 역할에 맞는 가이드 자동 노출
- 작업 단계별 체크리스트 + 도움말
- 관리자 직통 텔레그램 문의
- 시니어 배려 UI (큰 폰트·버튼)
"""
import streamlit as st
import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import get_settings
from utils.rbac import (
    render_role_selector, is_owner, is_manager, is_executor, is_cs,
    current_role, role_badge, ROLES,
)

st.set_page_config(
    page_title="가이드/매뉴얼 — 순삭 OS",
    page_icon="📖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

render_role_selector()

# ── 시니어 배려 전역 CSS ─────────────────────────────────────────
st.markdown(
    """
<style>
/* 시니어 배려 UI: 큰 폰트 + 큰 버튼 */
html, body, [class*="css"] {
    font-size: 17px !important;
}
.stButton > button {
    font-size: 18px !important;
    padding: 14px 24px !important;
    border-radius: 12px !important;
    min-height: 54px !important;
    font-weight: 700 !important;
}
.stMarkdown h4 { font-size: 20px !important; }
.stMarkdown h3 { font-size: 24px !important; }
.stMarkdown h2 { font-size: 28px !important; }
.stCheckbox label { font-size: 17px !important; }
.stExpander summary { font-size: 17px !important; }
/* 도움말 카드 */
.help-card {
    background: #f0f7ff;
    border-left: 5px solid #1976d2;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
    font-size: 16px;
}
/* 긴급 연락 버튼 */
.emergency-btn {
    background: linear-gradient(135deg,#d32f2f,#b71c1c);
    color: white !important;
    border-radius: 14px !important;
    padding: 16px 28px !important;
    font-size: 20px !important;
    font-weight: 800 !important;
    display: block;
    text-align: center;
    margin: 16px 0;
    text-decoration: none;
}
</style>
""",
    unsafe_allow_html=True,
)

settings = get_settings()
_role = current_role()

# ── 페이지 헤더 ─────────────────────────────────────────────────
_role_info = ROLES.get(_role, {})
st.markdown(
    f"""
<div style="background:linear-gradient(135deg,#1a237e 0%,#283593 100%);
     color:white;border-radius:14px;padding:20px 24px;margin-bottom:16px">
<h2 style="margin:0;color:#ffffff">📖 순삭 OS 가이드 / 매뉴얼</h2>
<p style="margin:6px 0 0 0;font-size:18px;color:#c5cae9">
{_role_info.get('label','—')} 맞춤 가이드가 표시됩니다
</p>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")

# ════════════════════════════════════════════════════════════════════
#  역할별 가이드 라우팅
# ════════════════════════════════════════════════════════════════════

# ──────────────────────── EXECUTOR (기사) 가이드 ──────────────────
if is_executor():
    st.markdown("## 🚗 기사 업무 가이드")
    st.caption("모든 단계를 순서대로 진행하세요. 도움말(?) 버튼을 클릭하면 자세한 안내가 나옵니다.")

    # ─── 1단계: 출발 전 준비
    st.markdown("---")
    st.markdown("### 1️⃣ 출발 전 준비")
    _c1_col1, _c1_col2 = st.columns([4, 1])
    with _c1_col1:
        st.markdown(
            """
<div class="help-card">
📍 <b>현장 출발 전 반드시 확인하세요</b><br>
• 배차된 주문의 주소·시간을 확인합니다<br>
• 기사 앱 → 내 주문 탭에서 고객명·픽업주소 확인<br>
• 출발 전 고객에게 전화 또는 문자 발송 필수
</div>
""",
            unsafe_allow_html=True,
        )
    with _c1_col2:
        with st.expander("❓"):
            st.markdown(
                "**출발 전 체크리스트:**\n"
                "- [ ] 주문 번호 확인\n"
                "- [ ] 고객 주소 네비 입력\n"
                "- [ ] 고객에게 도착 예정 문자 발송\n"
                "- [ ] 차량 상태(연료/청결) 점검"
            )

    # ─── 2단계: GPS/위치 확인
    st.markdown("### 2️⃣ GPS 위치 확인 및 도착 보고")
    _c2_col1, _c2_col2 = st.columns([4, 1])
    with _c2_col1:
        st.markdown(
            """
<div class="help-card">
🗺️ <b>기사 앱 → 내 주문 탭 → [도착 완료 보고] 버튼</b><br>
• 현장 도착 즉시 앱에서 도착 보고를 누르세요<br>
• GPS가 자동으로 현재 위치를 기록합니다<br>
• 도착 보고 후 <b>반드시 작업 전 사진</b>을 촬영하세요
</div>
""",
            unsafe_allow_html=True,
        )
    with _c2_col2:
        with st.expander("❓"):
            st.markdown(
                "**사진 촬영 위치 안내:**\n\n"
                "📸 **작업 전 사진**\n"
                "- 폐기물 전체가 보이는 각도\n"
                "- 주소판이 함께 나오면 베스트\n\n"
                "📐 촬영 방향: 정면 + 측면 2컷 이상"
            )

    # ─── 3단계: 작업 전 사진
    st.markdown("### 3️⃣ 작업 전 사진 업로드 (필수)")
    _c3_col1, _c3_col2 = st.columns([4, 1])
    with _c3_col1:
        st.markdown(
            """
<div class="help-card">
📸 <b>작업 시작 전 반드시 사진을 올려야 합니다</b><br>
• 기사 앱 → 내 주문 → [작업 전 사진 업로드]<br>
• 사진 미업로드 시 → <span style="color:red">다음 배차에서 자동 제외</span><br>
• <b>잘 찍은 예시 사진</b>은 아래 도움말을 클릭하세요
</div>
""",
            unsafe_allow_html=True,
        )
    with _c3_col2:
        with st.expander("❓ 예시"):
            st.markdown("**✅ 잘 찍은 사진 기준:**")
            st.markdown(
                "- 폐기물 전체가 한 화면에\n"
                "- 밝은 조도 (플래시 사용)\n"
                "- 건물 외관/번지가 보임\n\n"
                "**❌ 불합격 사진:**\n"
                "- 너무 가까이 찍어 전체 안 보임\n"
                "- 어두워서 식별 불가\n"
                "- 사진 흔들림"
            )
            st.info("사진이 기준 미달이면 AI가 자동 감지합니다.")

    # ─── 4단계: 작업 완료 사진
    st.markdown("### 4️⃣ 작업 완료 후 사진 업로드 (필수)")
    _c4_col1, _c4_col2 = st.columns([4, 1])
    with _c4_col1:
        st.markdown(
            """
<div class="help-card">
✅ <b>작업 완료 후 빈 자리 사진을 올려야 정산이 확정됩니다</b><br>
• 기사 앱 → 내 주문 → [작업 완료 사진 업로드]<br>
• 완전히 비워진 공간 + 주변 청결 상태 촬영<br>
• 업로드 후 [작업 완료 처리] 버튼을 눌러주세요
</div>
""",
            unsafe_allow_html=True,
        )
    with _c4_col2:
        with st.expander("❓ 예시"):
            st.markdown(
                "**완료 사진 체크:**\n"
                "- 폐기물이 완전히 제거된 빈 공간\n"
                "- 바닥/벽 청결 확인\n"
                "- 동일 각도로 Before/After 비교 가능하게"
            )

    # ─── 5단계: 정산 확인
    st.markdown("### 5️⃣ 정산 확인")
    _c5_col1, _c5_col2 = st.columns([4, 1])
    with _c5_col1:
        st.markdown(
            """
<div class="help-card">
💰 <b>정산은 월말 일괄 지급됩니다</b><br>
• 기사 앱 → 정산 탭에서 이달 예상 수당 확인 가능<br>
• 직영 기사: 월 40건 이상 시 운영비 전액 지급<br>
• 40건 미달 시 50% 지급 (운영비 차감 주의)
</div>
""",
            unsafe_allow_html=True,
        )
    with _c5_col2:
        with st.expander("❓"):
            st.markdown(
                "**정산 계산 방법:**\n"
                "- 개인(3.3%): 지급액 × 0.967 = 실수령\n"
                "- 사업자: 공급가 + 부가세 분리\n\n"
                "궁금한 점은 아래 관리자 문의 버튼을 이용하세요."
            )

# ──────────────────────── MANAGER 가이드 ─────────────────────────
elif is_manager() and not is_owner():
    st.markdown("## 👔 매니저 업무 가이드")
    st.caption("철거 현장 견적 입력 및 사진 촬영 중심 가이드입니다.")

    st.markdown("---")
    st.markdown("### 1️⃣ 현장 방문 전 준비")
    _mc1, _mc2 = st.columns([4, 1])
    with _mc1:
        st.markdown(
            """
<div class="help-card">
📋 <b>배차 스케줄링 → 매니저 모니터링 탭</b>에서 담당 철거 건을 확인하세요<br>
• 주문 상세에서 CS 기초 견적·철거 범위·층수·엘리베이터 여부 확인<br>
• 고객 연락처는 CS 상담원에게 전달받거나 기사 앱에서 확인
</div>
""",
            unsafe_allow_html=True,
        )
    with _mc2:
        with st.expander("❓"):
            st.markdown(
                "**현장 방문 전 체크:**\n"
                "- [ ] 철거 범위/면적 파악\n"
                "- [ ] 석면 여부 사전 문의\n"
                "- [ ] 팀 규모 (1인/2인 1조) 결정\n"
                "- [ ] 견적서 양식 준비"
            )

    st.markdown("### 2️⃣ 현장 사진 촬영 (3장 이상 필수)")
    _mc3, _mc4 = st.columns([4, 1])
    with _mc3:
        st.markdown(
            """
<div class="help-card">
📸 <b>현장 사진 3장 이상 업로드 후에만 [견적 확정] 버튼이 활성화됩니다</b><br>
• 배차 스케줄링 → 해당 주문 → 현장 견적 사진 업로드<br>
• 사진 부족 시 견적 확정 버튼이 잠깁니다(🔒)<br>
• 촬영 방향: <b>정면 / 측면 / 폐기물 상세</b>
</div>
""",
            unsafe_allow_html=True,
        )
    with _mc4:
        with st.expander("❓ 사진 가이드"):
            st.markdown(
                "**매니저 현장 사진 기준 3장:**\n\n"
                "**사진 1** — 건물 전경 (주소 확인 가능)\n\n"
                "**사진 2** — 철거 대상 전체 구조물\n\n"
                "**사진 3** — 폐기물/해체 상세 (석면·위험물 포함 여부)\n\n"
                "> AI가 견적 사진과 완료 사진을 자동 비교합니다. 정확하게 촬영해야 페널티가 없습니다."
            )

    st.markdown("### 3️⃣ 견적 금액 확정 및 발송")
    _mc5, _mc6 = st.columns([4, 1])
    with _mc5:
        st.markdown(
            """
<div class="help-card">
💰 <b>사진 3장 업로드 완료 후 견적 금액 입력 → [견적 확정 & 발송] 클릭</b><br>
• CS 기초 견적 대비 ±10% 범위 내 조정 권장<br>
• 확정 즉시 고객에게 알림톡 자동 발송<br>
• 확정 후 배차 가능 → 기사 배정으로 이어짐
</div>
""",
            unsafe_allow_html=True,
        )
    with _mc6:
        with st.expander("❓"):
            st.markdown(
                "**견적 초과 주의:**\n"
                "- CS 기초 견적 대비 10% 초과 시\n"
                "  → 대표에게 자동 알림 발송됨\n\n"
                "**견적 범위:**\n"
                "- 소형: ₩50,000 ~ ₩150,000\n"
                "- 대형: ₩150,000 ~ ₩500,000\n"
                "- 특수(석면): 별도 견적"
            )

    st.markdown("### 4️⃣ 기사 배치 및 완료 확인")
    st.markdown(
        """
<div class="help-card">
🚗 <b>견적 확정 → 배차 스케줄링 탭에서 기사 선택 → 배차 확정</b><br>
• 철거 전용 기사는 우선순위 상단에 자동 정렬됩니다<br>
• 2인 1조 필요 시 보조 기사도 함께 선택하세요<br>
• 작업 완료 후 고객 만족도 설문 자동 발송됩니다
</div>
""",
        unsafe_allow_html=True,
    )

# ──────────────────────── OWNER 가이드 ────────────────────────────
elif is_owner():
    st.markdown("## 👑 Owner(대표) 관리 가이드")
    st.caption("시스템 전체 관리 및 모니터링 중심 가이드입니다.")

    tab_sys, tab_alarm, tab_settle = st.tabs(["⚙️ 시스템 관리", "🔔 알림 모니터링", "💰 정산 관리"])
    with tab_sys:
        st.markdown(
            """
<div class="help-card">
<b>핵심 설정 위치:</b><br>
• <b>설정 페이지</b> → 정산 비율, 운영비 기준, 텔레그램 알림 설정<br>
• <b>지역 관리</b> → 세종/본사 ROI 추적 및 마케팅 채널별 성과 분석<br>
• <b>메인 대시보드</b> → 지역 스위칭 셀렉터(전체/본사/세종) + Owner 전용 알림창
</div>
""",
            unsafe_allow_html=True,
        )
    with tab_alarm:
        st.markdown(
            """
<div class="help-card">
<b>자동 알림 채널:</b><br>
• <b>카카오 알림톡</b> → 이상 징후(사진 불일치·정산 초과·미등록 번호)<br>
• <b>텔레그램 봇</b> → 모든 알림 동시 발송 + OS 딥링크 자동 첨부<br>
• <b>메인 대시보드</b> → Owner 전용 알림창(AI 불일치 + 자동 페널티)
</div>
""",
            unsafe_allow_html=True,
        )
    with tab_settle:
        st.markdown(
            """
<div class="help-card">
<b>정산 확인 흐름:</b><br>
• 정산 엔진 → 개별 기사 건당 수당 계산<br>
• 세무 페이지 → 원천세(3.3%) / 부가세 분리 발행<br>
• 월간 정산 명세서 → PDF 다운로드 가능
</div>
""",
            unsafe_allow_html=True,
        )

# ──────────────────────── CS 가이드 ───────────────────────────────
elif is_cs():
    st.markdown("## 🎧 CS 상담원 가이드")
    st.caption("고객 상담 및 주문 등록 중심 가이드입니다.")

    st.markdown("### 1️⃣ 고객 상담 주문 등록")
    st.markdown(
        """
<div class="help-card">
📞 <b>CS 상담센터 페이지에서 주문을 등록합니다</b><br>
• 고객명 / 연락처 / 픽업 주소 / 예약 시간 / 작업 유형(수거/철거) 입력<br>
• 철거 건: 범위·면적·층수·석면 여부 추가 입력 필수<br>
• 지역 선택 (본사/세종) + 마케팅 유입 경로 반드시 선택
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("### 2️⃣ 고객 응대 스크립트")
    with st.expander("📋 상담 스크립트 전체 보기", expanded=False):
        st.markdown(
            "**인바운드 첫 인사:**\n"
            "> '안녕하세요, 순삭입니다. 무엇을 도와드릴까요?'\n\n"
            "**견적 안내:**\n"
            "> '수거는 ₩20,000~₩80,000, 철거는 현장 방문 후 정확한 견적을 드립니다.'\n\n"
            "**예약 확인:**\n"
            "> '예약 완료되었습니다. 담당 기사님이 방문 전 연락드릴 예정입니다.'\n\n"
            "**불만 고객:**\n"
            "> '불편을 드려 정말 죄송합니다. 즉시 담당 매니저에게 연결해 드리겠습니다.'"
        )

st.markdown("---")

# ════════════════════════════════════════════════════════════════════
#  공통: 작업 단계별 체크리스트 (세션 유지)
# ════════════════════════════════════════════════════════════════════
st.markdown("## ✅ 오늘의 업무 체크리스트")
st.caption("완료한 항목을 체크하세요. 새로고침 시 초기화됩니다.")

if is_executor():
    _items = [
        "출발 전 고객 도착 예정 문자 발송",
        "현장 도착 후 도착 보고 완료",
        "작업 전 사진 업로드 (정면+측면)",
        "작업 완료 사진 업로드 (빈 공간)",
        "작업 완료 처리 버튼 클릭",
        "고객 만족 확인 후 퇴장",
    ]
elif is_manager() and not is_owner():
    _items = [
        "담당 철거 건 주문 상세 확인",
        "고객 방문 예약 및 주소 확인",
        "현장 사진 1장: 건물 전경 촬영",
        "현장 사진 2장: 철거 대상 구조물",
        "현장 사진 3장: 폐기물/석면 상세",
        "견적 금액 입력 후 [견적 확정] 클릭",
        "담당 기사 배차 완료 확인",
    ]
elif is_cs():
    _items = [
        "고객 주문 정보 정확히 입력",
        "지역 및 마케팅 유입경로 선택",
        "철거 건 — 추가 현장 정보 입력",
        "예약 확인 문자 고객에게 발송 확인",
        "이상 주문 플래그 확인",
    ]
else:  # owner
    _items = [
        "메인 대시보드 — Owner 전용 알림창 확인",
        "AI 사진 불일치 건 처리",
        "자동 페널티 내역 검토",
        "이달 정산 명세서 확인",
        "텔레그램 알림 정상 수신 여부 확인",
    ]

for _idx, _item in enumerate(_items):
    st.checkbox(_item, key=f"checklist_{_role}_{_idx}")

st.markdown("---")

# ════════════════════════════════════════════════════════════════════
#  긴급 고객센터 — 관리자에게 직통 문의 (텔레그램)
# ════════════════════════════════════════════════════════════════════
st.markdown("## 🆘 관리자 직통 문의")
st.markdown(
    """
<div style="background:#fff3e0;border-left:5px solid #ff6f00;border-radius:10px;
     padding:16px 20px;margin-bottom:16px;font-size:17px">
업무 중 도움이 필요하거나 긴급 상황이 발생하면 아래 버튼을 눌러주세요.<br>
관리자에게 <b>텔레그램으로 즉시 알림</b>이 전송됩니다.
</div>
""",
    unsafe_allow_html=True,
)

_msg_input = st.text_area(
    "📝 문의 내용 (선택 사항)",
    placeholder="예: 주문 #5번 현장에서 예상 외 석면이 발견됐습니다. 어떻게 처리하나요?",
    height=100,
    key="contact_admin_msg",
)

_c_col1, _c_col2 = st.columns([1, 3])
with _c_col1:
    if st.button("📨 관리자에게 문의", type="primary", key="contact_admin_btn"):
        _now = datetime.now().strftime("%Y-%m-%d %H:%M")
        _role_label = ROLES.get(_role, {}).get("label", _role)
        _tg_msg = (
            f"[순삭OS 직통 문의] 📨\n\n"
            f"■ 발신: {_role_label}\n"
            f"■ 시각: {_now}\n"
            f"■ 내용: {_msg_input or '(내용 없음)'}\n\n"
            f"⚡ 빠른 답변 부탁드립니다."
        )
        try:
            from utils.notifications import _send_telegram
            result = _send_telegram(_tg_msg, order_id=None)
            if result.get("success"):
                st.success("✅ 문의가 관리자에게 전송되었습니다! 빠른 시간 내에 연락드립니다.")
            else:
                err = result.get("error", "알 수 없는 오류")
                st.warning(f"⚠️ 텔레그램 전송 실패: {err}")
                _tg_set = settings.get("telegram_bot_token", "")
                if not _tg_set:
                    st.info("ℹ️ 관리자가 텔레그램 봇을 아직 설정하지 않았습니다. 직접 전화로 연락해 주세요.")
        except Exception as _e:
            st.error(f"전송 오류: {_e}")

with _c_col2:
    _admin_phone = settings.get("owner_phone", "")
    if _admin_phone:
        st.markdown(
            f"""
<div style="background:#e8f5e9;border-radius:10px;padding:12px 16px;font-size:17px">
📞 <b>긴급 전화:</b> <a href="tel:{_admin_phone}" style="font-size:20px;font-weight:bold;color:#1b5e20">{_admin_phone}</a>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.info("ℹ️ 긴급 전화번호는 설정 → 카카오 알림 설정에서 등록하세요.")

st.markdown("---")
st.caption("순삭 OS 가이드/매뉴얼 | 역할 변경 시 해당 역할에 맞는 가이드가 자동으로 표시됩니다.")

from utils.footer import show_legal_warning
show_legal_warning()
