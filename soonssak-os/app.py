import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

st.set_page_config(
    page_title="순삭 OS",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

from data.db import (get_orders, get_drivers, get_settings,
                      get_supply_requests, resolve_supply_request)
from utils.footer import show_legal_warning
from utils.rbac import (render_role_selector, is_owner, is_executor, is_cs,
                         is_manager, is_manager_only, manager_region,
                         current_role, ROLES, executor_team)
from utils.ai_vision import MATCH_ALERT_THRESHOLD, score_badge

render_role_selector()

st.markdown(
    """
<style>
html, body, [class*="css"] { font-size: 16px !important; }
.stButton > button {
    font-size: 17px !important;
    padding: 12px 20px !important;
    border-radius: 10px !important;
    min-height: 50px !important;
    font-weight: 600 !important;
}
.stMetric label { font-size: 15px !important; }
.stMetric [data-testid="stMetricValue"] { font-size: 26px !important; font-weight: 700 !important; }
/* 배너 글씨 강제 색상 */
.role-banner b { color: #1a1a1a !important; }
.role-banner span { color: #333 !important; }
@keyframes emergency-blink {
    0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(198,40,40,0.4); }
    50% { opacity: 0.7; box-shadow: 0 0 0 12px rgba(198,40,40,0); }
}
.emergency-blink {
    animation: emergency-blink 1.2s ease-in-out infinite;
    border: 3px solid #c62828 !important;
}
@keyframes icon-pulse {
    0%,100% { transform: scale(1); }
    50% { transform: scale(1.25); }
}
.pulse-icon { display:inline-block; animation: icon-pulse 1s ease-in-out infinite; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🚗 순삭 OS — 통합 관리 시스템")
st.markdown("**배차 · 실행팀 앱 · 정산 · 리스크 관리 · 세무 · 월간 정산 명세서**를 하나의 흐름으로")

# ── 역할별 첫 화면 안내 배너
_role_now = current_role()
_BANNER_KEY = f"_role_banner_closed_{_role_now}"
if not st.session_state.get(_BANNER_KEY, False):
    _TEAM_COLORS = {
        "블루":   ("#e3f2fd", "#1565c0"),
        "옐로우": ("#fffde7", "#f9a825"),
        "레드":   ("#ffebee", "#c62828"),
        "그린":   ("#e8f5e9", "#2e7d32"),
    }
    _team = executor_team() if is_executor() else ""
    _team_bg, _team_border = _TEAM_COLORS.get(_team, ("#e8f5e9", "#2e7d32"))

    _BANNERS = {
        "executor_blue":   {"bg": _team_bg,   "border": _team_border, "icon": "🔵", "title": f"실행팀 블루 환영합니다!", "msg": "오늘의 배차 주문을 확인하고 출발하세요. 사진(전/후 2장)을 빠뜨리지 마세요.", "link": "📖 실행팀 업무 가이드 → [가이드/매뉴얼] 페이지"},
        "executor_yellow": {"bg": "#fffde7",  "border": "#f9a825",    "icon": "🟡", "title": f"실행팀 옐로우 환영합니다!", "msg": "오늘의 배차 주문을 확인하고 출발하세요. 사진(전/후 2장)을 빠뜨리지 마세요.", "link": "📖 실행팀 업무 가이드 → [가이드/매뉴얼] 페이지"},
        "executor_red":    {"bg": "#ffebee",  "border": "#c62828",    "icon": "🔴", "title": f"실행팀 레드 환영합니다!", "msg": "오늘의 배차 주문을 확인하고 출발하세요. 사진(전/후 2장)을 빠뜨리지 마세요.", "link": "📖 실행팀 업무 가이드 → [가이드/매뉴얼] 페이지"},
        "executor_green":  {"bg": "#e8f5e9",  "border": "#2e7d32",    "icon": "🟢", "title": f"실행팀 그린 환영합니다!", "msg": "오늘의 배차 주문을 확인하고 출발하세요. 사진(전/후 2장)을 빠뜨리지 마세요.", "link": "📖 실행팀 업무 가이드 → [가이드/매뉴얼] 페이지"},
        "manager_sejong":  {"bg": "#e3f2fd",  "border": "#1565c0",    "icon": "👔", "title": "매니저 1 — 세종 지역", "msg": "세종 지역 리드 및 실행팀만 표시됩니다. 사진 3장 미업로드 시 견적 확정이 잠깁니다.", "link": "📖 현장 견적 가이드 → [가이드/매뉴얼] 페이지"},
        "manager_bonsa":   {"bg": "#e8eaf6",  "border": "#3949ab",    "icon": "👔", "title": "매니저 2 — 본사 지역", "msg": "본사 지역 리드 및 실행팀만 표시됩니다. 사진 3장 미업로드 시 견적 확정이 잠깁니다.", "link": "📖 현장 견적 가이드 → [가이드/매뉴얼] 페이지"},
        "cs":              {"bg": "#fff8e1",  "border": "#f57f17",    "icon": "🎧", "title": "CS 상담원 모드", "msg": "신규 주문은 CS 상담센터에서 등록하세요. 마케팅 유입 경로를 반드시 선택해 주세요.", "link": "📖 상담 스크립트 → [가이드/매뉴얼] 페이지"},
        "owner":           {"bg": "#f3e5f5",  "border": "#6a1b9a",    "icon": "👑", "title": "Owner(대표) 모드 — 무소음", "msg": "세종+본사 통합 KPI가 표시됩니다. 일상 운영 알림은 매니저에게만 발송됩니다.", "link": "📖 시스템 관리 가이드 → [가이드/매뉴얼] 페이지"},
    }
    _b = _BANNERS.get(_role_now)
    if _b:
        _bcol1, _bcol2 = st.columns([10, 1])
        with _bcol1:
            st.markdown(
                f"""
<div class="role-banner" style="background:{_b['bg']};border-left:5px solid {_b['border']};
     border-radius:10px;padding:12px 18px;margin-bottom:10px">
<b style="font-size:17px;color:#1a1a1a">{_b['icon']} {_b['title']}</b><br>
<span style="font-size:15px;color:#333">{_b['msg']}</span><br>
<span style="font-size:13px;color:#555">{_b['link']}</span>
</div>
""",
                unsafe_allow_html=True,
            )
        with _bcol2:
            if st.button("✕", key=f"close_banner_{_role_now}", help="배너 닫기"):
                st.session_state[_BANNER_KEY] = True
                st.rerun()

settings = get_settings()

# ─── 지역 데이터 범위 결정
if is_owner():
    _all_regions = ["전체"] + settings.get("regions", ["본사", "세종"])
    _owner_region = st.selectbox(
        "🗂️ 데이터 보기 지역", _all_regions, index=0, key="_owner_region_view",
        help="Owner 전용 — 지역별 데이터를 스위칭하거나 전체 통합 뷰로 조회합니다.",
    )
    if _owner_region != "전체":
        st.caption(f"🔍 **{_owner_region} 지역** 필터 적용 중")
elif is_manager_only():
    _owner_region = manager_region()
    st.markdown(
        f"""
<div style="background:#e8f5e9;border-left:4px solid #2e7d32;border-radius:8px;
     padding:8px 14px;margin-bottom:8px;font-size:14px;color:#1b5e20">
📍 <b>담당 지역 고정:</b> {_owner_region} — 타 지역 데이터는 자동으로 숨겨집니다.
</div>
""", unsafe_allow_html=True)
else:
    _owner_region = "전체"

st.divider()

import pandas as pd

orders = get_orders()
drivers = get_drivers()

if _owner_region != "전체":
    orders = [o for o in orders if o.get("region", "본사") == _owner_region]
    drivers = [d for d in drivers if d.get("region", "본사") == _owner_region]

status_counts = {}
for o in orders:
    status_counts[o["status"]] = status_counts.get(o["status"], 0) + 1

total_revenue = sum(
    (o["base_fee"] + (o["extra_fee"] if o.get("extra_fee_status") == "approved" else 0))
    for o in orders if o.get("payment_confirmed")
)
driver_payout = total_revenue * settings["driver_ratio"]
pending_extra = [o for o in orders if o.get("extra_fee_status") == "pending"]
available_drivers = sum(1 for d in drivers if d["available"])
flagged_count = sum(1 for o in orders if o.get("arbitrary_fee_flag"))
delayed_count = sum(1 for o in orders if o.get("delay_flag"))
photo_missing = sum(1 for o in orders if o["status"] in ("in_progress", "dispatched")
                    and not (o.get("photo_before") and o.get("photo_after")))
active_drivers = sum(1 for d in drivers if d.get("monthly_jobs", 0) >= settings.get("active_driver_threshold", 60))

# ══ Owner 전용 대시보드
if is_owner():
    _all_orders_raw = get_orders()
    _ai_flagged = [o for o in _all_orders_raw if o.get("photo_match_flagged") and o.get("photo_match_score") is not None]
    _auto_penalty = [o for o in _all_orders_raw if o.get("settlement_hold") or o.get("arbitrary_fee_flag")]
    _emergency_count = len(_ai_flagged) + len(_auto_penalty)

    if _emergency_count > 0:
        st.markdown(
            f"""
<div class="emergency-blink" style="background:#ffebee;border-radius:12px;
     padding:16px 22px;margin-bottom:16px">
<span class="pulse-icon" style="font-size:22px">🚨</span>
<b style="font-size:18px;color:#b71c1c"> 긴급 예외 알림 — {_emergency_count}건 즉시 확인 필요</b><br>
<span style="color:#c62828;font-size:14px">
  일상 운영 알림은 담당 매니저에게만 발송됩니다. 아래 항목은 Owner 개입이 필요한 예외 상황입니다.
</span>
</div>
""", unsafe_allow_html=True)

        with st.expander(f"🔐 예외 알림 상세 ({_emergency_count}건)", expanded=True):
            if _ai_flagged:
                st.markdown("##### 🤖 AI 사진 불일치 (사기 위험)")
                for o in _ai_flagged:
                    _score = o.get("photo_match_score")
                    _reasoning = o.get("photo_match_reasoning", "")
                    _flags = o.get("photo_match_flags", [])
                    _ec1, _ec2 = st.columns([1, 5])
                    with _ec1:
                        st.markdown(f"<div style='text-align:center'>{score_badge(_score)}</div>", unsafe_allow_html=True)
                        st.caption(f"임계값: {MATCH_ALERT_THRESHOLD}점")
                    with _ec2:
                        st.markdown(f"**#{o['id']}** {o['customer']} | 지역: {o.get('region','본사')} | AI: {_score}점")
                        st.caption(_reasoning)
                        for fl in _flags:
                            st.warning(f"⚠️ {fl}")
                    _ep = o.get("estimate_photo_path")
                    _cp = o.get("completion_photo_path")
                    if _ep or _cp:
                        _ic1, _ic2 = st.columns(2)
                        with _ic1:
                            if _ep and os.path.exists(_ep):
                                st.image(_ep, caption="견적 사진", use_container_width=True)
                        with _ic2:
                            if _cp and os.path.exists(_cp):
                                st.image(_cp, caption="완료 사진", use_container_width=True)
            if _auto_penalty:
                st.markdown("##### 🔒 정산 보류 / 임의 요금")
                for o in _auto_penalty:
                    flag_type = "정산 보류(Hold)" if o.get("settlement_hold") else "임의 요금 플래그"
                    st.error(f"**#{o['id']}** {o['customer']} — {flag_type} | 지역: {o.get('region','본사')} | 기사: {o.get('_driver_name','—')}")
    else:
        st.markdown(
            """
<div style="background:#e8f5e9;border-left:5px solid #2e7d32;border-radius:10px;
     padding:12px 18px;margin-bottom:16px">
<b style="font-size:16px;color:#1b5e20">✅ 긴급 예외 상황 없음</b><br>
<span style="color:#388e3c;font-size:14px">시스템이 자동으로 운영 중입니다. 일상 알림은 매니저가 수신합니다.</span>
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📊 운영 현황 KPI 요약")
    _total = len(orders)
    _completed = status_counts.get("completed", 0)
    _conversion = round(_completed / _total * 100, 1) if _total > 0 else 0.0
    _net_margin = total_revenue - driver_payout

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    with kpi1:
        st.markdown(f"<div style='background:#e8f5e9;border-radius:12px;padding:16px;text-align:center'><div style='font-size:13px;color:#388e3c'>💰 확정 매출</div><div style='font-size:28px;font-weight:800;color:#1b5e20'>₩{total_revenue:,.0f}</div></div>", unsafe_allow_html=True)
    with kpi2:
        st.markdown(f"<div style='background:#e3f2fd;border-radius:12px;padding:16px;text-align:center'><div style='font-size:13px;color:#1565c0'>📋 전체 주문</div><div style='font-size:28px;font-weight:800;color:#0d47a1'>{_total}건</div></div>", unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"<div style='background:#f3e5f5;border-radius:12px;padding:16px;text-align:center'><div style='font-size:13px;color:#7b1fa2'>✅ 완료 건수</div><div style='font-size:28px;font-weight:800;color:#4a148c'>{_completed}건</div></div>", unsafe_allow_html=True)
    with kpi4:
        _conv_color = "#388e3c" if _conversion >= 70 else ("#f57c00" if _conversion >= 40 else "#c62828")
        st.markdown(f"<div style='background:#fff8e1;border-radius:12px;padding:16px;text-align:center'><div style='font-size:13px;color:#f57f17'>🎯 성사율</div><div style='font-size:28px;font-weight:800;color:{_conv_color}'>{_conversion}%</div></div>", unsafe_allow_html=True)
    with kpi5:
        st.markdown(f"<div style='background:#fce4ec;border-radius:12px;padding:16px;text-align:center'><div style='font-size:13px;color:#c62828'>💎 순익</div><div style='font-size:28px;font-weight:800;color:#b71c1c'>₩{_net_margin:,.0f}</div></div>", unsafe_allow_html=True)

    st.markdown("")
    chart_col1, chart_col2, chart_col3 = st.columns([2, 2, 2])
    with chart_col1:
        st.markdown("**📈 주문 상태 분포**")
        _status_df = pd.DataFrame({"상태": ["대기중","배차완료","진행중","완료","취소"], "건수": [status_counts.get("pending",0), status_counts.get("dispatched",0), status_counts.get("in_progress",0), status_counts.get("completed",0), status_counts.get("cancelled",0)]}).set_index("상태")
        st.bar_chart(_status_df, height=200)
    with chart_col2:
        st.markdown("**🔨 작업 유형별 매출**")
        _wt_data = {"수거": 0, "철거": 0}
        for o in orders:
            if o.get("payment_confirmed"):
                amt = o["base_fee"] + (o["extra_fee"] if o.get("extra_fee_status") == "approved" else 0)
                _wt_data[o.get("work_type","수거")] = _wt_data.get(o.get("work_type","수거"), 0) + amt
        st.bar_chart(pd.DataFrame({"작업 유형": list(_wt_data.keys()), "매출(원)": list(_wt_data.values())}).set_index("작업 유형"), height=200)
    with chart_col3:
        st.markdown("**🗺️ 지역별 주문**")
        _region_data = {}
        for o in orders:
            _r = o.get("region", "본사")
            _region_data[_r] = _region_data.get(_r, 0) + 1
        if _region_data:
            st.bar_chart(pd.DataFrame({"지역": list(_region_data.keys()), "건수": list(_region_data.values())}).set_index("지역"), height=200)
        else:
            st.info("지역 데이터 없음")

    st.markdown("**🔄 주문 전환 퍼널**")
    _funnel_stages = [("📋 접수", len(orders)), ("📍 배차완료", status_counts.get("dispatched",0)+status_counts.get("in_progress",0)+status_counts.get("completed",0)), ("🔄 진행중", status_counts.get("in_progress",0)+status_counts.get("completed",0)), ("✅ 완료", status_counts.get("completed",0))]
    for _stage_name, _stage_val in _funnel_stages:
        _pct = int(_stage_val / len(orders) * 100) if orders else 0
        _fc1, _fc2 = st.columns([1, 5])
        with _fc1:
            st.markdown(f"**{_stage_name}** — {_stage_val}건")
        with _fc2:
            st.progress(_pct / 100, text=f"{_pct}%")

    st.divider()
    _pending_supply = get_supply_requests(unresolved_only=True)
    _supply_count = len(_pending_supply)
    if _supply_count > 0:
        _badge_color = "#c62828" if any(r.get("urgency") == "긴급" for r in _pending_supply) else "#f57c00"
        st.markdown(f"""<div style="background:#fff3e0;border-left:5px solid {_badge_color};border-radius:10px;padding:12px 18px;margin-bottom:8px;display:flex;align-items:center;gap:12px"><span style="background:{_badge_color};color:white;font-size:22px;font-weight:800;border-radius:50%;width:40px;height:40px;display:inline-flex;align-items:center;justify-content:center">{_supply_count}</span><div><b style="font-size:16px;color:{_badge_color}">📦 비품 보충 신청 대기</b><br><span style="font-size:13px;color:#ccc">매니저가 신청한 소모품 보충 건이 있습니다.</span></div></div>""", unsafe_allow_html=True)
        with st.expander(f"📦 비품 관리 — 미처리 {_supply_count}건", expanded=False):
            for _sr in _pending_supply:
                _urgency_badge = "<span style='background:#c62828;color:white;padding:1px 7px;border-radius:4px;font-size:12px'>🚨 긴급</span>" if _sr.get("urgency") == "긴급" else "<span style='background:#f57c00;color:white;padding:1px 7px;border-radius:4px;font-size:12px'>일반</span>"
                _items_str = ", ".join(f"{i.get('name','—')} ({i.get('qty','—')})" for i in _sr.get("items", []))
                st.markdown(f"**#{_sr['id']}** {_urgency_badge} | {_sr.get('region','—')} | {_sr.get('manager_label','—')} | {_sr.get('requested_at','—')}", unsafe_allow_html=True)
                st.caption(f"📦 신청 항목: {_items_str}")
                _rc1, _rc2 = st.columns([2, 5])
                with _rc1:
                    _resolve_note = st.text_input("처리 메모", placeholder="예: 익일 배송 완료", key=f"supply_note_{_sr['id']}", label_visibility="collapsed")
                with _rc2:
                    if st.button("✅ 처리 완료로 표시", key=f"supply_resolve_{_sr['id']}", type="primary"):
                        resolve_supply_request(_sr["id"], _resolve_note)
                        st.success(f"✅ #{_sr['id']} 처리 완료 표시됨")
                        st.rerun()
                st.markdown("---")
    else:
        st.markdown("""<div style="background:#1a2a1a;border-left:4px solid #9e9e9e;border-radius:8px;padding:10px 16px;margin-bottom:8px;font-size:14px;color:#9e9e9e">📦 <b>비품 관리</b> — 현재 미처리 신청 없음</div>""", unsafe_allow_html=True)

    st.divider()

# ══ 비-Owner
else:
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("📋 전체 주문", len(orders))
    with col2: st.metric("✅ 완료", status_counts.get("completed", 0))
    with col3: st.metric("🔄 진행중", status_counts.get("in_progress", 0))
    with col4: st.metric("⏳ 대기중", status_counts.get("pending", 0))
    with col5: st.metric("🚗 가용 실행팀", f"{available_drivers}명")

    st.divider()

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a: st.metric("💰 확정 매출", f"₩{total_revenue:,.0f}")
    with col_b: st.metric("👨‍✈️ 실행팀 지급액 (70%)", f"₩{driver_payout:,.0f}")
    with col_c:
        if pending_extra:
            st.metric("⚠️ 추가요금 승인 대기", f"{len(pending_extra)}건", delta="확인 필요", delta_color="inverse")
        else:
            st.metric("⚠️ 추가요금 승인 대기", "0건")
    with col_d: st.metric("🔥 활성 실행팀 (60건+)", f"{active_drivers}명")

    st.divider()

    if flagged_count or delayed_count or photo_missing:
        alert_col1, alert_col2, alert_col3 = st.columns(3)
        with alert_col1:
            if flagged_count:
                st.error(f"🚨 임의추가요금 적발: **{flagged_count}건** — 수당 0원 + 3배 배상 경고")
        with alert_col2:
            if delayed_count:
                st.warning(f"⏰ 지연 발생: **{delayed_count}건** — 패널티 차감 대상")
        with alert_col3:
            if photo_missing:
                st.error(f"📷 사진 미업로드: **{photo_missing}건** — 완료 처리 불가")
        st.divider()

st.subheader("📊 최근 주문 현황")

status_labels = {
    "pending": "⏳ 대기중", "dispatched": "📍 배차완료",
    "in_progress": "🔄 진행중", "completed": "✅ 완료", "cancelled": "❌ 취소",
}

order_rows = []
for o in sorted(orders, key=lambda x: x["created_at"], reverse=True)[:10]:
    driver = next((d for d in drivers if d["id"] == o.get("driver_id")), None)
    risk_flags = []
    if o.get("arbitrary_fee_flag"): risk_flags.append("🚨적발")
    if o.get("delay_flag"): risk_flags.append("⏰지연")
    if not (o.get("photo_before") and o.get("photo_after")) and o["status"] in ("in_progress", "dispatched"):
        risk_flags.append("📷미업로드")
    order_rows.append({
        "주문 ID": f"#{o['id']}", "고객명": o["customer"],
        "작업": "🔨 철거" if o.get("work_type") == "철거" else "📦 수거",
        "실행팀": driver["name"] if driver else "미배차",
        "예약 시간": o["scheduled_time"], "기본요금": f"₩{o['base_fee']:,}",
        "상태": status_labels.get(o["status"], o["status"]),
        "입금": "✅" if o.get("payment_confirmed") else "❌",
        "리스크": " ".join(risk_flags) if risk_flags else "—",
    })

if order_rows:
    st.dataframe(pd.DataFrame(order_rows), use_container_width=True, hide_index=True)

st.divider()

col_left, col_right = st.columns(2)
with col_left:
    st.subheader("🚗 실행팀 현황")
    for d in sorted(drivers, key=lambda x: x["rating"], reverse=True):
        status_icon = "🟢" if d["available"] else "🔴"
        monthly = d.get("monthly_jobs", 0)
        threshold = settings.get("active_driver_threshold", 60)
        active_tag = " 🔥활성" if monthly >= threshold else ""
        st.markdown(
            f"{status_icon} **{d['name']}** ({d.get('driver_type', '직영')}) | ⭐ {d['rating']} | "
            f"완료 {d['completed_jobs']}건 | 이달 {monthly}건{active_tag}"
        )

with col_right:
    st.subheader("🔔 빠른 메뉴")
    st.page_link("pages/1_배차_스케줄링.py", label="📅 배차/스케줄링", icon="📅")
    st.page_link("pages/2_기사_앱.py", label="📱 실행팀 앱 (사진 필수)", icon="📱")

    # 실행팀/CS는 정산·세무 메뉴 숨김
    if not is_executor() and not is_cs():
        st.page_link("pages/3_정산_엔진.py", label="💵 정산 엔진 (건당수당·Ace Bonus)", icon="💵")
    st.page_link("pages/4_리스크_관리.py", label="⚠️ 리스크 관리 (패널티·적발)", icon="⚠️")
    if not is_executor() and not is_cs():
        st.page_link("pages/5_세무.py", label="🧾 세무 관리", icon="🧾")
    st.page_link("pages/6_설정.py", label="⚙️ 설정", icon="⚙️")
    if not is_executor() and not is_cs():
        st.page_link("pages/7_월간_정산_명세서.py", label="📋 월간 정산 명세서", icon="📋")

show_legal_warning()
