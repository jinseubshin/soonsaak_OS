import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.tax_calc import calc_driver_settlement, TAX_TYPE_BUSINESS
from utils.schedule import (
    can_set_block, is_driver_blocked_at, get_driver_active_blocks,
    build_day_grid, get_current_driver_status, is_past_date,
    check_minimum_operation, count_weekly_fullday_count, get_monthly_block_count,
    ALLDAY_LEADTIME_H, PARTIAL_LEADTIME_H,
    MIN_FULLDAY_DAYS_PER_WEEK, FULLDAY_HOURS,
)
from data.db import add_schedule_block, remove_schedule_block, get_driver_schedules

from data.db import (get_drivers, get_orders, update_order, add_driver_log,
                     add_notification, get_driver_by_id, get_settings,
                     save_driver, get_all, add_satisfaction_survey,
                     add_journey_notification, mark_notification_sent,
                     get_driver_logs, get_phone_logs,
                     start_trip_tracking, update_trip_gps,
                     complete_trip_tracking, get_trip_data)
from utils.footer import show_legal_warning
from utils.masks import mask_phone
from utils.maps import geocode_address, estimate_travel, compute_eta, efficiency_label
from utils.rbac import render_role_selector, is_owner, is_manager, is_executor, is_cs, role_badge
from datetime import datetime
import json
import random
import uuid
from pathlib import Path
try:
    from streamlit_js_eval import get_geolocation as _get_geolocation
    _GEO_AVAILABLE = True
except ImportError:
    _GEO_AVAILABLE = False

st.set_page_config(page_title="기사 앱 — 순삭 OS", page_icon="📱", layout="wide")
st.title("📱 기사 앱")
st.caption("기사 선택 후 배차된 주문을 실시간으로 처리합니다")

render_role_selector()
st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")

ACCOUNT_WARNING = (
    "\n\n⚠️ 본사 공식 계좌 외 기사에게 직접 현금 지급 시 AS 및 보상이 불가합니다."
)

settings = get_settings()
DIRECT_THRESHOLD = settings.get("direct_team_threshold", 40)
FULL_COST = settings.get("direct_team_full_cost", 1500000)
HALF_COST = settings.get("direct_team_half_cost", 750000)

# CS 역할은 기사 앱 접근 불가
if is_cs():
    st.error("🚫 **CS 상담원 모드에서는 기사 앱에 접근할 수 없습니다.** 사이드바에서 역할을 변경하세요.")
    st.stop()

# ═══════════════════════════════════════════════════════════════
#  운영 정책 동의 게이트 — 세션 1회, 체크 전 메인 화면 진입 차단
# ═══════════════════════════════════════════════════════════════
_POLICY_KEY = "_driver_app_policy_agreed"

if not st.session_state.get(_POLICY_KEY, False):
    st.markdown(
        """
<div style="max-width:680px;margin:24px auto">
<div style="background:linear-gradient(135deg,#1a237e 0%,#283593 100%);
     border-radius:16px 16px 0 0;padding:20px 28px 16px">
  <h2 style="color:white;margin:0;font-size:22px">📋 순삭 기사 운영 정책 동의</h2>
  <p style="color:#c5cae9;margin:4px 0 0 0;font-size:13px">
    서비스 이용 전 아래 운영 정책을 반드시 확인하고 동의해 주세요.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── 정책 카드 1: 재판매 정책
    st.markdown(
        """
<div style="border:2px solid #3949ab;border-top:none;border-radius:0;
     background:#f8f9ff;padding:20px 28px">
  <h4 style="color:#1a237e;margin:0 0 10px 0">📦 제1조 — 수거 물품 재판매 정책</h4>
  <p style="margin:0 0 10px 0;line-height:1.7;font-size:15px;color:#222">
    수거 물품의 <b>재판매 수익은 기사님께 귀속</b>됩니다.<br>
    단, <span style="background:#fff3e0;padding:2px 6px;border-radius:4px;
    color:#e65100;font-weight:700">'당근마켓' 등 개인 간 거래 앱에 직접 판매하는 행위</span>는
    <b>순삭 브랜드 보호</b>를 위해 <b style="color:#c62828">엄격히 금지</b>합니다.
  </p>
  <div style="background:#fff8e1;border-left:4px solid #ffa000;border-radius:4px;
       padding:10px 14px;font-size:13px;color:#555">
    ✅ 허용: 공식 제휴 중고 채널, 사업자 등록 기반 개인 판매<br>
    ❌ 금지: 당근마켓, 번개장터, 중고나라 등 개인 간 거래 앱에서의 직접 판매
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── 정책 카드 2: 위반 시 제재
    st.markdown(
        """
<div style="border:2px solid #b71c1c;border-top:1px solid #e8eaf6;border-radius:0;
     background:#fff8f8;padding:20px 28px">
  <h4 style="color:#b71c1c;margin:0 0 10px 0">⚠️ 제2조 — 위반 시 제재 사항</h4>
  <p style="margin:0 0 10px 0;line-height:1.7;font-size:15px;color:#222">
    개인 간 거래 앱에서의 직접 판매로 인한 <b>고객 민원이 발생할 경우</b>,
    다음 제재가 즉각 적용됩니다.
  </p>
  <div style="background:#ffebee;border-radius:8px;padding:12px 16px">
    <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:8px">
      <span style="font-size:20px">🚫</span>
      <div>
        <b style="color:#c62828">즉각적인 배차 정지</b>
        <div style="font-size:13px;color:#555;margin-top:2px">민원 접수 즉시 AI 배차 시스템에서 자동 제외</div>
      </div>
    </div>
    <div style="display:flex;gap:12px;align-items:flex-start">
      <span style="font-size:20px">📄</span>
      <div>
        <b style="color:#c62828">계약 해지 사유 해당</b>
        <div style="font-size:13px;color:#555;margin-top:2px">근로 계약서 제12조(금지 행위)에 따른 즉시 해지 가능</div>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """<div style="border:2px solid #37474f;border-top:none;
        border-radius:0 0 16px 16px;background:#eceff1;padding:16px 28px 20px">
        <p style="color:#455a64;font-size:13px;margin:0 0 12px 0">
        아래 두 항목에 모두 체크하셔야 메인 화면으로 진입할 수 있습니다.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    _chk1 = st.checkbox(
        "✅ [재판매 정책 확인] 당근마켓 등 개인 간 거래 앱 직접 판매가 금지되며, "
        "수거 물품의 재판매 수익은 기사님께 귀속됨을 확인했습니다.",
        key="policy_chk1",
    )
    _chk2 = st.checkbox(
        "✅ [제재 사항 동의] 개인 간 거래로 인한 고객 민원 발생 시 즉각적인 배차 정지 및 "
        "계약 해지 사유가 됨을 인지하고 동의합니다.",
        key="policy_chk2",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    _btn_col1, _btn_col2 = st.columns([2, 3])
    with _btn_col1:
        _agree_btn = st.button(
            "✅ 동의하고 기사 앱 시작하기",
            type="primary",
            disabled=not (_chk1 and _chk2),
            use_container_width=True,
        )
    with _btn_col2:
        if not (_chk1 and _chk2):
            st.warning("⬆️ 두 항목 모두 체크해야 시작할 수 있습니다.")

    if _agree_btn and _chk1 and _chk2:
        st.session_state[_POLICY_KEY] = True
        st.rerun()

    st.stop()

# ── 동의 완료 배지 (선택적으로 표시)
st.markdown(
    "<div style='background:#e8f5e9;border-radius:6px;padding:6px 14px;"
    "font-size:12px;color:#2e7d32;display:inline-block;margin-bottom:8px'>"
    "✅ 운영 정책 동의 완료 (이번 세션)</div>",
    unsafe_allow_html=True,
)

drivers = get_drivers()
orders = get_orders()

# ── 무인 자동 지연 감지 (페이지 로딩 시 자동 실행)
try:
    from utils.auto_penalty import check_and_apply_delay_penalty
    _delay_settings = get_settings()
    _delayed = check_and_apply_delay_penalty(orders, _delay_settings)
    if _delayed:
        orders = get_orders()  # 페널티 적용 후 최신 상태 재로딩
except Exception:
    pass


def make_virtual_number(real_phone: str) -> str:
    """050 가상번호 시뮬레이션 — 실번호 기반 고정 매핑"""
    digits = "".join(c for c in real_phone if c.isdigit())
    if len(digits) >= 8:
        mid = digits[3:7]
        tail = digits[-4:]
    else:
        mid = "0000"
        tail = "0000"
    return f"050-{mid}-{tail}"


def log_virtual_call(order_id, driver_id, customer, virtual_num, real_num):
    add_driver_log({
        "order_id": order_id,
        "driver_id": driver_id,
        "event": "가상번호통화",
        "detail": {
            "virtual_number": virtual_num,
            "customer": customer,
            "call_started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    })


def dispatch_system_notification(order, driver_obj, notif_type, message, journey_field=None):
    """시스템 이름으로 알림톡 발송 + 여정 파이프라인 기록"""
    full_message = message + ACCOUNT_WARNING
    add_notification({
        "order_id": order["id"],
        "customer": order["customer"],
        "customer_phone": order["customer_phone"],
        "type": notif_type,
        "message": full_message,
        "sender": "순삭 본사 시스템",
    })
    if journey_field:
        add_journey_notification({
            "order_id": order["id"],
            "customer": order["customer"],
            "customer_phone": order["customer_phone"],
            "type": notif_type,
            "message": full_message,
        })
        mark_notification_sent(order["id"], journey_field)


# ─── Executor 모드: 본인 기사 프로필 한정 ───────────────
if is_executor():
    st.info(
        "🚗 **기사(Executor) 모드** — 본인의 배차 일정, 작업 보고, 개인 정산 명세서만 확인할 수 있습니다. "
        "다른 기사의 데이터는 표시되지 않습니다."
    )
    # Executor 본인 기사 설정 (최초 1회 선택 후 고정)
    if "executor_driver_name" not in st.session_state:
        st.warning("📋 처음 사용 시 본인 기사 프로필을 선택하세요.")
        executor_pick = st.selectbox(
            "본인 기사 프로필 선택",
            options=[d["name"] for d in drivers],
            key="executor_initial_pick"
        )
        if st.button("✅ 내 프로필로 설정", type="primary"):
            st.session_state["executor_driver_name"] = executor_pick
            st.rerun()
        st.stop()
    else:
        exec_name = st.session_state["executor_driver_name"]
        st.success(f"👤 본인 프로필: **{exec_name}** | [변경하려면 사이드바에서 역할 재선택 후 다시 설정하세요]")
        if st.button("🔄 프로필 재선택", key="executor_reset"):
            del st.session_state["executor_driver_name"]
            st.rerun()
        selected_driver_name = exec_name
else:
    selected_driver_name = st.selectbox(
        "👨‍✈️ 기사 선택",
        options=[d["name"] for d in drivers],
        key="driver_select"
    )

driver = next((d for d in drivers if d["name"] == selected_driver_name), None)

if not driver:
    st.warning("기사를 선택해주세요.")
    st.stop()

# ─── 신규 기사 온보딩 가이드 (등록 후 7일 이내)
from datetime import datetime as _dtcheck
_joined_str = driver.get("joined_at")
_is_new_driver = False
if _joined_str:
    try:
        _joined_dt = _dtcheck.strptime(_joined_str[:19], "%Y-%m-%d %H:%M:%S")
        _days_since = (_dtcheck.now() - _joined_dt).days
        _is_new_driver = _days_since <= 7
    except Exception:
        _is_new_driver = False

if _is_new_driver:
    with st.container():
        st.markdown(
            f"""
<div style="background:linear-gradient(135deg,#fff7e6 0%,#ffe4b5 100%);
     border-left:5px solid #ff8c00;border-radius:10px;padding:16px 20px;margin-bottom:12px">
<h4 style="margin:0 0 8px 0;color:#cc6600">🎉 환영합니다, {driver['name']} 기사님! — 신규 온보딩 가이드</h4>
<p style="margin:0;color:#7a4500;font-size:0.93em">
등록 후 <b>{_days_since}일</b> 경과 | 아래 가이드를 꼭 확인해 주세요 (7일간 상시 표시)
</p>
</div>
""",
            unsafe_allow_html=True,
        )
        _ob_col1, _ob_col2, _ob_col3 = st.columns(3)
        with _ob_col1:
            with st.expander("📸 작업 전/후 사진 샘플 보기", expanded=False):
                st.markdown(
                    "**수거 작업 사진 기준:**\n"
                    "- 🔵 **작업 전**: 폐기물 전체가 보이는 각도 (정면+측면)\n"
                    "- 🟢 **작업 후**: 완전히 빈 자리 + 주변 청결 상태\n"
                    "- 📐 필수: 배경 건물/주소판이 함께 나올 것\n\n"
                    "**철거 작업 사진 기준:**\n"
                    "- 🔵 **Before**: 철거 대상 전체 구조물\n"
                    "- 🟡 **중간**: 해체 진행 중 (위험 부위 포함)\n"
                    "- 🟢 **After**: 철거 완료 + 잔재물 처리 확인\n\n"
                    "> ⚠️ 사진 미업로드 시 해당 건 수당 차감 + 다음 배차에서 자동 제외됩니다."
                )
        with _ob_col2:
            with st.expander("🗣️ 고객 응대 스크립트", expanded=False):
                st.markdown(
                    "**도착 전 연락 (필수):**\n"
                    "> '안녕하세요, 순삭에서 수거/철거 작업으로 방문하는 기사 [이름]입니다. "
                    "약 15분 후 도착 예정입니다. 현장 확인 부탁드립니다.'\n\n"
                    "**작업 완료 후:**\n"
                    "> '작업 완료했습니다. 확인 부탁드립니다. 혹시 불편하신 점이 있으시면 말씀해 주세요.'\n\n"
                    "**불만 고객 응대:**\n"
                    "> '불편을 드려 정말 죄송합니다. 즉시 본사에 보고하겠습니다.' — 현장에서 절대 단독 처리 금지."
                )
        with _ob_col3:
            with st.expander("📋 첫 달 체크리스트", expanded=False):
                st.markdown(
                    "- [ ] 작업 전/후 사진 업로드 습관화\n"
                    "- [ ] 배차 알림 카카오톡 수신 설정\n"
                    "- [ ] 스케줄 OFF 등록 방법 숙지 (기사 앱 → 스케줄 탭)\n"
                    "- [ ] 정산 세무 유형 확인 (매니저 확인 필수)\n"
                    "- [ ] 고객 응대 스크립트 숙지\n"
                    "- [ ] 월 기준 건수 확인: 직영 40건 이상 시 운영비 전액\n"
                    f"- [ ] 전문분야: **{driver.get('specialty', '공통')}** 주문 우선 배차됩니다\n"
                )
        st.divider()

# ─── 기사 현황 배너
monthly = driver.get("monthly_jobs", 0)
is_direct = driver.get("driver_type", "직영") == "직영"
remaining = DIRECT_THRESHOLD - monthly

col_info1, col_info2, col_info3, col_info4 = st.columns(4)
with col_info1:
    st.metric("⭐ 평점", driver["rating"])
with col_info2:
    st.metric("🔢 이달 완료", f"{monthly}건", delta=f"기준 {DIRECT_THRESHOLD}건",
              delta_color="normal" if monthly >= DIRECT_THRESHOLD else "inverse")
with col_info3:
    sat = driver.get("avg_satisfaction")
    st.metric("😊 고객만족도", f"{sat}점" if sat else "미집계")
with col_info4:
    st.metric("📦수거 / 🔨철거", f"{driver.get('collection_jobs', 0)} / {driver.get('demolition_jobs', 0)}")

if is_direct and monthly < DIRECT_THRESHOLD:
    st.error(
        f"⚠️ **운영비 경고!** 이달 {monthly}건 완료 — {DIRECT_THRESHOLD}건 미달 시 "
        f"조건부 운영비 **₩{HALF_COST:,} (50%)** 적용됩니다. "
        f"(전액 기준 ₩{FULL_COST:,} / 잔여 **{remaining}건** 필요)"
    )
elif is_direct:
    st.success(f"✅ 이달 {monthly}건 달성 — 조건부 운영비 **전액 (₩{FULL_COST:,})** 지급 대상입니다.")

# ─── 월간 목표 달성률 프로그레스 바 ──────────────────────────────────────────
if is_direct:
    import calendar as _cal
    from datetime import date as _dtoday
    _today_d = _dtoday.today()
    _days_in_month = _cal.monthrange(_today_d.year, _today_d.month)[1]
    _days_remaining = _days_in_month - _today_d.day

    _progress_ratio = min(monthly / DIRECT_THRESHOLD, 1.0)
    _attain_pct = round(_progress_ratio * 100, 1)
    _left = max(0, DIRECT_THRESHOLD - monthly)

    # 예상 수당 계산
    if monthly >= DIRECT_THRESHOLD:
        _expected_cost = FULL_COST
        _cost_label = f"✅ 전액 수당 **₩{FULL_COST:,}** 지급 확정"
        _bar_color = "#22c55e"
    else:
        # 이번 달 남은 일수에서 달성 가능성 추정
        _pace_per_day = monthly / max(_today_d.day, 1)
        _projected = monthly + round(_pace_per_day * _days_remaining)
        _expected_cost = FULL_COST if _projected >= DIRECT_THRESHOLD else HALF_COST
        _cost_label = (
            f"🟡 현재 페이스 유지 시 **{_projected}건** 예상 → "
            f"{'전액 ₩{:,}'.format(FULL_COST) if _projected >= DIRECT_THRESHOLD else '50% ₩{:,}'.format(HALF_COST)} 예상"
        )
        _bar_color = "#f59e0b" if _attain_pct >= 60 else "#ef4444"

    st.markdown(f"#### 🎯 월간 목표 달성률 — {monthly}건 / {DIRECT_THRESHOLD}건 목표")
    st.progress(_progress_ratio)
    _prog_col1, _prog_col2, _prog_col3 = st.columns(3)
    with _prog_col1:
        st.metric("달성률", f"{_attain_pct}%",
                  delta=f"{'목표 달성!' if monthly >= DIRECT_THRESHOLD else f'{_left}건 부족'}",
                  delta_color="normal" if monthly >= DIRECT_THRESHOLD else "inverse")
    with _prog_col2:
        st.metric("남은 건수", f"{_left}건", delta=f"잔여 {_days_remaining}일")
    with _prog_col3:
        _full_per_day = DIRECT_THRESHOLD / _days_in_month
        _needed_per_day = _left / max(_days_remaining, 1) if _left > 0 else 0
        st.metric("일 필요 건수", f"{_needed_per_day:.1f}건/일",
                  delta=f"평균 기준 {_full_per_day:.1f}건/일")
    st.caption(_cost_label)

    # 월말 긴급 경고
    if _days_remaining <= 10 and monthly < DIRECT_THRESHOLD:
        st.warning(
            f"⏰ **월말 D-{_days_remaining}!** 스케줄을 최대한 열어두면 "
            f"AI 배차 시스템이 우선 배차합니다. (마지막 {10 if _days_remaining <= 10 else 5}일 긴급 상향 활성)"
        )

st.divider()

# ─── 개인 정산 명세서 (Executor: 항상 표시 / Manager·Owner: 접이식) ───
with st.expander(
    "💳 내 월간 정산 명세서 (PDF 다운로드)",
    expanded=is_executor()
):
    st.caption("본인의 이달 완료 주문 기준 정산 내역을 자동 생성합니다.")
    now_pdf = datetime.now()
    month_pdf_label = now_pdf.strftime("%Y년 %m월")
    driver_ratio = settings.get("driver_ratio", 0.7)

    my_orders = [o for o in orders if o.get("driver_id") == driver["id"] and o["status"] == "completed"]
    my_total_rev = sum(o.get("base_fee", 0) + (o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0) for o in my_orders)
    my_pay = my_total_rev * driver_ratio
    my_allowances = sum(max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0)) for o in my_orders)

    # ── 세무 유형별 계산
    _my_tax = calc_driver_settlement(my_pay, driver)
    my_withholding = _my_tax["withholding"]
    my_net = _my_tax["net_pay"] + my_allowances
    _is_biz = _my_tax["tax_type"] == TAX_TYPE_BUSINESS

    # ── 세무 유형 안내 배너
    if _is_biz:
        st.info(
            f"🏢 **사업자(부가세 포함)** | "
            f"공급가 ₩{int(_my_tax['supply_amount']):,} + 부가세 ₩{int(_my_tax['vat']):,} "
            f"= 총 ₩{int(my_pay):,} 고정 지급\n\n"
            "📌 매달 정산 확정 후 **세금계산서를 발행**해 주세요. 미발행 시 지급이 지연될 수 있습니다."
        )
    else:
        st.warning(
            f"👤 **개인(3.3%)** — 3.3% 공제 후 지급 예정입니다.\n\n"
            f"원천세 ₩{int(my_withholding):,} 자동 공제 후 실지급 ₩{int(my_pay - my_withholding):,}"
        )

    # 요약 지표
    pdf_cols = st.columns(4)
    with pdf_cols[0]:
        st.metric("이달 완료", f"{len(my_orders)}건")
    with pdf_cols[1]:
        st.metric("총 매출 기여", f"₩{my_total_rev:,}")
    with pdf_cols[2]:
        st.metric(f"지급액({int(driver_ratio*100)}%)", f"₩{my_pay:,.0f}")
    with pdf_cols[3]:
        if _is_biz:
            st.metric("총 지급액 (부가세 포함)", f"₩{int(_my_tax['net_pay']):,}")
        else:
            st.metric("원천세 공제 후 실지급", f"₩{int(my_pay - my_withholding):,.0f}")

    # ── 세무 상세 계산 내역 (UI)
    st.markdown("**세무 계산 내역**")
    st.code(_my_tax["breakdown_text"] + (f" + 건당수당 ₩{my_allowances:,}" if my_allowances else ""), language=None)

    if st.button("📥 개인 정산 명세서 생성 (HTML→인쇄→PDF)", type="primary", key="personal_pdf_btn"):
        order_rows_html = ""
        for o in my_orders:
            fee = o.get("base_fee", 0) + (o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0)
            d_pay = fee * driver_ratio
            _o_tax = calc_driver_settlement(d_pay, driver)
            allow = max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0))
            if _is_biz:
                tax_col = f"공급가 ₩{int(_o_tax['supply_amount']):,} / VAT ₩{int(_o_tax['vat']):,}"
                net_col = f"₩{int(_o_tax['net_pay']):,}"
            else:
                tax_col = f"-₩{int(_o_tax['withholding']):,}"
                net_col = f"₩{int(_o_tax['net_pay']):,}"
            order_rows_html += f"""
            <tr>
              <td>#{o['id']}</td>
              <td>{o.get('scheduled_time','—')[:10]}</td>
              <td>{o.get('work_type','—')}</td>
              <td style='text-align:right'>₩{fee:,}</td>
              <td style='text-align:right'>₩{d_pay:,.0f}</td>
              <td style='text-align:right;color:#c62828'>{tax_col}</td>
              <td style='text-align:right;color:#1b5e20'>{net_col}</td>
              <td style='text-align:right;color:#1565c0'>₩{allow:,.0f}</td>
            </tr>"""

        # 세무 유형별 요약 블록
        if _is_biz:
            summary_tax_block = f"""
  <p>💼 정산 유형: <b>사업자(부가세 포함)</b></p>
  <p>📋 공급가액: <b>₩{int(_my_tax['supply_amount']):,}</b></p>
  <p style="color:#1565c0">💧 부가세(10%): <b>₩{int(_my_tax['vat']):,}</b></p>
  <p class="net-pay">💵 총 지급액 (고정): ₩{int(my_pay):,}</p>
  <p style="font-size:13px;color:#888">※ 추가 부가세 없음 — 총 지급 = Base 고정</p>"""
            tax_notice_block = """
<div class="tax-note">
  📌 <b>사업자 기사 안내</b>: 매달 정산 확정 후 반드시 세금계산서를 발행해 주세요.<br>
  미발행 시 지급이 지연될 수 있습니다. (부가가치세법 제32조)
</div>"""
        else:
            summary_tax_block = f"""
  <p>💼 정산 유형: <b>개인(3.3%)</b></p>
  <p style="color:#c62828">📋 원천징수세 (소득세 3% + 지방소득세 0.3%): <b>-₩{int(my_withholding):,}</b></p>
  <p class="net-pay">💵 최종 실지급 예상: ₩{int(my_pay - my_withholding):,}</p>"""
            tax_notice_block = """
<div class="tax-note">
  👤 <b>개인 기사 안내</b>: 3.3% 공제 후 지급 예정입니다.<br>
  원천징수세(소득세 3% + 지방소득세 0.3%)는 본사에서 매달 세무서에 신고·납부합니다. (소득세법 제127조)
</div>"""

        biz_info_html = ""
        if _is_biz and driver.get("business_reg_no"):
            biz_info_html = f"""
<p style="font-size:13px;color:#555">
  사업자등록번호: {driver.get('business_reg_no','—')} |
  업태: {driver.get('business_type','—')} |
  종목: {driver.get('business_category','—')}
</p>"""

        personal_html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>{driver['name']} — {month_pdf_label} 개인 정산 명세서</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; margin: 30px; color: #222; }}
  h1 {{ color: #2e7d32; border-bottom: 3px solid #2e7d32; padding-bottom: 8px; font-size: 22px; }}
  h2 {{ color: #388e3c; font-size: 16px; margin-top: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px; }}
  th {{ background: #2e7d32; color: white; padding: 8px; text-align: center; }}
  td {{ border: 1px solid #ccc; padding: 6px 8px; }}
  tr:nth-child(even) {{ background: #f1f8e9; }}
  .summary-box {{ background: #e8f5e9; border-left: 5px solid #2e7d32; padding: 12px 16px;
                  margin: 16px 0; border-radius: 4px; }}
  .summary-box p {{ margin: 4px 0; font-size: 14px; }}
  .net-pay {{ font-size: 22px; font-weight: bold; color: #1b5e20; }}
  .footer {{ margin-top: 28px; font-size: 11px; color: #888; border-top: 1px solid #ddd;
             padding-top: 8px; }}
  .tax-note {{ background: #fff8e1; padding: 8px 12px; border-left: 4px solid #f9a825;
               margin: 12px 0; font-size: 12px; }}
  @media print {{ body {{ margin: 10px; }} }}
</style></head><body>
<h1>💳 {driver['name']} 기사 — {month_pdf_label} 개인 정산 명세서</h1>
<p style="color:#555">생성일시: {now_pdf.strftime('%Y-%m-%d %H:%M')} | 유형: {driver.get('driver_type','—')} | 평점: ⭐{driver.get('rating','—')}</p>
{biz_info_html}

<div class="summary-box">
  <p>📦 이달 완료 건수: <b>{len(my_orders)}건</b></p>
  <p>💰 총 매출 기여: <b>₩{my_total_rev:,}</b></p>
  <p>🤝 지급액 ({int(driver_ratio*100)}%): <b>₩{my_pay:,.0f}</b></p>
  <p>🏦 건당수당 합계: <b>₩{my_allowances:,.0f}</b></p>
  {summary_tax_block}
</div>
{tax_notice_block}

<h2>📋 주문별 상세 내역</h2>
<table>
  <tr>
    <th>주문#</th><th>작업일</th><th>유형</th>
    <th>매출금액</th><th>지급액(70%)</th><th>세무공제</th><th>실지급</th><th>건당수당</th>
  </tr>
  {order_rows_html}
</table>

<p style="margin-top:16px;font-size:13px">✅ 총 {len(my_orders)}건 | 최종 실지급(수당 포함): <b>₩{int(my_net):,.0f}</b></p>

<div class="footer">
  본 명세서는 순삭 OS에서 자동 생성되었습니다. 최종 지급액은 본사 확인 후 결정됩니다.<br>
  문의: 순삭 본사 정산팀
</div>
</body></html>"""

        st.download_button(
            label="⬇️ 개인 명세서 다운로드 (Ctrl+P → PDF 저장)",
            data=personal_html.encode("utf-8"),
            file_name=f"순삭OS_{driver['name']}_{month_pdf_label}_개인정산명세서.html",
            mime="text/html",
            key="personal_pdf_download"
        )
        st.info("📌 다운로드 후 브라우저에서 열고 **Ctrl+P** → '대상: PDF로 저장' 선택하세요.")

st.divider()

# ─── 내 스케줄 관리 ──────────────────────────────────────────
with st.expander("📅 내 스케줄 관리 — 날짜·시간별 업무 가능 여부 설정", expanded=is_executor()):
    st.caption(
        f"• **전일 휴무** 는 최소 {ALLDAY_LEADTIME_H}시간 전까지 / "
        f"**부분 시간 차단** 은 최소 {PARTIAL_LEADTIME_H}시간 전까지 설정 가능합니다.\n"
        "• 이미 배차된 슬롯은 수정 불가 — 긴급 휴무는 담당 매니저에게 문의하세요."
    )

    _all_schedules_now = get_driver_schedules()
    _driver_id = driver["id"]
    _role_str = "executor" if is_executor() else ("manager" if is_manager() else "owner")

    sc_col1, sc_col2 = st.columns([1, 2])

    with sc_col1:
        st.markdown("**📆 날짜 선택**")
        from datetime import date, timedelta as _td
        _today = date.today()
        _target_date = st.date_input(
            "대상 날짜",
            value=_today,
            min_value=_today,
            max_value=_today + _td(days=30),
            key=f"sched_date_{driver['id']}",
            label_visibility="collapsed",
        )
        _date_str = _target_date.strftime("%Y-%m-%d")

        st.markdown("**⏰ 차단 유형**")
        _block_type = st.radio(
            "차단 유형",
            ["🌙 전일 휴무", "⏳ 부분 시간 차단"],
            key=f"sched_type_{driver['id']}",
            label_visibility="collapsed",
        )
        _is_all_day = "전일" in _block_type

        _start_h, _end_h = None, None
        if not _is_all_day:
            hour_range = st.slider(
                "차단 시간대 (시간)",
                min_value=6, max_value=22, value=(10, 14),
                key=f"sched_hours_{driver['id']}",
            )
            _start_h, _end_h = hour_range

        _reason = st.text_input(
            "휴무 사유 (선택)",
            placeholder="예: 병원 방문, 개인 사정",
            key=f"sched_reason_{driver['id']}",
        )

        if st.button("📵 차단 등록", type="primary", key=f"sched_add_{driver['id']}"):
            # Lead Time 검증
            _ok, _msg = can_set_block(_date_str, _is_all_day, _start_h)
            if not _ok:
                st.error(_msg)
            else:
                # 최소 가동 의무 검증 (주당 5일 풀타임)
                _op_ok, _op_msg = check_minimum_operation(
                    driver, _all_schedules_now, _date_str, _is_all_day, _start_h, _end_h
                )
                if not _op_ok:
                    st.error(_op_msg)
                else:
                    # 배정된 주문과 겹치는지 확인
                    _conflict_orders = []
                    for _o in orders:
                        if _o.get("driver_id") != _driver_id:
                            continue
                        if _o.get("status") in ("cancelled", "completed"):
                            continue
                        _osched = _o.get("scheduled_time", "")
                        if not _osched.startswith(_date_str):
                            continue
                        try:
                            _oh = int(_osched[11:13])
                        except Exception:
                            continue
                        if _is_all_day or (_start_h is not None and _start_h <= _oh <= _end_h):
                            _conflict_orders.append(_o)

                    if _conflict_orders:
                        st.error(
                            f"🚫 **차단 불가** — 해당 시간대에 배정된 주문이 있습니다: "
                            f"{', '.join('#'+str(o['id']) for o in _conflict_orders)}\n\n"
                            "배정된 주문이 있는 슬롯은 수정 권한이 없습니다. 담당 매니저에게 문의하세요."
                        )
                    else:
                        add_schedule_block({
                            "driver_id": _driver_id,
                            "date": _date_str,
                            "is_all_day": _is_all_day,
                            "start_hour": _start_h,
                            "end_hour": _end_h,
                            "reason": _reason,
                        }, role=_role_str)
                        st.success(
                            f"✅ {'전일 휴무' if _is_all_day else f'{_start_h}시~{_end_h}시 차단'} 등록 완료! "
                            f"({_date_str})"
                        )
                        st.rerun()

    with sc_col2:
        st.markdown(f"**📊 {_date_str} 시간대 현황**")
        _grid = build_day_grid(_all_schedules_now, _driver_id, _date_str, orders)
        _grid_html = "<div style='display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px'>"
        for _slot in _grid:
            _h = _slot["hour"]
            if _slot["has_order"]:
                _bg = "#1565c0"; _fc = "white"; _label = "📦 배차"
            elif _slot["blocked"]:
                _bg = "#c62828"; _fc = "white"; _label = "🔴 Off"
            else:
                _bg = "#e8f5e9"; _fc = "#1b5e20"; _label = "🟢 On"
            _grid_html += (
                f"<div style='background:{_bg};color:{_fc};padding:6px 10px;"
                f"border-radius:8px;font-size:13px;min-width:70px;text-align:center'>"
                f"<b>{_h:02d}:00</b><br>{_label}</div>"
            )
        _grid_html += "</div>"
        st.markdown(_grid_html, unsafe_allow_html=True)
        st.caption("🔵 배차됨 = 차단 불가 | 🔴 Off = 차단 중 | 🟢 On = 영업 중")

        st.markdown("**📋 등록된 차단 목록**")
        _active_blocks = get_driver_active_blocks(_all_schedules_now, _driver_id)
        if not _active_blocks:
            st.info("등록된 휴무가 없습니다.")
        else:
            for _b in sorted(_active_blocks, key=lambda x: (x.get("date",""), x.get("start_hour", 0))):
                _bcol1, _bcol2 = st.columns([4, 1])
                with _bcol1:
                    if _b.get("is_all_day"):
                        _btype = "🌙 전일 휴무"
                    else:
                        _btype = f"⏳ {_b.get('start_hour',0):02d}:00 ~ {_b.get('end_hour',0):02d}:00"
                    _breason = f" — {_b['reason']}" if _b.get("reason") else ""
                    st.markdown(f"**{_b.get('date')}** {_btype}{_breason}")
                    st.caption(f"등록: {_b.get('created_at','—')} ({_b.get('created_by_role','—')})")
                with _bcol2:
                    # 배정된 주문이 있는 차단은 삭제 불가
                    _has_conflict = any(
                        o.get("driver_id") == _driver_id
                        and o.get("status") not in ("cancelled","completed")
                        and o.get("scheduled_time","").startswith(_b.get("date",""))
                        for o in orders
                    )
                    if _has_conflict:
                        st.caption("🔒 배차 중\n삭제 불가")
                    else:
                        if st.button("🗑️ 삭제", key=f"del_sched_{_b['id']}", help="이 차단 해제"):
                            remove_schedule_block(_b["id"], role=_role_str)
                            st.success("차단 해제 완료")
                            st.rerun()

st.divider()

driver_orders = [o for o in orders if o.get("driver_id") == driver["id"] and o["status"] not in ("completed", "cancelled")]
all_driver_orders = [o for o in orders if o.get("driver_id") == driver["id"]]

if not driver_orders:
    if all_driver_orders:
        completed = [o for o in all_driver_orders if o["status"] == "completed"]
        st.success(f"✅ 오늘 완료한 주문: **{len(completed)}건**")
    st.info("현재 배차된 진행 중인 주문이 없습니다.")
else:
    for order in driver_orders:
        st.divider()
        virtual_num = make_virtual_number(order.get("customer_phone", "010-0000-0000"))
        masked_phone = mask_phone(order.get("customer_phone", ""), "manager")

        col1, col2 = st.columns([2, 1])
        with col1:
            wtype = order.get("work_type", "수거")
            icon = "🔨" if wtype == "철거" else "📦"
            st.markdown(f"### {icon} 주문 #{order['id']} — {order['customer']}")
            st.markdown(f"📍 **출발:** {order['pickup']}")
            st.markdown(f"🏁 **도착:** {order['destination']}")
            st.markdown(f"⏰ **예약:** {order['scheduled_time']}")
            st.markdown(f"💰 **기본요금:** ₩{order['base_fee']:,}")
            st.markdown(f"🔧 **작업 유형:** {'🔨 철거' if wtype == '철거' else '📦 수거'}")

            # ─── 번호 마스킹 + 가상번호 전화 버튼
            st.divider()
            phone_col1, phone_col2 = st.columns([2, 1])
            with phone_col1:
                st.markdown(
                    f"📞 **고객 연락처:** `{masked_phone}`"
                    f"<span style='font-size:11px;color:#888;margin-left:8px'>"
                    f"(가상번호로만 연결됩니다)</span>",
                    unsafe_allow_html=True
                )
            with phone_col2:
                call_key = f"call_{order['id']}"
                if st.button("📞 전화하기 (가상번호)", key=call_key, type="primary"):
                    st.session_state[call_key] = True

            if st.session_state.get(call_key):
                st.info(
                    f"🔗 **가상번호 연결 중:** `{virtual_num}` → 고객 ({masked_phone})\n\n"
                    f"📌 이 통화는 본사 법인 명의로 기록되며, 개인 연락처로 직접 전화하는 것은 계약 위반입니다."
                )
                if st.button("📝 통화 종료 & 기록 저장", key=f"call_end_{order['id']}"):
                    log_virtual_call(order["id"], driver["id"], order["customer"],
                                     virtual_num, order.get("customer_phone", ""))
                    st.session_state[call_key] = False
                    st.success(f"✅ 통화 기록 저장됨 — {datetime.now().strftime('%H:%M:%S')}")
                    st.rerun()

        with col2:
            status_display = {
                "dispatched": "📍 배차완료",
                "in_progress": "🔄 진행중",
                "completed": "✅ 완료",
            }
            st.markdown(f"**현재 상태:** {status_display.get(order['status'], order['status'])}")

            for label, val in [
                ("작업 전", order.get("photo_before")),
                ("작업 후", order.get("photo_after")),
                ("정리 정돈", order.get("photo_cleanup")),
            ]:
                if val:
                    st.success(f"📷 {label} ✅")
                else:
                    st.warning(f"{'🔴' if label != '정리 정돈' else '🟡'} {label} 미업로드")

            # AI 사진 검증 결과 표시 (철거 건만)
            if order.get("work_type") == "철거" and order.get("photo_match_score") is not None:
                from utils.ai_vision import score_badge, MATCH_ALERT_THRESHOLD
                ai_score = order["photo_match_score"]
                st.markdown("---")
                st.markdown(f"**🤖 AI 검증 결과:**")
                st.markdown(score_badge(ai_score), unsafe_allow_html=True)
                if order.get("photo_match_reasoning"):
                    st.caption(f"AI 판단: {order['photo_match_reasoning']}")

        # ─── 사진 업로드 섹션 (전/후/정리 3장)
        all_photos_ok = order.get("photo_before") and order.get("photo_after") and order.get("photo_cleanup")
        with st.expander(
            "📷 작업 사진 업로드 (완료 처리 전 필수 — 전/후/정리 3장)",
            expanded=not all_photos_ok
        ):
            _ph_help_col1, _ph_help_col2 = st.columns([6, 1])
            with _ph_help_col1:
                st.warning("⚠️ 작업 전·후 및 주변 정리 사진을 모두 업로드해야 완료 처리가 가능합니다.")
            with _ph_help_col2:
                with st.expander("❓"):
                    st.markdown(
                        "**✅ 잘 찍은 사진 기준:**\n\n"
                        "📸 **작업 전 사진**\n"
                        "- 폐기물 전체가 보이도록\n"
                        "- 밝게, 흔들림 없이\n"
                        "- 건물 입구/주소판 포함\n\n"
                        "📸 **작업 후 사진**\n"
                        "- 같은 각도로 재촬영\n"
                        "- 빈 공간이 명확히 보임\n\n"
                        "📸 **정리 정돈 사진**\n"
                        "- 주변 바닥·벽 깨끗한 상태\n\n"
                        "> 사진이 기준 미달이면 AI가 자동 감지해 다음 배차에서 제외됩니다."
                    )
            up_col1, up_col2, up_col3 = st.columns(3)
            photo_fields = [
                (up_col1, "작업 전 사진", "before", f"before_{order['id']}", f"save_before_{order['id']}", "작업전사진업로드"),
                (up_col2, "작업 후 사진", "after", f"after_{order['id']}", f"save_after_{order['id']}", "작업후사진업로드"),
                (up_col3, "정리 정돈 사진", "cleanup", f"cleanup_{order['id']}", f"save_cleanup_{order['id']}", "정리정돈사진업로드"),
            ]
            for col, label, field_key, uploader_key, btn_key, log_event in photo_fields:
                db_field = f"photo_{field_key}"
                with col:
                    st.markdown(f"**{label}**")
                    uploaded = st.file_uploader(label, type=["jpg", "jpeg", "png"],
                                                key=uploader_key, label_visibility="collapsed")
                    if uploaded:
                        st.image(uploaded, caption=label, use_container_width=True)
                        if st.button(f"✅ {label} 저장", key=btn_key):
                            now_upload = datetime.now()
                            _photo_bytes = uploaded.getvalue()
                            _photo_ext = uploaded.name.rsplit(".", 1)[-1].lower()
                            extra_fields = {db_field: uploaded.name}

                            # ── 작업 전 사진 업로드 = 현장 도착 자동 기록 (지연 패널티 판단 기준)
                            if field_key == "before":
                                extra_fields["photo_before_at"] = now_upload.strftime("%Y-%m-%d %H:%M:%S")
                                dep_str = order.get("departed_at")
                                if dep_str:
                                    try:
                                        dep_dt = datetime.strptime(dep_str, "%Y-%m-%d %H:%M:%S")
                                        actual_min = max(0, int((now_upload - dep_dt).total_seconds() / 60))
                                        is_late = actual_min >= 30
                                        expected_min = order.get("expected_travel_min")
                                        extra_fields["actual_travel_min"] = actual_min
                                        extra_fields["departure_delay_minutes"] = actual_min
                                        extra_fields["delay_flag"] = is_late
                                        if not order.get("arrived_at"):
                                            extra_fields["arrived_at"] = now_upload.strftime("%Y-%m-%d %H:%M:%S")
                                        # ── 계약서 제9조: 30분 이상 지연 시 관리자 알림 자동 기록
                                        if is_late:
                                            mgr_delay_msg = (
                                                f"[순삭OS 지연패널티] ⚠️ 주문 #{order['id']} ({order['customer']}) — "
                                                f"기사 {driver['name']} | 출발~도착 실측 {actual_min}분 "
                                                f"(예상 {expected_min or '—'}분 / 기준 30분) | "
                                                f"작업전사진 업로드 {now_upload.strftime('%H:%M')} | "
                                                f"계약서 제9조 — 정산 시 수당 차감 대상 자동 분류됨"
                                            )
                                            dispatch_system_notification(
                                                order, driver,
                                                "지연패널티감지",
                                                mgr_delay_msg,
                                                journey_field=None,
                                            )
                                    except Exception:
                                        pass

                            # ── 완료 사진 (작업 후) → AI 검증용 파일 저장 + 검증 트리거
                            if field_key == "after":
                                from utils.ai_vision import save_photo, compare_photos
                                comp_path = save_photo(order["id"], "completion", _photo_bytes, _photo_ext)
                                extra_fields["completion_photo_path"] = comp_path
                                estimate_path = order.get("estimate_photo_path")
                                if order.get("work_type") == "철거" and estimate_path:
                                    with st.spinner("🤖 AI가 견적 사진과 완료 사진을 비교 중..."):
                                        result = compare_photos(estimate_path, comp_path, order)
                                    extra_fields["photo_match_score"] = result.get("score")
                                    extra_fields["photo_match_flagged"] = result.get("flagged", False)
                                    extra_fields["photo_match_reasoning"] = result.get("reasoning", "")
                                    extra_fields["photo_match_flags"] = result.get("flags", [])
                                    extra_fields["photo_match_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    score = result.get("score")
                                    if result.get("error"):
                                        st.warning(f"⚠️ AI 분석 일시 오류: {result['error']}")
                                    elif result.get("flagged"):
                                        st.error(
                                            f"🤖 AI 불일치 감지 — Match Score: **{score}점** | "
                                            f"대표님께 카카오 알림이 즉시 전송됩니다."
                                        )
                                        try:
                                            from utils.notifications import notify_photo_mismatch
                                            _notif_order = {**order, "_driver_name": driver.get("name", "—")}
                                            notify_photo_mismatch(
                                                order=_notif_order,
                                                score=score,
                                                reasoning=result.get("reasoning", ""),
                                                flags=result.get("flags", []),
                                            )
                                        except Exception:
                                            pass
                                        # ── 정산 즉시 Hold + 배차 우선순위 하향
                                        try:
                                            from utils.auto_penalty import apply_settlement_hold
                                            apply_settlement_hold(
                                                order_id=order["id"],
                                                score=score,
                                                reasoning=result.get("reasoning", ""),
                                            )
                                            st.error(
                                                "🔒 **정산 보류(Hold) 자동 처리** — "
                                                "AI 사진 불일치로 이 건의 정산이 즉시 보류됩니다. "
                                                "매니저 확인 후 해제 가능합니다."
                                            )
                                        except Exception:
                                            pass
                                    else:
                                        st.success(f"🤖 AI 검증 통과 — Match Score: **{score}점** ✅")

                            update_order(order["id"], extra_fields)
                            add_driver_log({"order_id": order["id"], "driver_id": driver["id"], "event": log_event,
                                            "detail": {"upload_at": datetime.now().strftime("%H:%M:%S")}})
                            st.success(f"{label} 저장됨")
                            st.rerun()
                    elif order.get(db_field):
                        before_at = order.get("photo_before_at") if field_key == "before" else None
                        suffix = f" ({before_at[11:16]} 업로드)" if before_at else ""
                        st.success(f"✅ 저장됨: {order[db_field]}{suffix}")

        # ─── 현장 상황 보고 (CS 접수 내용과 다를 경우)
        field_report = order.get("field_report")
        cs_items_str = ", ".join(order.get("cs_items") or [])

        if cs_items_str or order.get("cs_memo"):
            st.divider()
            st.markdown("**📋 CS 접수 내용 (현장 확인 기준)**")
            if cs_items_str:
                st.info(f"**상담 품목:** {cs_items_str}")
            if order.get("cs_memo"):
                st.caption(f"CS 메모: {order['cs_memo']}")

        if field_report:
            st.warning(
                f"🚨 **현장 상황 보고 접수됨** — {field_report.get('description','—')}\n\n"
                f"보고 시각: {field_report.get('reported_at','—')} | "
                f"CS 처리: {'완료' if field_report.get('cs_response') else '대기 중'}"
            )
        else:
            with st.expander(
                "🚨 현장 상황 보고 — CS 접수 내용과 현장이 다른 경우 클릭",
                expanded=False
            ):
                st.warning("현장 상황이 상담 내용과 다를 경우 반드시 보고해주세요. 임의 추가 요금 요구는 계약 위반입니다.")
                report_desc = st.text_area(
                    "현장 상황 설명 *",
                    placeholder="예: 냉장고가 2대였으나 상담 시 1대로 접수됨 / 엘리베이터 없어 계단 이동 필요",
                    key=f"report_desc_{order['id']}",
                    height=80,
                )
                report_photo = st.file_uploader(
                    "현장 증거 사진 (선택)",
                    type=["jpg", "jpeg", "png"],
                    key=f"report_photo_{order['id']}"
                )
                if st.button("🚨 현장 상황 보고 제출", key=f"submit_report_{order['id']}", type="primary"):
                    if not report_desc.strip():
                        st.error("상황 설명을 입력해주세요.")
                    else:
                        report_data = {
                            "description": report_desc,
                            "photo": report_photo.name if report_photo else None,
                            "reported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "driver_id": driver["id"],
                            "driver_name": driver["name"],
                            "cs_response": None,
                            "manager_reviewed": False,
                        }
                        update_order(order["id"], {"field_report": report_data})
                        add_driver_log({
                            "order_id": order["id"],
                            "driver_id": driver["id"],
                            "event": "현장상황보고",
                            "detail": {"description": report_desc},
                        })
                        dispatch_system_notification(
                            order, driver,
                            "현장상황보고",
                            f"[순삭 본사] 주문 #{order['id']} 현장 상황 보고가 접수되었습니다. "
                            f"CS 확인 후 처리됩니다. 임의로 추가 요금을 요구하지 마세요.",
                        )
                        st.success("✅ 현장 상황 보고가 제출되었습니다. CS 담당자가 확인합니다.")
                        st.rerun()

        # ─── 출발 현황 정보 표시
        dep_at = order.get("departed_at")
        arr_at = order.get("arrived_at")
        eta_str = order.get("eta")

        if dep_at or arr_at:
            status_track_cols = st.columns(5)
            with status_track_cols[0]:
                if dep_at:
                    st.markdown(
                        f"<div style='background:#e8f4fd;padding:8px;border-radius:8px;"
                        f"border-left:4px solid #2196f3'>"
                        f"🚗 <b>출발 시각</b><br>{dep_at[11:16]}</div>",
                        unsafe_allow_html=True
                    )
            with status_track_cols[1]:
                exp_min = order.get("expected_travel_min")
                dist_km = order.get("travel_dist_km")
                src = order.get("travel_source", "")
                if exp_min is not None:
                    src_badge = f"<span style='font-size:10px;color:#888'>({src})</span>"
                    st.markdown(
                        f"<div style='background:#fff8e1;padding:8px;border-radius:8px;"
                        f"border-left:4px solid #ffc107'>"
                        f"🗺️ <b>예상 이동</b><br>{exp_min}분 / {dist_km}km<br>{src_badge}</div>",
                        unsafe_allow_html=True
                    )
                elif eta_str:
                    st.markdown(
                        f"<div style='background:#fff8e1;padding:8px;border-radius:8px;"
                        f"border-left:4px solid #ffc107'>"
                        f"⏱️ <b>도착 예정</b><br>{eta_str}</div>",
                        unsafe_allow_html=True
                    )
            with status_track_cols[2]:
                if eta_str:
                    st.markdown(
                        f"<div style='background:#e3f2fd;padding:8px;border-radius:8px;"
                        f"border-left:4px solid #1976d2'>"
                        f"⏰ <b>도착 예정 시각</b><br>{eta_str}</div>",
                        unsafe_allow_html=True
                    )
            with status_track_cols[3]:
                if arr_at:
                    st.markdown(
                        f"<div style='background:#e8f5e9;padding:8px;border-radius:8px;"
                        f"border-left:4px solid #4caf50'>"
                        f"📍 <b>현장 도착</b><br>{arr_at[11:16]}</div>",
                        unsafe_allow_html=True
                    )
            with status_track_cols[4]:
                actual_min = order.get("actual_travel_min")
                exp_min2 = order.get("expected_travel_min")
                if actual_min is not None and exp_min2 is not None:
                    label, color = efficiency_label(exp_min2, actual_min)
                    st.markdown(
                        f"<div style='background:#f5f5f5;padding:8px;border-radius:8px;"
                        f"border-left:4px solid {color}'>"
                        f"📊 <b>이동 효율</b><br>{label}<br>"
                        f"<span style='font-size:11px'>예상 {exp_min2}분 → 실제 {actual_min}분</span></div>",
                        unsafe_allow_html=True
                    )
                elif actual_min is not None:
                    delay_min = order.get("departure_delay_minutes")
                    if delay_min is not None and delay_min >= 30:
                        st.markdown(
                            f"<div style='background:#ffebee;padding:8px;border-radius:8px;"
                            f"border-left:4px solid #f44336'>"
                            f"🔴 <b>지연</b><br>이동 {delay_min}분</div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"<div style='background:#e8f5e9;padding:8px;border-radius:8px;"
                            f"border-left:4px solid #4caf50'>"
                            f"🟢 <b>정상</b><br>이동 {delay_min}분</div>",
                            unsafe_allow_html=True
                        )

        # ─── 실시간 ETA 카운트다운 패널 (출발 후 & 미도착 상태)
        _dep_at = order.get("departed_at")
        _eta_str = order.get("eta")
        _arr_at = order.get("arrived_at")
        _photo_before_at = order.get("photo_before_at")
        if _dep_at and _eta_str and not (_arr_at or _photo_before_at):
            try:
                _now = datetime.now()
                # ETA는 "HH:MM" 포맷 → 오늘 날짜로 datetime 생성
                _eta_dt = datetime.strptime(
                    _dep_at[:10] + " " + _eta_str, "%Y-%m-%d %H:%M"
                )
                # 자정 넘으면 하루 추가
                if _eta_dt < datetime.strptime(_dep_at, "%Y-%m-%d %H:%M:%S"):
                    from datetime import timedelta as _td
                    _eta_dt += _td(days=1)
                _remain_sec = int((_eta_dt - _now).total_seconds())
                _remain_min = _remain_sec // 60
                _exp_min = order.get("expected_travel_min", 0) or 0

                if _remain_sec > 0:
                    # 아직 ETA 이전 → 정상 진행 중
                    _late_min = max(0, int((_now - datetime.strptime(_dep_at, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60) - _exp_min)
                    if _late_min >= 5:
                        # 예상보다 지연 중 → 경고
                        st.warning(
                            f"⚠️ **이동 중 지연 감지** — 출발 후 **{int((_now - datetime.strptime(_dep_at, '%Y-%m-%d %H:%M:%S')).total_seconds()/60)}분** 경과 | "
                            f"예상 {_exp_min}분 초과 **{_late_min}분 지연** | "
                            f"ETA {_eta_str} (자동 업데이트 필요)"
                        )
                    else:
                        st.info(
                            f"🚗 **이동 중** — 도착 예정 **{_eta_str}** | "
                            f"약 **{_remain_min}분 남음** | "
                            f"예상 이동 {_exp_min}분 기준 정상 진행 중"
                        )
                else:
                    # ETA 지났는데 도착 미기록 → 지연 가능성 경고
                    _overdue_min = abs(_remain_sec) // 60
                    if _overdue_min >= 30:
                        st.error(
                            f"🔴 **지연 패널티 주의!** ETA({_eta_str}) 초과 **{_overdue_min}분** — "
                            f"작업 전 사진 업로드 시 자동 지연 기록됩니다. "
                            f"계약서 제9조에 따라 수당 차감 대상이 될 수 있습니다."
                        )
                    else:
                        st.warning(
                            f"⏰ **도착 예정 시각 경과** — ETA {_eta_str} 기준 **{_overdue_min}분 초과** | "
                            f"아직 30분 미만이므로 패널티 없음. 도착 시 사진 업로드 바랍니다."
                        )
            except Exception:
                pass

        # ─── GPS 위치 확인 섹션 (배차완료 & 미출발 상태에서만 표시)
        gps_lat_runtime = None
        gps_lng_runtime = None
        gps_display_label = None

        if order["status"] == "dispatched" and not order.get("departed_at"):
            st.markdown("---")
            st.markdown("**📡 GPS 위치 확인 — 출발 전 위치를 먼저 확인해 주세요**")

            gps_cache_key = f"gps_cache_{order['id']}"
            gps_denied_key = f"gps_denied_{order['id']}"

            saved_gps = st.session_state.get(gps_cache_key)
            gps_denied = st.session_state.get(gps_denied_key, False)

            if not saved_gps and not gps_denied:
                if _GEO_AVAILABLE:
                    loc = _get_geolocation(key=f"geo_req_{order['id']}")
                    if loc and isinstance(loc, dict) and "coords" in loc:
                        c = loc["coords"]
                        saved_gps = {
                            "lat": c["latitude"],
                            "lng": c["longitude"],
                            "accuracy": c.get("accuracy", 0),
                            "ts": datetime.now().strftime("%H:%M:%S"),
                        }
                        st.session_state[gps_cache_key] = saved_gps
                    elif loc is not None and "error" in str(loc).lower():
                        st.session_state[gps_denied_key] = True
                        gps_denied = True
                else:
                    st.info("📦 GPS 패키지를 불러오는 중입니다. 잠시 후 다시 시도해 주세요.")

            if gps_denied:
                st.markdown(
                    "<div style='background:#fff3cd;border:2px solid #e65100;border-radius:10px;"
                    "padding:16px;margin:8px 0'>"
                    "<h4 style='color:#b71c1c;margin:0 0 8px 0'>🚫 위치 권한이 거부되었습니다</h4>"
                    "<p style='margin:4px 0;font-size:15px'>"
                    "<b>정확한 시간 안내와 정산을 위해 위치 권한 허용이 필수입니다.</b></p>"
                    "<p style='margin:4px 0;color:#555;font-size:13px'>"
                    "GPS 위치는 출발~도착 실측 시간 계산 및 지연 패널티 정산 근거에 사용됩니다.</p>"
                    "<p style='margin:8px 0 0 0;font-size:13px'>"
                    "📱 <b>해결 방법:</b> 브라우저 주소창 왼쪽 🔒 잠금 아이콘 → <b>위치</b> → "
                    "<b>허용</b> 선택 후 새로고침</p>"
                    "</div>",
                    unsafe_allow_html=True
                )
                gps_col1, gps_col2 = st.columns([1, 2])
                with gps_col1:
                    if st.button("🔄 위치 권한 재요청", key=f"retry_gps_{order['id']}", type="primary"):
                        st.session_state.pop(gps_denied_key, None)
                        st.session_state.pop(gps_cache_key, None)
                        st.rerun()
                with gps_col2:
                    st.caption("권한 허용 후 위 버튼을 눌러 재요청하세요")
                gps_lat_runtime = round(37.5665 + random.uniform(-0.04, 0.04), 6)
                gps_lng_runtime = round(126.9780 + random.uniform(-0.04, 0.04), 6)
                gps_display_label = "⚠️ 시뮬레이션 좌표 (위치 권한 없음)"

            elif saved_gps:
                gps_lat_runtime = saved_gps["lat"]
                gps_lng_runtime = saved_gps["lng"]
                accuracy = saved_gps["accuracy"]
                gps_display_label = f"실제 GPS (정확도 ±{accuracy:.0f}m)"

                gps_ui_cols = st.columns([4, 1])
                with gps_ui_cols[0]:
                    st.success(
                        f"✅ **GPS 위치 확인 완료** | "
                        f"위도 {gps_lat_runtime:.5f} / 경도 {gps_lng_runtime:.5f} | "
                        f"정확도 ±{accuracy:.0f}m | {saved_gps['ts']}"
                    )
                with gps_ui_cols[1]:
                    if st.button("🔄 새로고침", key=f"refresh_gps_{order['id']}"):
                        st.session_state.pop(gps_cache_key, None)
                        st.rerun()

            else:
                st.info(
                    "📡 브라우저에서 위치 권한 요청 중입니다. "
                    "팝업이 나타나면 **'허용'** 을 클릭해 주세요."
                )
                st.caption("위치 권한 없이도 출발은 가능하나, 도착 예정 시간 정확도가 낮아집니다.")
                gps_lat_runtime = round(37.5665 + random.uniform(-0.04, 0.04), 6)
                gps_lng_runtime = round(126.9780 + random.uniform(-0.04, 0.04), 6)
                gps_display_label = "🔄 GPS 대기 중 (임시 좌표)"

        else:
            # 이미 출발했거나 배차완료 아님 → 저장된 GPS 또는 폴백
            saved_gps = st.session_state.get(f"gps_cache_{order['id']}")
            if saved_gps:
                gps_lat_runtime = saved_gps["lat"]
                gps_lng_runtime = saved_gps["lng"]
                gps_display_label = f"실제 GPS (정확도 ±{saved_gps.get('accuracy', 0):.0f}m)"
            else:
                gps_lat_runtime = round(37.5665 + random.uniform(-0.04, 0.04), 6)
                gps_lng_runtime = round(126.9780 + random.uniform(-0.04, 0.04), 6)
                gps_display_label = "시뮬레이션 좌표"

        # ─── 실시간 추적 링크 표시 (출발 후)
        _depart_summ = st.session_state.get(f"depart_summary_{order['id']}")
        if order.get("tracking_token") and order.get("departed_at"):
            _tk = order["tracking_token"]
            _dom = os.environ.get("REPLIT_DEV_DOMAIN", "")
            _turl = f"https://{_dom}/실시간_추적?oid={order['id']}&tok={_tk}" if _dom else ""
            if _turl:
                st.markdown(
                    f"""<div style='background:#e3f2fd;border-left:4px solid #1976d2;
                    border-radius:8px;padding:10px 14px;margin:8px 0'>
                    📡 <b>고객 실시간 추적 링크 (출발 시 자동 발송됨)</b><br>
                    <a href='{_turl}' target='_blank' style='font-size:13px;word-break:break-all'>{_turl}</a><br>
                    <span style='font-size:12px;color:#555'>고객이 이 링크를 열면 기사님의 현재 위치가 지도에 표시됩니다. 30초마다 자동 갱신.</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # ─── GPS 실시간 폴링 + 지오펜싱 (이동 중, 미도착 상태)
        if order["status"] == "in_progress" and not order.get("arrived_at"):
            _live_trip = get_trip_data(order["id"])
            if _live_trip and _GEO_AVAILABLE:
                _live_loc = _get_geolocation(key=f"live_geo_{order['id']}")
                if _live_loc and isinstance(_live_loc, dict) and "coords" in _live_loc:
                    _lc = _live_loc["coords"]
                    _ll, _lg = _lc["latitude"], _lc["longitude"]
                    _geo_result = update_trip_gps(order["id"], _ll, _lg)
                    _dist_m = _geo_result.get("dist_m")
                    if _geo_result.get("geofence_triggered"):
                        # 100m 이내 최초 진입 → 고객 도착 임박 알림 자동 발송
                        dispatch_system_notification(
                            order, driver,
                            "도착임박",
                            f"[순삭 본사] {order['customer']}님, 담당 기사가 잠시 후 도착합니다. "
                            f"문을 열어주시거나 작업 준비를 부탁드립니다. 🚗",
                            journey_field="notif_geofence",
                        )
                        st.success(
                            "✅ **지오펜싱 감지 — 목적지 100m 이내 진입!**\n\n"
                            "고객에게 '잠시 후 도착합니다' 알림이 자동 발송되었습니다."
                        )
                    elif _dist_m is not None:
                        st.info(
                            f"📡 **GPS 갱신 완료** | 목적지까지 약 **{_dist_m:.0f}m** | "
                            f"위도 {_ll:.5f} / 경도 {_lg:.5f}"
                        )

        st.markdown("**📲 상태 업데이트 — 버튼 클릭 시 본사 이름으로 자동 알림톡 발송**")
        st.caption("🤖 기사님이 직접 문자 보내실 필요 없습니다. 버튼을 누르면 시스템이 자동 발송합니다.")

        btn_cols = st.columns(5)

        with btn_cols[0]:
            dep_disabled = order["status"] not in ("dispatched",) or bool(order.get("departed_at"))
            if st.button("🚗 출발하기", key=f"depart_{order['id']}", type="primary",
                         disabled=dep_disabled):
                now = datetime.now()

                # ── 1. 기사 현재 GPS (위 GPS 섹션에서 수집된 실제 좌표 우선 사용)
                gps_lat = gps_lat_runtime if gps_lat_runtime else round(37.5665 + random.uniform(-0.05, 0.05), 6)
                gps_lng = gps_lng_runtime if gps_lng_runtime else round(126.9780 + random.uniform(-0.05, 0.05), 6)

                # ── 2. 고객 주소 → 좌표 (Nominatim 무료 지오코딩)
                dest_addr = order.get("pickup", "") or order.get("destination", "")
                dest_lat_save, dest_lng_save = None, None
                with st.spinner("🗺️ 경로 계산 중... (지도 API 연결)"):
                    dest_coords = None
                    cache_key = f"geocode_{dest_addr}"
                    if cache_key in st.session_state:
                        dest_coords = st.session_state[cache_key]
                    else:
                        dest_coords = geocode_address(dest_addr)
                        st.session_state[cache_key] = dest_coords

                    # ── 3. OSRM으로 실제 도로 소요시간 계산
                    if dest_coords:
                        dest_lat, dest_lng = dest_coords
                        dest_lat_save, dest_lng_save = dest_lat, dest_lng
                        travel_info = estimate_travel(gps_lat, gps_lng, dest_lat, dest_lng)
                    else:
                        # 주소 변환 실패 → 직선거리 기본 추정 15분
                        travel_info = {"duration_min": 15, "dist_km": 0.0, "source": "기본값"}

                duration_min = travel_info["duration_min"]
                dist_km = travel_info["dist_km"]
                travel_source = travel_info["source"]

                # ── 4. ETA 계산
                eta_dt = compute_eta(now, duration_min)
                eta_display = eta_dt.strftime("%H:%M")

                # ── 5. DB 저장
                gps_src = gps_display_label or "시뮬레이션"
                update_order(order["id"], {
                    "status": "in_progress",
                    "departed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "gps_lat": gps_lat,
                    "gps_lng": gps_lng,
                    "eta": eta_display,
                    "expected_travel_min": duration_min,
                    "travel_dist_km": dist_km,
                    "travel_source": travel_source,
                })
                add_driver_log({
                    "order_id": order["id"],
                    "driver_id": driver["id"],
                    "event": "출발",
                    "detail": {
                        "departed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "gps_lat": gps_lat,
                        "gps_lng": gps_lng,
                        "gps_source": gps_src,
                        "eta": eta_display,
                        "expected_travel_min": duration_min,
                        "dist_km": dist_km,
                        "travel_source": travel_source,
                    }
                })

                # ── 6. 트립 추적 시작 + 추적 토큰 생성
                _tracking_token = str(uuid.uuid4())[:8]
                start_trip_tracking(
                    order_id=order["id"],
                    driver_id=driver["id"],
                    driver_name=driver["name"],
                    origin_lat=gps_lat,
                    origin_lng=gps_lng,
                    dest_lat=dest_lat_save,
                    dest_lng=dest_lng_save,
                    dest_address=dest_addr,
                    eta_str=eta_display,
                    expected_min=duration_min,
                    tracking_token=_tracking_token,
                )
                update_order(order["id"], {"tracking_token": _tracking_token})

                # ── 7. 추적 링크 생성
                _domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
                _tracking_url = (
                    f"https://{_domain}/실시간_추적?oid={order['id']}&tok={_tracking_token}"
                    if _domain else ""
                )

                # ── 8. 고객 알림톡 자동 발송 (추적 링크 포함)
                _track_line = (
                    f"\n\n🔗 실시간 위치 확인: {_tracking_url}"
                    if _tracking_url else ""
                )
                depart_msg = (
                    f"[순삭수거] {order['customer']}님, 담당 기사가 출발했습니다.\n\n"
                    f"약 {duration_min}분 뒤인 {eta_display}에 도착 예정입니다.\n\n"
                    f"원활한 작업을 위해 현장 주차 및 통로 확보를 부탁드립니다!\n\n"
                    f"📍 예상 이동 거리: 약 {dist_km}km ({travel_source})"
                    f"{_track_line}"
                )
                dispatch_system_notification(
                    order, driver,
                    "기사출발",
                    depart_msg,
                    journey_field="notif_dispatched"
                )

                # ── 9. GPS 소스 품질 기록
                gps_quality = "실제GPS" if gps_display_label and "실제" in str(gps_display_label) else "추정좌표"
                st.session_state[f"depart_summary_{order['id']}"] = {
                    "departed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "eta": eta_display,
                    "duration_min": duration_min,
                    "dist_km": dist_km,
                    "gps_quality": gps_quality,
                    "tracking_url": _tracking_url,
                }
                st.success(
                    f"✅ **출발 완료!** 고객 알림톡 자동 발송됨\n\n"
                    f"📨 '담당 기사가 출발했습니다. 약 {duration_min}분 뒤인 {eta_display}에 도착 예정'\n\n"
                    f"📍 경로: {dist_km}km | GPS: {gps_quality} | 산출: {travel_source}"
                )
                st.rerun()

        with btn_cols[1]:
            arr_disabled = not bool(order.get("departed_at")) or bool(order.get("arrived_at"))
            if st.button("📍 현장도착", key=f"arrive_{order['id']}",
                         disabled=arr_disabled):
                now = datetime.now()
                dep_time_str = order.get("departed_at", "")
                actual_min = 0
                try:
                    dep_dt = datetime.strptime(dep_time_str, "%Y-%m-%d %H:%M:%S")
                    actual_min = max(0, int((now - dep_dt).total_seconds() / 60))
                except Exception:
                    actual_min = 0

                expected_min = order.get("expected_travel_min")
                is_late = actual_min >= 30
                eff_label, _ = efficiency_label(expected_min or actual_min, actual_min)

                # 트립 완료 기록 (현재 GPS 또는 캐시 사용)
                _arr_gps = st.session_state.get(f"gps_cache_{order['id']}")
                _arr_lat = _arr_gps["lat"] if _arr_gps else gps_lat_runtime or 37.5665
                _arr_lng = _arr_gps["lng"] if _arr_gps else gps_lng_runtime or 126.9780
                complete_trip_tracking(order["id"], _arr_lat, _arr_lng, actual_min)

                update_order(order["id"], {
                    "arrived_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "actual_travel_min": actual_min,
                    "departure_delay_minutes": actual_min,
                    "delay_flag": is_late,
                })
                add_driver_log({
                    "order_id": order["id"],
                    "driver_id": driver["id"],
                    "event": "현장도착",
                    "detail": {
                        "arrived_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "actual_travel_min": actual_min,
                        "expected_travel_min": expected_min,
                        "efficiency": eff_label,
                        "delay_flag": is_late,
                    }
                })
                if is_late:
                    st.warning(
                        f"⚠️ 현장 도착! 실제 이동 {actual_min}분 "
                        f"(예상 {expected_min}분 → {eff_label}) — 지연 패널티 적용 대상"
                    )
                else:
                    st.success(
                        f"📍 현장 도착 완료! 실제 이동 {actual_min}분 "
                        f"(예상 {expected_min}분) — {eff_label}"
                    )
                st.rerun()

        with btn_cols[2]:
            if st.button("⏰ 지연", key=f"delay_{order['id']}",
                         disabled=order["status"] not in ("in_progress", "dispatched")):
                update_order(order["id"], {"delay_flag": True})
                add_driver_log({"order_id": order["id"], "driver_id": driver["id"], "event": "지연"})
                dispatch_system_notification(
                    order, driver,
                    "지연",
                    "[순삭 본사] 죄송합니다. 작업팀 도착이 다소 지연되고 있습니다. 빠르게 처리하겠습니다.",
                )
                st.warning("⏰ 지연 알림 발송됨 — 수당 차감 대상으로 등록됩니다.")
                st.rerun()

        with btn_cols[3]:
            if st.button("🔔 5분전", key=f"eta_{order['id']}",
                         disabled=order["status"] not in ("in_progress",)):
                add_driver_log({"order_id": order["id"], "driver_id": driver["id"], "event": "5분전 도착"})
                dispatch_system_notification(
                    order, driver,
                    "5분전 도착",
                    "[순삭 본사] 담당 작업팀이 약 5분 후 도착 예정입니다. 미리 준비해 주세요! 🚗",
                    journey_field="notif_eta"
                )
                st.info("🔔 5분전 도착 알림 — 본사 이름으로 자동 발송!")
                st.rerun()

        with btn_cols[4]:
            photos_required = order.get("photo_before") and order.get("photo_after") and order.get("photo_cleanup")
            if st.button("✅ 완료", key=f"complete_{order['id']}", type="primary",
                         disabled=order["status"] not in ("in_progress",)):
                if not photos_required:
                    missing = []
                    if not order.get("photo_before"): missing.append("작업 전")
                    if not order.get("photo_after"): missing.append("작업 후")
                    if not order.get("photo_cleanup"): missing.append("정리 정돈")
                    st.error(f"❌ 완료 처리 불가 — {', '.join(missing)} 사진 업로드 필요")
                else:
                    update_order(order["id"], {"status": "completed"})
                    add_driver_log({"order_id": order["id"], "driver_id": driver["id"], "event": "완료"})
                    dispatch_system_notification(
                        order, driver,
                        "완료",
                        "[순삭 본사] 작업이 깔끔하게 완료되었습니다! 이용해 주셔서 감사합니다 🙏 전·후 사진은 본사에서 보관합니다.",
                        journey_field="notif_completed"
                    )
                    all_db = get_all()
                    for d in all_db["drivers"]:
                        if d["id"] == driver["id"]:
                            d["completed_jobs"] = d.get("completed_jobs", 0) + 1
                            d["monthly_jobs"] = d.get("monthly_jobs", 0) + 1
                            if order.get("work_type") == "철거":
                                d["demolition_jobs"] = d.get("demolition_jobs", 0) + 1
                            else:
                                d["collection_jobs"] = d.get("collection_jobs", 0) + 1
                            break
                    db_path = Path(__file__).parent.parent / "data" / "soonssak_db.json"
                    with open(db_path, "w", encoding="utf-8") as f:
                        json.dump(all_db, f, ensure_ascii=False, indent=2, default=str)
                    st.success("🎉 완료 처리! 본사 이름으로 감사 알림톡 자동 발송됨")
                    st.rerun()

        if not photos_required and order["status"] == "in_progress":
            missing = []
            if not order.get("photo_before"): missing.append("작업 전")
            if not order.get("photo_after"): missing.append("작업 후")
            if not order.get("photo_cleanup"): missing.append("정리 정돈")
            st.error(f"⚠️ 완료 버튼 비활성 — {', '.join(missing)} 사진 업로드 필요")

        # ─── 추가 요금 요청
        with st.expander("💸 추가 요금 요청"):
            if order.get("extra_fee_status") == "pending":
                st.warning(f"⏳ 추가 요금 ₩{order['extra_fee']:,} 고객 승인 대기 중")
            elif order.get("extra_fee_status") == "approved":
                st.success(f"✅ 추가 요금 ₩{order['extra_fee']:,} 고객 승인됨")
            elif order.get("extra_fee_status") == "rejected":
                st.error("❌ 추가 요금 고객 거절 — 출동비만 정산됩니다")
            else:
                extra_amount = st.number_input("추가 요금 금액 (원)", min_value=0, step=5000, key=f"extra_{order['id']}")
                extra_reason = st.text_input("사유", placeholder="예: 층간 이동, 장거리 추가", key=f"reason_{order['id']}")
                if st.button("📤 고객에게 추가요금 승인 요청", key=f"req_extra_{order['id']}"):
                    if extra_amount > 0:
                        update_order(order["id"], {"extra_fee": int(extra_amount), "extra_fee_status": "pending"})
                        dispatch_system_notification(
                            order, driver,
                            "추가요금요청",
                            f"[순삭 본사] 현장 상황으로 인한 추가 요금 ₩{extra_amount:,} 승인이 필요합니다. "
                            f"사유: {extra_reason} | [승인하기 / 거절하기] 본사로 연락 주세요."
                        )
                        st.success("📤 고객에게 추가요금 승인 알림 자동 발송!")
                        st.rerun()
                    else:
                        st.error("금액을 입력해주세요.")

# ─── 가상번호 통화 이력
st.divider()
st.subheader("📞 가상번호(050) 소통 이력")
st.caption("법인 가상번호를 통한 모든 통화 기록이 자동 저장됩니다.")

all_logs = get_driver_logs()
call_logs = [
    lg for lg in all_logs
    if lg.get("event") == "가상번호통화" and lg.get("driver_id") == driver["id"]
]

if not call_logs:
    st.info("가상번호 통화 이력이 없습니다.")
else:
    import pandas as pd
    rows = []
    for lg in reversed(call_logs[-20:]):
        detail = lg.get("detail", {})
        rows.append({
            "통화 시각": detail.get("call_started", lg.get("timestamp", "—"))[:16],
            "주문": f"#{lg.get('order_id', '—')}",
            "고객": detail.get("customer", "—"),
            "가상번호(050)": detail.get("virtual_number", "—"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"💾 총 {len(call_logs)}건의 통화 기록이 DB에 저장됨")

# ─── 고객 만족도 설문
st.divider()
st.subheader("😊 고객 만족도 설문 등록")
completed_orders_survey = [o for o in all_driver_orders if o["status"] == "completed" and o.get("satisfaction_score") is None]
if not completed_orders_survey:
    done_with_survey = [o for o in all_driver_orders if o["status"] == "completed" and o.get("satisfaction_score") is not None]
    if done_with_survey:
        avg_score = sum(o["satisfaction_score"] for o in done_with_survey) / len(done_with_survey)
        st.success(f"✅ 이 기사의 만족도 설문 완료 {len(done_with_survey)}건 | 평균 점수: ⭐ {avg_score:.1f}")
    else:
        st.info("설문 등록 대기 중인 완료 주문이 없습니다.")
else:
    for co in completed_orders_survey:
        with st.expander(f"주문 #{co['id']} — {co['customer']} 설문 등록"):
            score = st.slider("고객 만족도 (1~5점)", 1, 5, 5, key=f"survey_score_{co['id']}")
            comment = st.text_area("고객 코멘트 (선택)", key=f"survey_comment_{co['id']}")
            if st.button(f"📝 설문 저장", key=f"save_survey_{co['id']}"):
                update_order(co["id"], {
                    "satisfaction_score": score,
                    "satisfaction_comment": comment,
                })
                add_satisfaction_survey({
                    "order_id": co["id"],
                    "driver_id": driver["id"],
                    "score": score,
                    "comment": comment,
                })
                all_db = get_all()
                scores_for_driver = [
                    o.get("satisfaction_score") for o in all_db["orders"]
                    if o.get("driver_id") == driver["id"] and o.get("satisfaction_score")
                ]
                if scores_for_driver:
                    avg = round(sum(scores_for_driver) / len(scores_for_driver), 1)
                    for d in all_db["drivers"]:
                        if d["id"] == driver["id"]:
                            d["avg_satisfaction"] = avg
                            d["rating"] = round(min(5.0, (d.get("rating", 4.0) * 0.7 + avg * 0.3)), 1)
                            break
                    db_path = Path(__file__).parent.parent / "data" / "soonssak_db.json"
                    with open(db_path, "w", encoding="utf-8") as f:
                        json.dump(all_db, f, ensure_ascii=False, indent=2, default=str)
                st.success(f"✅ 만족도 {score}점 저장됨 — 기사 프로필에 반영됩니다!")
                st.rerun()

st.divider()

# ─── 매니저 전용: 법인폰 로그 대조 결과 ───────────────
with st.expander("📱 [매니저 전용] 법인폰 로그 대조 결과", expanded=False):
    st.caption("법인폰 감사 페이지의 분석 결과와 이 기사의 배차 이력을 대조합니다.")
    phone_logs = get_phone_logs()
    driver_phone_logs = [pl for pl in phone_logs if pl.get("driver_id") == driver["id"]]

    if not driver_phone_logs:
        st.info("이 기사의 법인폰 로그가 없습니다. '법인폰 감사' 페이지에서 먼저 등록하세요.")
    else:
        completed_order_ids = {o["id"] for o in all_driver_orders if o["status"] == "completed"}
        anomalies = []
        for pl in driver_phone_logs:
            matched = pl.get("matched_order_id")
            if matched and matched not in completed_order_ids:
                anomalies.append(pl)

        if anomalies:
            st.error(f"🔴 이상 감지: {len(anomalies)}건의 통화 로그가 완료 배차와 불일치합니다!")
            for a in anomalies:
                st.warning(
                    f"통화 일시: {a.get('call_time','—')} | "
                    f"상대번호: {a.get('contact_number','—')} | "
                    f"매칭주문: #{a.get('matched_order_id','—')} (미완료)"
                )
        else:
            st.success(f"✅ 법인폰 로그 {len(driver_phone_logs)}건 모두 배차 이력과 정상 일치")

        # 요약 테이블
        log_rows = []
        for pl in driver_phone_logs[-10:]:
            matched_id = pl.get("matched_order_id")
            is_ok = matched_id in completed_order_ids if matched_id else None
            log_rows.append({
                "통화일시": pl.get("call_time","—"),
                "상대번호": pl.get("contact_number","—"),
                "통화유형": pl.get("call_type","—"),
                "매칭주문": f"#{matched_id}" if matched_id else "미매칭",
                "대조결과": "✅ 정상" if is_ok else ("🔴 불일치" if is_ok is False else "⚠️ 미확인"),
            })
        if log_rows:
            st.dataframe(__import__("pandas").DataFrame(log_rows), use_container_width=True, hide_index=True)

st.divider()

# ─── 알림톡 발송 이력
st.subheader("📬 알림톡 발송 이력 (본사 자동 발송)")
from data.db import get_notifications
notifications = [n for n in get_notifications() if
                 any(o.get("driver_id") == driver["id"] for o in orders if o["id"] == n.get("order_id"))]
if not notifications:
    st.info("발송된 알림이 없습니다.")
else:
    for n in reversed(notifications[-10:]):
        type_icon = {"출발": "🚀", "지연": "⏰", "5분전 도착": "🔔", "완료": "✅",
                     "추가요금요청": "💸"}.get(n["type"], "📢")
        sender_tag = " _(본사 자동발송)_" if n.get("sender") else ""
        st.markdown(f"{type_icon} **{n['type']}**{sender_tag} — {n['customer']} ({n['customer_phone']}) — `{n['sent_at']}`")
        st.caption(n["message"][:120] + "…" if len(n.get("message", "")) > 120 else n.get("message", ""))

show_legal_warning()
