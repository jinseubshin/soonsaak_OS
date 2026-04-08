import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import get_settings, save_settings
from utils.footer import show_legal_warning
from utils.rbac import (render_role_selector, is_owner, is_manager, is_manager_only,
                         is_executor, is_cs, role_badge)

st.set_page_config(page_title="설정 — 순삭 OS", page_icon="⚙️", layout="wide")
st.title("⚙️ 시스템 설정")

render_role_selector()
st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")

# 설정은 Owner(대표) 전용. Manager는 읽기만 가능.
if is_cs() or is_executor():
    st.error(
        "🚫 **접근 권한 없음** — 시스템 설정은 대표(Owner) / 매니저 전용입니다.\n\n"
        "CS 상담원·기사 모드에서는 설정 변경이 불가합니다."
    )
    st.stop()

if is_manager_only():
    st.warning(
        "👔 **매니저 모드** — 설정 내용은 읽기 전용으로 표시됩니다. "
        "항목 변경은 대표(Owner)에게 요청하세요."
    )

_read_only = is_manager_only()

settings = get_settings()

st.subheader("💰 정산 비율 설정")
col1, col2, col3, col4 = st.columns(4)
with col1:
    driver_ratio = st.number_input(
        "기사 수수료 비율 (%)", min_value=0.0, max_value=100.0,
        value=settings["driver_ratio"] * 100, step=0.5,
    ) / 100
with col2:
    cs_ratio = st.number_input(
        "CS 비율 (%)", min_value=0.0, max_value=100.0,
        value=settings["cs_ratio"] * 100, step=0.5,
    ) / 100
with col3:
    success_fee_ratio = st.number_input(
        "성공보수 비율 (%)", min_value=0.0, max_value=100.0,
        value=settings["success_fee_ratio"] * 100, step=0.5,
    ) / 100
with col4:
    dispatch_fee = st.number_input(
        "출동비 (원)", min_value=0, value=settings["dispatch_fee"], step=5000,
    )

st.divider()

st.subheader("🤖 무인 자동 페널티 설정")
st.caption("지연 자동 감지 및 페널티 금액을 설정합니다. 기사 앱 로딩 시마다 자동 점검됩니다.")
ap_col1, ap_col2 = st.columns(2)
with ap_col1:
    delay_threshold_min = st.number_input(
        "지연 감지 기준 (분)", min_value=10, max_value=120,
        value=settings.get("delay_threshold_min", 30), step=5,
        help="예약 시간 초과 후 이 시간(분)이 지나면 자동 지연 페널티 적용",
        disabled=_read_only,
    )
with ap_col2:
    auto_penalty_amount = st.number_input(
        "자동 페널티 금액 (원)", min_value=0,
        value=settings.get("auto_penalty_amount", 20000), step=5000,
        help="지연 감지 시 자동 차감되는 페널티 금액",
        disabled=_read_only,
    )

st.divider()

st.subheader("👔 매니저(이사급) 정산 설정")
m_col1, m_col2, m_col3, m_col4 = st.columns(4)
with m_col1:
    manager_base_cost = st.number_input(
        "매니저 기본 운영비 (원/월)", min_value=0,
        value=settings.get("manager_base_cost", 1500000), step=100000,
        help="계약상 월 고정 운영비"
    )
with m_col2:
    demolition_incentive_min = st.number_input(
        "철거 인센티브 최소 (원/건)", min_value=0,
        value=settings.get("demolition_incentive_min", 50000), step=5000,
    )
with m_col3:
    demolition_incentive_max = st.number_input(
        "철거 인센티브 최대 (원/건)", min_value=0,
        value=settings.get("demolition_incentive_max", 100000), step=5000,
    )
with m_col4:
    active_driver_threshold = st.number_input(
        "활성 기사 기준 (건/월)", min_value=1,
        value=settings.get("active_driver_threshold", 60), step=1,
        help="월 N건 이상 수행 시 활성 기사로 분류"
    )

st.info(f"📌 실행자 유지 보충 보너스: 활성 기사 2명 → **₩100,000** | 3명 이상 → **₩200,000**")

st.divider()

st.subheader("🚗 직영팀(기사) 운영비 설정")
d_col1, d_col2, d_col3 = st.columns(3)
with d_col1:
    direct_team_threshold = st.number_input(
        "전액 지급 기준 (건/월)", min_value=1,
        value=settings.get("direct_team_threshold", 40), step=1,
        help="이 건수 이상 시 운영비 전액 지급"
    )
with d_col2:
    direct_team_full_cost = st.number_input(
        "조건부 운영비 전액 (원)", min_value=0,
        value=settings.get("direct_team_full_cost", 1500000), step=100000,
        help=f"월 기준 건수 이상 시 전액 지급"
    )
with d_col3:
    direct_team_half_cost = st.number_input(
        "조건부 운영비 50% (원)", min_value=0,
        value=settings.get("direct_team_half_cost", 750000), step=50000,
        help="월 기준 건수 미달 시 50% 지급"
    )

st.info(
    f"📌 건당 수당 범위 — **수거:** ₩20,000~₩40,000 / **철거:** ₩50,000~₩200,000\n\n"
    f"지연 발생 시 해당 건 수당 차감 | 임의 추가요금 적발 시 수당 0원 + 3배 배상 경고"
)

st.divider()

# ──────────────── 수거 전용 건당 단가표 설정 ────────────────
st.subheader("📦 수거 전용 기사 건당 단가표")
st.caption(
    "수거 전용(specialty=수거) 기사의 품목 유형별 건당 지급 단가를 설정합니다. "
    "정산 엔진에서 해당 기사의 수거 작업에 이 단가가 기준으로 적용됩니다."
)

_coll_rates = settings.get("collection_allowance_rates", {})
_coll_items_default = [
    {"label": "소형 수거 (1인 가구 소파/의자 등)", "key": "small", "default_min": 20000, "default_max": 30000},
    {"label": "중형 수거 (장롱/냉장고/세탁기 등)", "key": "medium", "default_min": 30000, "default_max": 40000},
    {"label": "대형 수거 (침대/피아노/에어컨 등)", "key": "large",  "default_min": 35000, "default_max": 50000},
    {"label": "다량/잡화 수거 (이사짐/소량 철거 후처리 등)", "key": "bulk", "default_min": 50000, "default_max": 80000},
]

_new_coll_rates = {}
with st.expander("📋 품목별 단가 설정", expanded=True):
    for _item in _coll_items_default:
        _item_key = _item["key"]
        _saved = _coll_rates.get(_item_key, {"min": _item["default_min"], "max": _item["default_max"]})
        _c1, _c2, _c3 = st.columns([3, 1, 1])
        with _c1:
            st.markdown(f"**{_item['label']}**")
        with _c2:
            _min_val = st.number_input(
                "최소 (원)", min_value=0,
                value=int(_saved.get("min", _item["default_min"])), step=1000,
                key=f"coll_min_{_item_key}",
                label_visibility="collapsed" if not _read_only else "visible",
                disabled=_read_only,
            )
        with _c3:
            _max_val = st.number_input(
                "최대 (원)", min_value=0,
                value=int(_saved.get("max", _item["default_max"])), step=1000,
                key=f"coll_max_{_item_key}",
                label_visibility="collapsed" if not _read_only else "visible",
                disabled=_read_only,
            )
        _new_coll_rates[_item_key] = {"min": _min_val, "max": _max_val}

    if not _read_only:
        if st.button("💾 수거 단가표 저장", key="save_coll_rates"):
            _s = get_settings()
            _s["collection_allowance_rates"] = _new_coll_rates
            save_settings(_s)
            st.success("✅ 수거 전용 단가표 저장 완료")
            st.rerun()

st.divider()

st.subheader("🧾 세무 설정")
withholding_rate = st.number_input(
    "원천징수율 (%)", min_value=0.0, max_value=100.0,
    value=settings["withholding_tax_rate"] * 100, step=0.1,
    help="개인사업자 3.3% (소득세 3% + 지방소득세 0.3%)",
) / 100

st.divider()

# ──────────────── 매니저 등록 및 지역 관리 ────────────────
st.subheader("🗺️ 지역 및 매니저 등록")
st.info(
    "각 매니저별로 담당 지역과 고유 법인폰 번호를 등록합니다. "
    "법인폰 번호는 통화 로그 업로드 시 지역 자동 매칭에 활용됩니다."
)

managers_list = settings.get("managers", [])
regions_list = settings.get("regions", ["본사", "세종"])

# 지역 목록 편집
col_r1, col_r2 = st.columns([3, 1])
with col_r1:
    new_regions_str = st.text_input(
        "담당 지역 목록 (쉼표 구분)",
        value=", ".join(regions_list),
        help="예: 본사, 세종, 대전"
    )
with col_r2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("지역 저장"):
        new_regions = [r.strip() for r in new_regions_str.split(",") if r.strip()]
        cur = get_settings()
        cur["regions"] = new_regions
        save_settings(cur)
        st.success("지역 목록 저장됨")
        st.rerun()

st.markdown("**등록된 매니저 목록**")
if managers_list:
    mgr_rows = []
    for m in managers_list:
        mgr_rows.append({
            "ID": m["id"],
            "이름": m["name"],
            "담당 지역": m["region"],
            "법인폰": m.get("corporate_phone", "—"),
            "역할": m.get("role", "매니저"),
        })
    import pandas as _pd
    st.dataframe(_pd.DataFrame(mgr_rows), use_container_width=True, hide_index=True)
else:
    st.info("등록된 매니저가 없습니다.")

with st.expander("➕ 매니저 신규 등록"):
    with st.form("add_manager_form"):
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            m_name = st.text_input("이름 *", placeholder="이세종")
            m_role = st.selectbox("역할", ["대표", "지역매니저", "팀장"])
        with mc2:
            m_region = st.selectbox("담당 지역 *", regions_list)
            m_phone = st.text_input("법인폰 번호 *", placeholder="010-0000-0000")
        with mc3:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption("법인폰 번호는 통화 로그 업로드 시 지역 자동 매칭에 사용됩니다.")
        if st.form_submit_button("매니저 등록", type="primary"):
            if not m_name or not m_phone:
                st.error("이름과 법인폰 번호를 입력하세요.")
            else:
                cur = get_settings()
                existing = cur.get("managers", [])
                new_id = max([m["id"] for m in existing], default=0) + 1
                existing.append({
                    "id": new_id,
                    "name": m_name,
                    "region": m_region,
                    "corporate_phone": m_phone,
                    "role": m_role,
                })
                cur["managers"] = existing
                save_settings(cur)
                st.success(f"✅ {m_name} 매니저 등록 완료! (지역: {m_region}, 법인폰: {m_phone})")
                st.rerun()

with st.expander("🗑️ 매니저 삭제"):
    if managers_list:
        del_opts = {f"{m['name']} ({m['region']})": m["id"] for m in managers_list}
        del_target = st.selectbox("삭제할 매니저", list(del_opts.keys()))
        if st.button("삭제 확정", type="secondary"):
            del_id = del_opts[del_target]
            cur = get_settings()
            cur["managers"] = [m for m in cur.get("managers", []) if m["id"] != del_id]
            save_settings(cur)
            st.success("삭제 완료")
            st.rerun()

st.divider()

# ──────────────── 지역별 정산 명칭 커스텀 ────────────────
st.subheader("🏷️ 지역별 정산 항목 명칭 커스텀")
st.caption(
    "각 지역의 정산 화면에서 사용할 명칭을 설정합니다. "
    "예: 세종 지역의 '운영비' 항목을 '지역 활동비'로 변경 가능합니다."
)

region_labels = settings.get("region_labels", {})
updated_labels = {}
for region in regions_list:
    current_labels = region_labels.get(region, {})
    with st.expander(f"🗺️ {region} 지역 명칭 설정"):
        lc1, lc2 = st.columns(2)
        with lc1:
            base_cost_label = st.text_input(
                "운영비 항목 명칭",
                value=current_labels.get("manager_base_cost", "운영비"),
                key=f"label_base_{region}",
                help="정산 엔진에서 매니저 고정비용 항목명으로 표시됩니다"
            )
            incentive_label = st.text_input(
                "인센티브 항목 명칭",
                value=current_labels.get("incentive", "인센티브"),
                key=f"label_incentive_{region}",
            )
        with lc2:
            activity_label = st.text_input(
                "지역 활동비 명칭",
                value=current_labels.get("region_activity", "지역 활동비"),
                key=f"label_activity_{region}",
            )
            allowance_label = st.text_input(
                "기사 수당 항목 명칭",
                value=current_labels.get("driver_allowance", "기사 수당"),
                key=f"label_allowance_{region}",
            )
        updated_labels[region] = {
            "manager_base_cost": base_cost_label,
            "incentive": incentive_label,
            "region_activity": activity_label,
            "driver_allowance": allowance_label,
        }

if st.button("🏷️ 명칭 설정 저장", type="primary"):
    cur = get_settings()
    cur["region_labels"] = updated_labels
    save_settings(cur)
    st.success("✅ 지역별 정산 명칭 저장 완료!")
    st.rerun()

st.divider()

st.subheader("📲 카카오 알림 설정")
st.caption(
    "이상 징후(AI 사진 불일치·정산가 초과·미등록 번호 접촉) 발생 시 대표 휴대폰으로 즉시 알림을 발송합니다. "
    "Kakao Alimtalk 웹훅 또는 범용 HTTP 웹훅 URL을 입력하세요."
)

notif_col1, notif_col2, notif_col3 = st.columns(3)
with notif_col1:
    kakao_webhook_url = st.text_input(
        "카카오 알림 웹훅 URL",
        value=settings.get("kakao_webhook_url", ""),
        placeholder="https://kapi.kakao.com/... 또는 범용 웹훅",
        help="Kakao Alimtalk 웹훅 URL 또는 Slack/Make 등 범용 웹훅. 비워두면 알림 비활성화.",
        disabled=_read_only,
    )
with notif_col2:
    owner_phone = st.text_input(
        "대표 휴대폰 번호",
        value=settings.get("owner_phone", ""),
        placeholder="010-0000-0000",
        help="알림 수신 대표자 번호 (카카오 알림톡 페이로드에 포함)",
        disabled=_read_only,
    )
with notif_col3:
    app_base_url = st.text_input(
        "관리 페이지 URL (선택)",
        value=settings.get("app_base_url", ""),
        placeholder="https://순삭OS.replit.app",
        help="알림 메시지 내 [관리 페이지 링크] 및 텔레그램 딥링크에 사용",
        disabled=_read_only,
    )

# 알림 테스트 버튼 (Owner 전용)
if is_owner() and kakao_webhook_url:
    if st.button("🧪 테스트 알림 발송"):
        from utils.notifications import _send_webhook
        test_payload = {
            "event": "test",
            "message": "[순삭OS] 테스트 알림입니다. 웹훅 연결이 정상입니다.",
            "to": owner_phone,
        }
        result = _send_webhook(test_payload, kakao_webhook_url)
        if result["success"]:
            st.success(f"✅ 테스트 알림 발송 성공 (HTTP {result['status_code']})")
        else:
            st.error(f"❌ 발송 실패: {result.get('error') or result.get('status_code')}")
elif not kakao_webhook_url:
    st.info("ℹ️ 웹훅 URL을 입력하면 이상 징후 자동 알림이 활성화됩니다.")

st.divider()

# ──────────────── 텔레그램 알림 설정 ────────────────
st.subheader("✈️ 텔레그램 알림 설정")
st.caption(
    "텔레그램 봇을 통해 이상 징후 알림을 실시간으로 수신합니다. "
    "메시지 하단에 **[OS 상세페이지 바로가기]** 딥링크가 자동 첨부되어 클릭 즉시 해당 주문 견적 화면으로 연결됩니다."
)

tg_col1, tg_col2 = st.columns(2)
with tg_col1:
    telegram_bot_token = st.text_input(
        "텔레그램 봇 토큰",
        value=settings.get("telegram_bot_token", ""),
        type="password",
        placeholder="123456789:ABCDefgh...",
        help="@BotFather에서 발급받은 봇 토큰. 비워두면 텔레그램 알림 비활성화.",
        disabled=_read_only,
    )
with tg_col2:
    telegram_chat_id = st.text_input(
        "텔레그램 Chat ID",
        value=settings.get("telegram_chat_id", ""),
        placeholder="-100123456789 또는 개인 ID",
        help="알림을 수신할 채팅방(그룹/개인) ID. @userinfobot에서 확인 가능.",
        disabled=_read_only,
    )

_tg_active = bool(settings.get("telegram_bot_token") and settings.get("telegram_chat_id"))
if _tg_active:
    st.success("✅ 텔레그램 알림 활성화 상태 — 모든 이상 징후 알림에 OS 딥링크가 자동 첨부됩니다.")
else:
    st.info("ℹ️ 봇 토큰 + Chat ID를 모두 입력하면 텔레그램 알림이 활성화됩니다.")

if is_owner() and telegram_bot_token and telegram_chat_id:
    if st.button("🧪 Owner 텔레그램 테스트 발송", key="tg_test"):
        from utils.notifications import _send_telegram
        result = _send_telegram(
            "🔐 [순삭OS Owner 테스트] 긴급/예외 알림 채널 — 연결 정상 확인.",
            order_id=None,
        )
        if result["success"]:
            st.success("✅ Owner 텔레그램 테스트 발송 성공!")
        else:
            st.error(f"❌ 발송 실패: {result.get('error')}")

st.divider()

# ──────────────── 매니저 텔레그램 알림 설정 (지역별 분리) ────────────────
st.subheader("👔 매니저 텔레그램 설정 — 지역별 분리 (일상 운영 알림 전용)")
st.markdown(
    """
<div style="background:#e3f2fd;border-left:4px solid #1976d2;border-radius:8px;
     padding:12px 16px;margin-bottom:12px">
<b>📢 알림 수신자 분리 정책</b><br>
• <b>매니저 1(세종) 채널</b>: 세종 지역 리드/지연/견적 → 세종 매니저만 수신<br>
• <b>매니저 2(본사) 채널</b>: 본사 지역 리드/지연/견적 → 본사 매니저만 수신<br>
• <b>Owner 채널</b> (위): AI 불일치 / 미등록 번호 / 정산보류 / 근태불량 / 사고/클레임 → Owner만<br>
• Owner는 일상 운영 알림을 수신하지 않습니다 <b>(무소음 모드)</b>
</div>
""",
    unsafe_allow_html=True,
)

# 매니저 1 (세종)
st.markdown("**👔 매니저 1 — 세종 지역 텔레그램**")
m1c1, m1c2 = st.columns(2)
with m1c1:
    mgr1_telegram_bot_token = st.text_input(
        "매니저1(세종) 봇 토큰",
        value=settings.get("mgr1_telegram_bot_token", ""),
        type="password",
        placeholder="123456789:ABCDefgh...",
        disabled=_read_only,
    )
with m1c2:
    mgr1_telegram_chat_id = st.text_input(
        "매니저1(세종) Chat ID",
        value=settings.get("mgr1_telegram_chat_id", ""),
        placeholder="-100123456789",
        disabled=_read_only,
    )
_mgr1_active = bool(mgr1_telegram_bot_token and mgr1_telegram_chat_id)
if _mgr1_active:
    st.success("✅ 매니저1(세종) 텔레그램 활성화")
    if is_owner() and st.button("🧪 매니저1(세종) 테스트 발송", key="mgr1_tg_test"):
        from utils.notifications import _raw_telegram
        result = _raw_telegram(mgr1_telegram_bot_token, mgr1_telegram_chat_id,
                               "👔 [순삭OS] 매니저1(세종) 알림 채널 — 연결 정상 확인.")
        st.success("✅ 발송 성공!") if result["success"] else st.error(f"❌ {result.get('error')}")
else:
    st.info("ℹ️ 봇 토큰 + Chat ID를 입력하면 세종 지역 알림이 활성화됩니다.")

st.markdown("")

# 매니저 2 (본사)
st.markdown("**👔 매니저 2 — 본사 지역 텔레그램**")
m2c1, m2c2 = st.columns(2)
with m2c1:
    mgr2_telegram_bot_token = st.text_input(
        "매니저2(본사) 봇 토큰",
        value=settings.get("mgr2_telegram_bot_token", ""),
        type="password",
        placeholder="123456789:ABCDefgh...",
        disabled=_read_only,
    )
with m2c2:
    mgr2_telegram_chat_id = st.text_input(
        "매니저2(본사) Chat ID",
        value=settings.get("mgr2_telegram_chat_id", ""),
        placeholder="-100123456789",
        disabled=_read_only,
    )
_mgr2_active = bool(mgr2_telegram_bot_token and mgr2_telegram_chat_id)
if _mgr2_active:
    st.success("✅ 매니저2(본사) 텔레그램 활성화")
    if is_owner() and st.button("🧪 매니저2(본사) 테스트 발송", key="mgr2_tg_test"):
        from utils.notifications import _raw_telegram
        result = _raw_telegram(mgr2_telegram_bot_token, mgr2_telegram_chat_id,
                               "👔 [순삭OS] 매니저2(본사) 알림 채널 — 연결 정상 확인.")
        st.success("✅ 발송 성공!") if result["success"] else st.error(f"❌ {result.get('error')}")
else:
    st.info("ℹ️ 봇 토큰 + Chat ID를 입력하면 본사 지역 알림이 활성화됩니다.")

st.divider()

# ──────────────── 법인폰 3대 등록 ────────────────
st.subheader("📱 법인폰 3대 등록 — 디바이스 연동")
st.markdown(
    """
<div style="background:#f3e5f5;border-left:4px solid #7b1fa2;border-radius:8px;
     padding:12px 16px;margin-bottom:12px">
<b>📱 법인폰 번호 등록 목적</b><br>
• 등록된 번호는 통화 로그 업로드 시 <b>지역 자동 매칭</b>에 사용됩니다.<br>
• 텔레그램 리포트 전송 시 <b>매니저 번호로만 필터링</b>하여 Owner 폰에 일상 알림이 수신되지 않습니다.<br>
• Owner 전용 수정 항목입니다.
</div>
""", unsafe_allow_html=True)

dp_c1, dp_c2, dp_c3 = st.columns(3)
with dp_c1:
    st.markdown("**👑 대표(Owner) 법인폰**")
    owner_device_phone = st.text_input(
        "대표 법인폰 번호",
        value=settings.get("owner_device_phone", ""),
        placeholder="010-0000-0000",
        help="Owner 법인폰 — 긴급/예외 알림만 수신",
        disabled=_read_only,
    )
with dp_c2:
    st.markdown("**👔 매니저1(세종) 법인폰**")
    mgr1_device_phone = st.text_input(
        "매니저1(세종) 법인폰 번호",
        value=settings.get("mgr1_device_phone", ""),
        placeholder="010-0000-0000",
        help="세종 담당 매니저 법인폰 — 세종 지역 일상 알림 수신",
        disabled=_read_only,
    )
with dp_c3:
    st.markdown("**👔 매니저2(본사) 법인폰**")
    mgr2_device_phone = st.text_input(
        "매니저2(본사) 법인폰 번호",
        value=settings.get("mgr2_device_phone", ""),
        placeholder="010-0000-0000",
        help="본사 담당 매니저 법인폰 — 본사 지역 일상 알림 수신",
        disabled=_read_only,
    )

if owner_device_phone or mgr1_device_phone or mgr2_device_phone:
    st.markdown(
        f"<div style='background:#e8f5e9;border-radius:8px;padding:8px 14px;font-size:13px'>"
        f"📱 등록된 법인폰: "
        f"{'👑 ' + owner_device_phone if owner_device_phone else ''} "
        f"{'| 👔(세종) ' + mgr1_device_phone if mgr1_device_phone else ''} "
        f"{'| 👔(본사) ' + mgr2_device_phone if mgr2_device_phone else ''}"
        f"</div>", unsafe_allow_html=True)

st.divider()

st.subheader("🔑 API 키 설정")
col_a, col_b = st.columns(2)
with col_a:
    kakao_api_key = st.text_input(
        "카카오 알림톡 API 키", value=settings.get("kakao_api_key", ""),
        type="password", placeholder="카카오비즈니스 API 키"
    )
with col_b:
    grenter_api_key = st.text_input(
        "GRENTER API 키", value=settings.get("grenter_api_key", ""),
        type="password", placeholder="GRENTER 세무 플랫폼 API 키"
    )

st.divider()

if _read_only:
    st.info("👔 매니저 모드: 설정 내용 조회만 가능합니다. 변경하려면 대표(Owner)에게 요청하세요.")

col_save, col_reset = st.columns([1, 4])
with col_save:
    if st.button("💾 설정 저장", type="primary", disabled=_read_only):
        cur = get_settings()
        new_settings = {
            **cur,
            "driver_ratio": driver_ratio,
            "cs_ratio": cs_ratio,
            "success_fee_ratio": success_fee_ratio,
            "dispatch_fee": int(dispatch_fee),
            "withholding_tax_rate": withholding_rate,
            "delay_threshold_min": int(delay_threshold_min),
            "auto_penalty_amount": int(auto_penalty_amount),
            "kakao_webhook_url": kakao_webhook_url,
            "owner_phone": owner_phone,
            "app_base_url": app_base_url,
            "telegram_bot_token": telegram_bot_token,
            "telegram_chat_id": telegram_chat_id,
            "mgr1_telegram_bot_token": mgr1_telegram_bot_token,
            "mgr1_telegram_chat_id": mgr1_telegram_chat_id,
            "mgr2_telegram_bot_token": mgr2_telegram_bot_token,
            "mgr2_telegram_chat_id": mgr2_telegram_chat_id,
            "owner_device_phone": owner_device_phone,
            "mgr1_device_phone": mgr1_device_phone,
            "mgr2_device_phone": mgr2_device_phone,
            "kakao_api_key": kakao_api_key,
            "grenter_api_key": grenter_api_key,
            "manager_base_cost": int(manager_base_cost),
            "demolition_incentive_min": int(demolition_incentive_min),
            "demolition_incentive_max": int(demolition_incentive_max),
            "active_driver_threshold": int(active_driver_threshold),
            "direct_team_threshold": int(direct_team_threshold),
            "direct_team_full_cost": int(direct_team_full_cost),
            "direct_team_half_cost": int(direct_team_half_cost),
        }
        save_settings(new_settings)
        st.success("✅ 설정이 저장되었습니다!")
        st.rerun()

with col_reset:
    if st.button("🔄 기본값 초기화", disabled=_read_only):
        default = {
            "driver_ratio": 0.70, "cs_ratio": 0.40, "success_fee_ratio": 0.05,
            "withholding_tax_rate": 0.033, "dispatch_fee": 30000,
            "kakao_api_key": "", "grenter_api_key": "",
            "manager_base_cost": 1500000,
            "demolition_incentive_min": 50000, "demolition_incentive_max": 100000,
            "active_driver_threshold": 60,
            "direct_team_threshold": 40,
            "direct_team_full_cost": 1500000, "direct_team_half_cost": 750000,
        }
        save_settings(default)
        st.success("✅ 기본값으로 초기화되었습니다!")
        st.rerun()

st.divider()

st.subheader("ℹ️ 현재 설정 요약")
s = get_settings()
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("기사 수수료", f"{s['driver_ratio']*100:.1f}%")
with col2:
    st.metric("CS 비율", f"{s['cs_ratio']*100:.1f}%")
with col3:
    st.metric("성공보수", f"{s['success_fee_ratio']*100:.1f}%")
with col4:
    st.metric("출동비", f"₩{s['dispatch_fee']:,}")
with col5:
    st.metric("원천징수율", f"{s['withholding_tax_rate']*100:.1f}%")

col6, col7, col8 = st.columns(3)
with col6:
    st.metric("매니저 기본 운영비", f"₩{s.get('manager_base_cost', 1500000):,}/월")
with col7:
    st.metric("직영팀 전액 기준", f"월 {s.get('direct_team_threshold', 40)}건 이상")
with col8:
    st.metric("활성 기사 기준", f"월 {s.get('active_driver_threshold', 60)}건 이상")

show_legal_warning()
