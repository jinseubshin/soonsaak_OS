import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (
    get_drivers, get_orders, add_order, update_order,
    add_notification, add_journey_notification, mark_notification_sent,
    get_settings, get_driver_by_id, is_blacklisted
)
from utils.footer import show_legal_warning
from utils.masks import mask_phone
from utils.rbac import render_role_selector, is_cs, is_owner, is_manager, is_executor, role_badge
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="CS 상담센터 — 순삭 OS", page_icon="🎧", layout="wide")
st.title("🎧 CS 상담센터")
st.caption("고객 상담 입력 → 1차 견적 → 철거 시 매니저 견적 확정 → 자동 알림톡")

render_role_selector()
st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")

# Executor 역할은 이 페이지 접근 불가
if is_executor():
    st.error("🚫 기사(Executor) 모드에서는 CS 상담 페이지에 접근할 수 없습니다.")
    st.stop()

IS_CS = is_cs()
IS_ADMIN = is_owner()

if IS_CS:
    st.warning(
        "🔐 **CS 상담원 모드** — 적용된 제한:\n"
        "- 고객 연락처 뒷자리 **전체 마스킹** (010-****-****)\n"
        "- 본사 순이익/마진 데이터 비공개\n"
        "- 기본 요금 자동 산출만 가능 (임의 수정 불가)\n"
        "- 블랙리스트 고객 즉시 경고"
    )
else:
    st.info(
        "✅ **CS 권한**: 상담 내용·품목 입력 및 수거 건 1차 견적 확정 | "
        "❌ **CS 제한**: 철거 건 최종 가격 결정은 매니저 전용 | "
        "🔨 **철거 건**: 등록 즉시 매니저에게 알림 → 매니저가 현장 조건 반영 후 견적 확정"
    )

# ─── 블랙리스트 실시간 조회 (폼 입력 전 사전 체크) ───
st.markdown("#### 🔍 블랙리스트 사전 조회")
bl_check_cols = st.columns([2, 1])
with bl_check_cols[0]:
    check_phone = st.text_input(
        "고객 번호 사전 조회 (상담 전 확인)",
        placeholder="010-0000-0000",
        key="bl_precheck_phone"
    )
with bl_check_cols[1]:
    st.markdown("<br>", unsafe_allow_html=True)
    do_check = st.button("🔍 블랙리스트 조회", key="bl_check_btn")

if do_check and check_phone:
    bl_entry = is_blacklisted(check_phone)
    if bl_entry:
        st.error(
            f"🚨 **[주의] 블랙리스트 고객입니다!**\n\n"
            f"📞 번호: {bl_entry.get('phone','—')} | "
            f"이름: {bl_entry.get('customer_name','—')} | "
            f"사유: **{bl_entry.get('reason','—')}**\n\n"
            f"상세: {bl_entry.get('detail','—')} | "
            f"등록자: {bl_entry.get('added_by','—')} | "
            f"등록일: {bl_entry.get('created_at','—')[:10]}"
        )
    elif check_phone:
        st.success(f"✅ {check_phone} — 블랙리스트 해당 없음. 정상 상담 가능합니다.")

settings = get_settings()
DIRECT_THRESHOLD = settings.get("direct_team_threshold", 40)
DEMO_INCENTIVE_MIN = settings.get("demolition_incentive_min", 50000)
DEMO_INCENTIVE_MAX = settings.get("demolition_incentive_max", 100000)
ACCOUNT_WARNING = (
    "\n\n⚠️ [본사 안내] 본사 공식 계좌 외 기사에게 직접 현금 지급 시 "
    "AS 및 보상이 불가합니다. 모든 결제는 본사 공식 채널을 이용해 주세요."
)

ITEM_PRICE_TABLE = {
    "냉장고 (소)": {"base": 30000, "work_type": "수거"},
    "냉장고 (대)": {"base": 50000, "work_type": "수거"},
    "세탁기": {"base": 30000, "work_type": "수거"},
    "TV (50인치 이하)": {"base": 20000, "work_type": "수거"},
    "TV (50인치 초과)": {"base": 35000, "work_type": "수거"},
    "소파 (1인용)": {"base": 25000, "work_type": "수거"},
    "소파 (3인용 이상)": {"base": 50000, "work_type": "수거"},
    "침대 (싱글)": {"base": 30000, "work_type": "수거"},
    "침대 (퀸/킹)": {"base": 50000, "work_type": "수거"},
    "책상/의자 세트": {"base": 25000, "work_type": "수거"},
    "에어컨 (벽걸이)": {"base": 50000, "work_type": "수거"},
    "에어컨 (스탠드)": {"base": 80000, "work_type": "수거"},
    "철거 — 인테리어 (소, ~10평)": {"base": 200000, "work_type": "철거"},
    "철거 — 인테리어 (중, 11~25평)": {"base": 400000, "work_type": "철거"},
    "철거 — 인테리어 (대, 26평+)": {"base": 800000, "work_type": "철거"},
    "철거 — 욕실": {"base": 300000, "work_type": "철거"},
    "철거 — 주방": {"base": 350000, "work_type": "철거"},
    "기타 (직접 입력)": {"base": 0, "work_type": "수거"},
}

WASTE_TYPE_OPTIONS = ["건설폐기물", "가구류", "가전류", "혼합 폐기물", "인테리어 자재", "욕실 자재", "주방 자재", "기타"]
HIGH_VALUE_THRESHOLD = 300000

tab1, tab2, tab3 = st.tabs(["📝 신규 상담 접수", "📋 상담 이력 조회", "📊 오늘 접수 현황"])
drivers = get_drivers()
orders = get_orders()

# ──────────────── Tab 1: 신규 상담 접수 ────────────────
with tab1:
    st.subheader("📝 신규 상담 접수 — CS 전용")

    # 작업 유형 먼저 선택 (철거 여부에 따라 폼 구성 달라짐)
    form_work_type = st.radio(
        "작업 유형 선택 *",
        ["📦 수거", "🔨 철거"],
        horizontal=True,
        key="form_work_type_radio"
    )
    is_demolition_form = form_work_type == "🔨 철거"

    if is_demolition_form:
        st.warning(
            "🔨 **철거 건 접수 안내**\n\n"
            "- 철거 건은 **매니저가 현장 조건을 확인 후 최종 견적을 확정**합니다.\n"
            "- 등록 즉시 담당 매니저에게 **실시간 알림**이 발송됩니다.\n"
            "- CS는 기초 정보와 현장 조건만 입력하세요."
        )

    with st.form("cs_consultation_form", clear_on_submit=False):
        st.markdown("#### 👤 고객 정보")
        col1, col2 = st.columns(2)
        with col1:
            customer = st.text_input("고객명 *", placeholder="홍길동")
            customer_phone = st.text_input("고객 연락처 *", placeholder="010-0000-0000")
        with col2:
            pickup = st.text_input("현장 주소 *", placeholder="서울 강남구 역삼동 123-45")
            destination = st.text_input("목적지 (폐기장/하역지)", placeholder="경기도 용인시 처인구 456")

        scheduled_time = st.text_input("예약 일시", value=datetime.now().strftime("%Y-%m-%d %H:%M"))

        # ── 지역 + 마케팅 유입경로 ──────────────────────────────────────────────
        st.markdown("#### 🗺️ 지역 & 유입경로")
        reg_col1, reg_col2 = st.columns(2)
        with reg_col1:
            _all_regions = get_settings().get("regions", ["본사", "세종"])
            form_region = st.selectbox(
                "담당 지역 *",
                _all_regions,
                help="세종 지역은 수거 및 철거 모두 접수 가능합니다",
            )
        with reg_col2:
            MARKETING_CHANNELS = [
                "—", "당근마켓", "네이버 플레이스", "카카오 채널",
                "인스타그램/SNS", "지인 추천", "블로그/기사", "기타",
            ]
            form_channel = st.selectbox(
                "마케팅 유입 경로",
                MARKETING_CHANNELS,
                help="세종 지역 ROI 분석에 활용됩니다",
            )

        # ════════════════════════════════════════════
        if not is_demolition_form:
            # ── 수거 전용 폼
            st.markdown("#### 📦 수거 품목 선택 및 견적")
            items_selected = st.multiselect(
                "상담 품목 선택 *",
                options=[k for k, v in ITEM_PRICE_TABLE.items() if v["work_type"] == "수거"],
                help="품목을 선택하면 기준 요금이 자동 계산됩니다"
            )
            auto_base = sum(ITEM_PRICE_TABLE[i]["base"] for i in items_selected)

            if items_selected:
                st.markdown(f"**자동 산출 기준 요금:** ₩{auto_base:,}")
            else:
                auto_base = 30000

            st.markdown(
                f"<div style='padding:8px;background:#f0f2f6;border-radius:6px;"
                f"font-size:18px;font-weight:bold'>기준 요금: ₩{auto_base:,}</div>",
                unsafe_allow_html=True
            )
            st.caption("💡 수거 건 가격은 CS가 확정합니다.")
            base_fee = auto_base

            # 철거 전용 필드는 비어있음
            demolition_area = None
            has_ladder_car = False
            waste_types = []
            has_asbestos = False
            floor_number = None
            has_elevator = True
            demolition_scope = ""
            team_size = 1

        else:
            # ── 철거 전용 폼
            items_selected = [i for i in ITEM_PRICE_TABLE if ITEM_PRICE_TABLE[i]["work_type"] == "철거"]

            st.markdown("#### 🔨 철거 상세 정보 입력 (CS 접수 필수)")
            st.info("아래 정보를 최대한 상세히 입력해주세요. 매니저가 이 내용을 기반으로 최종 견적을 산출합니다.")

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                demolition_scope = st.selectbox(
                    "철거 범위 *",
                    ["인테리어 전체", "부분 인테리어", "욕실", "주방", "방 단위", "기타"]
                )
                demolition_area = st.number_input(
                    "철거 면적 (평) *",
                    min_value=1.0, max_value=500.0, value=10.0, step=0.5
                )
                floor_number = st.number_input("작업 층수", min_value=1, max_value=50, value=1)
            with col_d2:
                has_elevator = st.checkbox("엘리베이터 있음", value=True)
                has_ladder_car = st.checkbox("사다리차 필요", value=False)
                has_asbestos = st.checkbox("⚠️ 석면 의심 (위험물질)", value=False)
                team_size = st.radio("팀 구성 (철거 기본: 2인 1조)", [1, 2, 3], index=1, horizontal=True)

            st.markdown("**폐기물 종류 ***")
            waste_types = st.multiselect(
                "폐기물 종류",
                WASTE_TYPE_OPTIONS,
                default=["건설폐기물"]
            )

            # CS는 기준 견적만 표시, 최종 금액은 매니저 확정
            area_val = demolition_area or 10.0
            if area_val <= 10:
                cs_estimate = 200000
            elif area_val <= 25:
                cs_estimate = 400000
            else:
                cs_estimate = 800000
            if has_ladder_car:
                cs_estimate += 100000
            if has_asbestos:
                cs_estimate += 200000

            st.markdown("#### 💰 CS 기초 견적 (참고용)")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                st.markdown(
                    f"<div style='padding:10px;background:#fff3cd;border-radius:8px;"
                    f"border:1px solid #ffc107'>"
                    f"<b>CS 기초 견적 (참고용):</b><br>"
                    f"<span style='font-size:22px;font-weight:bold'>₩{cs_estimate:,}</span>"
                    f"<br><small>⚠️ 최종 견적은 매니저가 확정합니다</small></div>",
                    unsafe_allow_html=True
                )
            with col_e2:
                if has_asbestos:
                    st.error("☢️ 석면 의심 — 등록 즉시 매니저에게 긴급 알림 발송됩니다!")
                elif has_ladder_car:
                    st.warning("🚛 사다리차 필요 — 추가 견적 산정 대상")

            base_fee = cs_estimate
            items_selected = [f"철거 — {demolition_scope} ({demolition_area}평)"]

        st.markdown("#### 📷 현장 사진")
        cs_photo = st.file_uploader(
            "고객 제공 현장 사진 (선택)", type=["jpg", "jpeg", "png"],
            help="카카오톡 등으로 받은 현장 사진을 업로드하세요"
        )
        if cs_photo:
            st.image(cs_photo, caption="현장 사진 미리보기", width=300)

        st.markdown("#### 📝 상담 메모")
        cs_memo = st.text_area(
            "상담 특이사항 / 고객 요청사항",
            placeholder="예: 4층 엘리베이터 없음, 오전 중 작업 필수, 특수 폐기물 있음",
            height=80
        )

        st.divider()
        wt_label = "🔨 철거" if is_demolition_form else "📦 수거"
        confirm_col1, confirm_col2 = st.columns([3, 1])
        with confirm_col1:
            if is_demolition_form:
                st.markdown(
                    f"**[{wt_label} 예약 접수]** 클릭 시:\n"
                    f"- ① 주문이 '매니저 견적 대기' 상태로 등록됩니다\n"
                    f"- ② 담당 **매니저에게 실시간 철거 건 알림**이 발송됩니다\n"
                    f"- ③ 매니저가 현장 조건 반영 후 최종 견적을 확정합니다\n"
                    f"- ④ 견적 확정 시 고객에게 **공식 견적서 알림톡**이 자동 발송됩니다"
                )
            else:
                st.markdown(
                    f"**[{wt_label} 예약 확정]** 클릭 시:\n"
                    f"- ① 주문 등록 및 배차 대기 상태로 설정됩니다\n"
                    f"- ② 고객에게 **예약 확정 알림톡**이 자동 발송됩니다\n"
                    f"- ③ 우선순위 알고리즘으로 최적 기사 자동 추천"
                )
        with confirm_col2:
            btn_label = "🔨 철거 접수" if is_demolition_form else "✅ 예약 확정"
            submitted = st.form_submit_button(btn_label, type="primary", use_container_width=True)

        if submitted:
            missing = []
            if not customer: missing.append("고객명")
            if not customer_phone: missing.append("고객 연락처")
            if not pickup: missing.append("현장 주소")
            if not items_selected: missing.append("품목/철거범위")
            if is_demolition_form and not waste_types: missing.append("폐기물 종류")
            if missing:
                st.error(f"❌ 필수 입력 누락: {', '.join(missing)}")
            else:
                work_type_val = "철거" if is_demolition_form else "수거"
                order_status = "pending"

                _channel_val = form_channel if form_channel != "—" else None
                order_id = add_order({
                    "customer": customer,
                    "customer_phone": customer_phone,
                    "pickup": pickup,
                    "destination": destination or pickup,
                    "scheduled_time": scheduled_time,
                    "driver_id": None,
                    "status": order_status,
                    "base_fee": int(base_fee),
                    "extra_fee": 0,
                    "extra_fee_status": None,
                    "payment_confirmed": False,
                    "work_type": work_type_val,
                    "region": form_region,
                    "marketing_channel": _channel_val,
                    "cs_confirmed": True,
                    "cs_memo": cs_memo,
                    "cs_items": items_selected,
                    "cs_photo": cs_photo.name if cs_photo else None,
                    "manager_closed": False,
                    "field_report": None,
                    "settlement_ready": False,
                    # 철거 전용
                    "demolition_area": float(demolition_area) if demolition_area else None,
                    "has_ladder_car": has_ladder_car,
                    "waste_types": waste_types,
                    "has_asbestos": has_asbestos,
                    "floor_number": int(floor_number) if floor_number else None,
                    "has_elevator": has_elevator,
                    "demolition_scope": demolition_scope,
                    "team_size": team_size,
                    "manager_quote": None,
                    "manager_quote_confirmed": False,
                    "manager_quote_sent": False,
                })

                if is_demolition_form:
                    # 매니저 실시간 알림 (긴급)
                    asbestos_tag = " ☢️ 석면 의심!" if has_asbestos else ""
                    ladder_tag = " 🚛 사다리차 필요" if has_ladder_car else ""
                    mgr_alert_msg = (
                        f"[순삭 본사] 🔨 철거 건 신규 접수{asbestos_tag}{ladder_tag}\n"
                        f"주문 #{order_id} — {customer} | {pickup}\n"
                        f"철거 범위: {demolition_scope} | 면적: {demolition_area}평 | {floor_number}층\n"
                        f"팀 구성: {team_size}인 | 폐기물: {', '.join(waste_types)}\n"
                        f"CS 기초 견적: ₩{base_fee:,} → 매니저 최종 견적 확정 필요"
                    )
                    add_notification({
                        "order_id": order_id,
                        "customer": "매니저",
                        "customer_phone": "내부",
                        "type": "철거건_매니저알림",
                        "message": mgr_alert_msg,
                        "sender": "순삭 본사 시스템",
                        "is_internal": True,
                    })
                    st.success(
                        f"✅ 주문 #{order_id} 철거 건 접수 완료!\n\n"
                        f"{'☢️ 석면 의심 — 긴급 알림 발송!' if has_asbestos else ''}"
                        f"📲 **매니저에게 실시간 알림 발송 완료**\n\n"
                        f"매니저가 현장 조건 확인 후 최종 견적을 입력하면 고객에게 자동 발송됩니다.\n"
                        f"배차 스케줄링 > 매니저 모니터링에서 진행 상황을 확인하세요."
                    )
                    if has_asbestos:
                        st.error("☢️ **석면 의심 건** — 전문 처리 업체 별도 안내 필요. 매니저에게 즉시 연락하세요.")
                else:
                    # 수거 건: 고객 예약 확정 알림톡 발송
                    conf_msg = (
                        f"[순삭 본사] {customer}님, 예약이 확정되었습니다! 🎉\n"
                        f"작업 일시: {scheduled_time}\n"
                        f"품목: {', '.join(items_selected[:3])}{'외' if len(items_selected) > 3 else ''}\n"
                        f"예상 요금: ₩{base_fee:,}"
                        + ACCOUNT_WARNING
                    )
                    add_notification({
                        "order_id": order_id,
                        "customer": customer,
                        "customer_phone": customer_phone,
                        "type": "예약확정",
                        "message": conf_msg,
                        "sender": "순삭 본사 시스템",
                    })
                    add_journey_notification({
                        "order_id": order_id,
                        "customer": customer,
                        "customer_phone": customer_phone,
                        "type": "📅 예약 확정",
                        "message": conf_msg,
                    })
                    mark_notification_sent(order_id, "notif_reserved")
                    st.success(
                        f"✅ 주문 #{order_id} 수거 예약 확정!\n\n"
                        f"📲 **{customer}** 님께 예약 확정 알림톡 자동 발송됨"
                    )
                st.rerun()

# ──────────────── Tab 2: 상담 이력 조회 ────────────────
with tab2:
    st.subheader("📋 CS 접수 주문 이력")
    all_orders_view = sorted(orders, key=lambda x: x.get("created_at", ""), reverse=True)

    status_labels = {
        "pending": "⏳ 대기", "dispatched": "📍 배차완료",
        "in_progress": "🔄 진행중", "completed": "✅ 완료", "cancelled": "❌ 취소",
    }

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_status = st.selectbox("상태 필터", ["전체", "대기", "배차완료", "진행중", "완료"])
    with col_f2:
        filter_type = st.selectbox("작업 유형", ["전체", "수거", "철거"])
    with col_f3:
        filter_quote = st.selectbox("철거 견적", ["전체", "견적 미확정", "견적 확정됨"])

    filtered = all_orders_view
    if filter_status != "전체":
        status_rev = {"대기": "pending", "배차완료": "dispatched", "진행중": "in_progress", "완료": "completed"}
        filtered = [o for o in filtered if o["status"] == status_rev.get(filter_status)]
    if filter_type != "전체":
        filtered = [o for o in filtered if o.get("work_type") == filter_type]
    if filter_quote == "견적 미확정":
        filtered = [o for o in filtered if o.get("work_type") == "철거" and not o.get("manager_quote_confirmed")]
    elif filter_quote == "견적 확정됨":
        filtered = [o for o in filtered if o.get("manager_quote_confirmed")]

    if not filtered:
        st.info("해당 조건의 주문이 없습니다.")
    else:
        for o in filtered[:20]:
            drv = get_driver_by_id(o.get("driver_id"))
            drv2 = get_driver_by_id(o.get("second_driver_id"))
            is_demo = o.get("work_type") == "철거"

            tags = []
            if is_demo: tags.append("🔨 철거")
            if o.get("has_asbestos"): tags.append("☢️ 석면")
            if o.get("has_ladder_car"): tags.append("🚛 사다리차")
            if o.get("team_size", 1) >= 2: tags.append(f"👥 {o.get('team_size',1)}인조")
            if o.get("manager_quote_confirmed"): tags.append("✅ 견적확정")
            elif is_demo: tags.append("⏳ 견적대기")
            if o.get("manager_closed"): tags.append("👔 매니저성사")
            if o.get("field_report"): tags.append("🚨 현장보고")

            tag_str = " ".join(tags)
            price_display = f"₩{o.get('manager_quote', o['base_fee']):,}" if o.get('manager_quote_confirmed') else f"CS기초 ₩{o['base_fee']:,}"

            with st.expander(
                f"#{o['id']} {o['customer']} | {price_display} | "
                f"{status_labels.get(o['status'], o['status'])} {tag_str}"
            ):
                col1, col2, col3 = st.columns(3)
                # CS 역할: 연락처 마스킹, 마진/수익 비공개
                phone_display = mask_phone(o['customer_phone'], 'cs' if IS_CS else 'admin')
                with col1:
                    st.markdown(f"**고객:** {o['customer']}")
                    st.markdown(f"**연락처:** {phone_display}")
                    if IS_CS:
                        st.caption("🔒 연락처 전체 표시는 관리자 권한이 필요합니다")
                    st.markdown(f"**예약:** {o['scheduled_time']}")
                    st.markdown(f"**현장:** {o['pickup']}")
                with col2:
                    st.markdown(f"**기사(1):** {drv['name'] if drv else '미배차'}")
                    if drv2:
                        st.markdown(f"**기사(2):** {drv2['name']}")
                    st.markdown(f"**상태:** {status_labels.get(o['status'], o['status'])}")
                    photos_ok = o.get("photo_before") and o.get("photo_after") and o.get("photo_cleanup")
                    st.markdown(f"**사진:** {'✅' if photos_ok else '⚠️ 미완료'}")
                with col3:
                    if is_demo:
                        st.markdown(f"**철거 범위:** {o.get('demolition_scope','—')} | {o.get('demolition_area','—')}평")
                        st.markdown(f"**층수:** {o.get('floor_number','—')}층 | 엘리베이터: {'✅' if o.get('has_elevator') else '❌'}")
                        if o.get("manager_quote_confirmed"):
                            # CS 역할: 마진/수익 계산값 숨김 → 확정 여부만 표시
                            if IS_CS:
                                st.success("✅ 매니저 견적 확정됨 (금액은 관리자 확인)")
                            else:
                                st.success(f"✅ 매니저 확정 견적: ₩{o.get('manager_quote',0):,}")
                        else:
                            st.warning("⏳ 매니저 견적 확정 대기 중")
                    else:
                        st.markdown(f"**품목:** {', '.join((o.get('cs_items') or [])[:3])}")
                        st.markdown(f"**기본요금:** ₩{o['base_fee']:,}")
                        if not IS_CS:
                            driver_pay = o['base_fee'] * settings.get("driver_ratio", 0.7)
                            cs_share = o['base_fee'] * settings.get("cs_ratio", 0.4)
                            st.caption(f"기사지급: ₩{driver_pay:,.0f} | CS배분: ₩{cs_share:,.0f}")

                if o.get("cs_memo"):
                    st.info(f"📝 CS 메모: {o['cs_memo']}")

                if o.get("field_report"):
                    fr = o["field_report"]
                    st.warning(f"🚨 현장 보고: {fr.get('description','—')} | {fr.get('reported_at','—')}")
                    cs_response = st.text_input("CS 대응 메모", value=fr.get("cs_response",""), key=f"cs_resp_{o['id']}")
                    if st.button("💾 저장", key=f"cs_resp_save_{o['id']}"):
                        updated_fr = dict(fr)
                        updated_fr["cs_response"] = cs_response
                        update_order(o["id"], {"field_report": updated_fr})
                        st.success("대응 메모 저장됨")
                        st.rerun()

# ──────────────── Tab 3: 오늘 접수 현황 ────────────────
with tab3:
    st.subheader("📊 오늘 접수 현황")
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_orders = [o for o in orders if o.get("scheduled_time", "").startswith(today_str)]

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📋 오늘 예약", f"{len(today_orders)}건")
    with col2:
        demo_cnt = len([o for o in today_orders if o.get("work_type") == "철거"])
        st.metric("🔨 철거", f"{demo_cnt}건")
    with col3:
        pending = len([o for o in today_orders if o["status"] == "pending"])
        st.metric("⏳ 배차 대기", f"{pending}건",
                  delta="즉시 배차 필요" if pending > 0 else None,
                  delta_color="inverse" if pending > 0 else "normal")
    with col4:
        st.metric("🔄 진행중", f"{len([o for o in today_orders if o['status']=='in_progress'])}건")
    with col5:
        st.metric("✅ 완료", f"{len([o for o in today_orders if o['status']=='completed'])}건")

    # 철거 건 견적 대기
    demo_quote_pending = [
        o for o in orders
        if o.get("work_type") == "철거" and not o.get("manager_quote_confirmed")
        and o["status"] not in ("completed", "cancelled")
    ]
    if demo_quote_pending:
        st.error(f"🔨 철거 건 견적 미확정 {len(demo_quote_pending)}건 — 매니저 확정 필요!")
        for o in demo_quote_pending:
            asbestos_tag = " ☢️ 석면!" if o.get("has_asbestos") else ""
            st.warning(
                f"**주문 #{o['id']} {o['customer']}** | {o.get('demolition_scope','—')} "
                f"{o.get('demolition_area','—')}평{asbestos_tag} | CS기초 ₩{o['base_fee']:,}"
            )
        st.divider()

    field_reports = [o for o in orders if o.get("field_report") and not o["field_report"].get("cs_response")]
    if field_reports:
        st.error(f"🚨 현장 상황 보고 미처리 {len(field_reports)}건")
        for o in field_reports:
            fr = o["field_report"]
            st.warning(f"주문 #{o['id']} {o['customer']} — {fr.get('description','—')[:60]}")
        st.divider()

    st.subheader("📬 오늘 발송 알림 현황")
    from data.db import get_notifications
    notifs = get_notifications()
    today_notifs = [n for n in notifs if n.get("sent_at", "").startswith(today_str)]
    if not today_notifs:
        st.info("오늘 발송된 알림이 없습니다.")
    else:
        rows = []
        for n in reversed(today_notifs[-10:]):
            rows.append({
                "시각": n.get("sent_at", "—")[:16],
                "유형": n.get("type", "—"),
                "수신": n.get("customer", "—"),
                "발송주체": n.get("sender", "수동") or "수동",
                "내부알림": "✅" if n.get("is_internal") else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

show_legal_warning()
