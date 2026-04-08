import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (
    get_drivers, get_orders, add_order, update_order, save_driver,
    get_driver_by_id, next_driver_id, get_settings, get_waiting_executors,
    add_notification, add_journey_notification, mark_notification_sent
)
from utils.footer import show_legal_warning
from utils.masks import mask_phone
from utils.rbac import render_role_selector, is_owner, is_manager, is_executor, is_cs, role_badge
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(page_title="배차/스케줄링 — 순삭 OS", page_icon="📅", layout="wide")
st.title("📅 배차 / 스케줄링")

render_role_selector()

settings = get_settings()
DIRECT_THRESHOLD = settings.get("direct_team_threshold", 40)
HIGH_VALUE_THRESHOLD = 300000
ACCOUNT_WARNING = (
    "\n\n⚠️ 본사 공식 계좌 외 기사에게 직접 현금 지급 시 AS 및 보상이 불가합니다."
)

# ── RBAC 배지 + 권한 안내
st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")
if is_cs():
    st.info(
        "🎧 **CS 모드** — AI가 추천한 **Top 3 기사** 중에서만 배차 확정 가능합니다. "
        "매니저 모니터링·기사 관리 탭은 접근 제한됩니다."
    )
elif is_executor():
    st.warning("🚗 **기사 모드** — 이 페이지는 매니저 전용입니다. 본인 배차 정보는 '기사 앱'에서 확인하세요.")
elif is_manager():
    st.info(
        "👔 **매니저 권한**: 전체 배차 현황 모니터링 + 고단가 건 직접 개입 | "
        "❌ **매니저 제한**: 가격 결정·변경은 CS 초기 확정 금액이 기준이며 임의 변경 불가"
    )


def _driver_recent_jobs_24h(driver_id, orders):
    """최근 24시간 내 완료된 작업 건수"""
    cutoff = datetime.now() - timedelta(hours=24)
    count = 0
    for o in orders:
        if o.get("driver_id") == driver_id and o.get("status") in ("completed", "in_progress"):
            try:
                sched = datetime.strptime(o["scheduled_time"], "%Y-%m-%d %H:%M")
                if sched >= cutoff:
                    count += 1
            except Exception:
                pass
    return count


def _driver_last_job_time(driver_id, orders):
    """기사의 가장 최근 완료 주문 스케줄 시각 반환 (없으면 None)"""
    times = []
    for o in orders:
        if o.get("driver_id") == driver_id and o.get("status") == "completed":
            try:
                t = datetime.strptime(o["scheduled_time"], "%Y-%m-%d %H:%M")
                times.append(t)
            except Exception:
                pass
    return max(times) if times else None


def _driver_needs_rest(driver_id, orders, rest_hours=1):
    """작업 완료 후 rest_hours 이내이면 True (휴식 필요)"""
    last = _driver_last_job_time(driver_id, orders)
    if last is None:
        return False
    elapsed = (datetime.now() - last).total_seconds() / 3600
    return elapsed < rest_hours


def _month_end_urgency_boost(driver: dict) -> int:
    """
    월말 + 직영 + 40건 미달 + 스케줄 열려있음 → 배차 1순위 강제 상향 보너스.
    마지막 10일 이내이면 +50점, 마지막 5일 이내이면 +80점.
    """
    from datetime import date
    import calendar
    today = date.today()
    _, days_in_month = calendar.monthrange(today.year, today.month)
    days_remaining = days_in_month - today.day
    monthly = driver.get("monthly_jobs", 0)
    is_direct = driver.get("driver_type") == "직영"
    if not is_direct or monthly >= DIRECT_THRESHOLD:
        return 0
    if days_remaining <= 5:
        return 80   # 마지막 5일: 강력 상향
    if days_remaining <= 10:
        return 50   # 마지막 10일: 우선 상향
    return 0


def _specialty_bonus(driver: dict, order_work_type: str, avail_drivers: list) -> int:
    """
    가치 기반 배차(Value Dispatch) 전문분야 일치 보너스/페널티.
    - 수거 주문 → 수거 전용팀 +25점 / 철거 전용 -15점
      단, 수거 전용 가용 기사가 0명이면 철거팀 페널티 제거 (폴백)
    - 철거 주문 → 철거/공통 기사 +20점 / 수거 전용 -10점
      단, 철거/공통 가용 기사가 0명이면 수거팀 페널티 제거 (폴백)
    """
    specialty = driver.get("specialty", "공통")
    if order_work_type == "수거":
        coll_avail = [d for d in avail_drivers if d.get("specialty") in ("수거", "공통")]
        if specialty == "수거":
            return 25
        elif specialty == "공통":
            return 0
        else:  # 철거 전용
            return -15 if coll_avail else 0   # 폴백: 수거팀 없으면 페널티 없음
    else:  # 철거
        demo_avail = [d for d in avail_drivers if d.get("specialty") in ("철거", "공통")]
        if specialty == "철거":
            return 20
        elif specialty == "공통":
            return 5
        else:  # 수거 전용
            return -10 if demo_avail else 0   # 폴백


def calc_priority_score(driver, target_work_type, orders=None, rest_hours=1):
    collection = driver.get("collection_jobs", 0)
    demolition = driver.get("demolition_jobs", 0)
    total = collection + demolition
    rating = driver.get("rating", 4.0)
    monthly = driver.get("monthly_jobs", 0)
    if target_work_type == "철거":
        balance_score = (collection / max(total, 1)) * 40
    else:
        balance_score = (demolition / max(total, 1)) * 40
    rating_score = (rating / 5.0) * 40
    active_bonus = 10 if monthly >= DIRECT_THRESHOLD else 0
    # ── 공정성 가중치: 직영팀 보너스 (외주 대비 20점 우위)
    type_bonus = 15 if driver.get("driver_type") == "직영" else 0
    # ── 24시간 내 작업 건수 많을수록 감점 (일감 몰아주기 방지)
    recent_penalty = 0
    if orders is not None:
        recent_24h = _driver_recent_jobs_24h(driver["id"], orders)
        recent_penalty = min(recent_24h * 8, 24)   # 최대 -24점
    # ── 월말 긴급 상향: 직영 + 40건 미달 + 마지막 10일
    urgency_boost = _month_end_urgency_boost(driver)
    return round(balance_score + rating_score + active_bonus + type_bonus + urgency_boost - recent_penalty, 1)


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 자동 배차 (우선순위)",
    "👔 매니저 모니터링",
    "📋 주문 등록",
    "🧑‍✈️ 기사 관리",
    "📊 배차 우선순위 현황",
])

# ──────────────── Tab 1: 자동 배차 ────────────────
with tab1:
    if is_executor():
        st.error("🚫 기사 모드에서는 배차 탭에 접근할 수 없습니다. '기사 앱'을 사용하세요.")
        st.stop()

    st.subheader("자동 배차 추천 — 편식 방지 우선순위 알고리즘")
    st.info(
        "⚖️ **편식 방지 배차:** 저단가(수거) 완료 건수가 많은 기사에게 고단가(철거) 작업 배정 확률이 높아집니다. "
        "점수 = 작업 균형(40) + 평점(40) + 활성 보너스(10)"
    )
    if is_cs():
        st.warning(
            "🎧 **CS 모드 제한** — AI 우선순위 **Top 3** 기사 카드만 표시됩니다. "
            "Top 3 외 기사로의 배차는 매니저 권한이 필요합니다."
        )

    orders = get_orders()
    drivers = get_drivers()
    pending_orders = [o for o in orders if o["status"] == "pending"]

    if not pending_orders:
        st.info("현재 배차 대기 중인 주문이 없습니다.")
    else:
        for order in pending_orders:
            work_type = order.get("work_type", "수거")
            icon = "🔨" if work_type == "철거" else "📦"
            is_high = order["base_fee"] >= HIGH_VALUE_THRESHOLD or work_type == "철거"
            high_tag = " ⚡ 고단가" if is_high else ""
            cs_tag = " 🎧 CS접수" if order.get("cs_confirmed") else ""
            with st.expander(
                f"{icon} 주문 #{order['id']} — {order['customer']} | "
                f"{order['scheduled_time']} | {work_type} | ₩{order['base_fee']:,}{high_tag}{cs_tag}"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**출발지:** {order['pickup']}")
                    st.markdown(f"**목적지:** {order['destination']}")
                    st.markdown(f"**작업 유형:** {'🔨 철거' if work_type == '철거' else '📦 수거'}")
                    if order.get("cs_items"):
                        st.markdown(f"**상담 품목:** {', '.join(order['cs_items'][:4])}")
                with col2:
                    # ※ 가격은 읽기 전용 표시 (매니저 변경 불가)
                    st.markdown(
                        f"**기본요금 (CS 확정가 — 변경 불가):**\n"
                        f"<div style='background:#f8f9fa;padding:6px 10px;border-radius:6px;"
                        f"font-size:20px;font-weight:bold'>₩{order['base_fee']:,}</div>",
                        unsafe_allow_html=True
                    )
                    st.caption("🔒 가격 결정권은 CS에 있습니다. 매니저는 배차 및 모니터링만 가능합니다.")
                    st.markdown(f"**고객 연락처:** {mask_phone(order['customer_phone'], 'manager')}")
                if order.get("cs_memo"):
                    st.info(f"📝 CS 메모: {order['cs_memo']}")

                st.markdown("---")
                is_demo_order = work_type == "철거"
                team_size_needed = order.get("team_size", 1)

                _dispatch_blocked = False
                if is_demo_order:
                    st.info(
                        f"🔨 **철거 건 — 직영팀 우선 배차 적용** | "
                        f"{'👥 ' + str(team_size_needed) + '인 1조 배차 필요' if team_size_needed >= 2 else '1인 배차'}"
                    )
                    if not order.get("manager_quote_confirmed"):
                        st.error(
                            "🚫 **배차 불가 — 매니저 최종 견적 미확정**\n\n"
                            "철거 건은 매니저가 현장 방문 후 최종 견적을 확정해야 배차가 가능합니다. "
                            "**'매니저 모니터링' 탭**에서 견적을 먼저 확정하세요."
                        )
                        _dispatch_blocked = True
                    else:
                        st.success(f"✅ 매니저 확정 견적: ₩{order.get('manager_quote', order['base_fee']):,}")

                if not _dispatch_blocked:
                    st.markdown(
                        f"**📊 추천 기사 — '{work_type}' 작업 우선순위 점수순"
                        f"{'  (직영팀 최우선)' if is_demo_order else ''}**"
                    )

                    try:
                        sched_time = datetime.strptime(order["scheduled_time"], "%Y-%m-%d %H:%M")
                        sched_hour = sched_time.hour
                        sched_min = sched_time.minute
                    except Exception:
                        sched_hour, sched_min = 0, 0

                    # ── 자기주도형 스케줄 Off 기사 제외
                    from utils.schedule import is_driver_blocked_at
                    from data.db import get_driver_schedules
                    _all_schedules = get_driver_schedules()

                    def driver_available_for_order(d):
                        try:
                            from_h, from_m = map(int, d["available_from"].split(":"))
                            to_h, to_m = map(int, d["available_to"].split(":"))
                            sched_mins = sched_hour * 60 + sched_min
                            base_ok = d["available"] and (from_h * 60 + from_m) <= sched_mins <= (to_h * 60 + to_m)
                        except Exception:
                            base_ok = d["available"]
                        if not base_ok:
                            return False
                        # 기사가 스케줄 차단한 시간대면 제외
                        return not is_driver_blocked_at(_all_schedules, d["id"], sched_time)

                    avail_drivers = [d for d in drivers if driver_available_for_order(d)]

                    # ── Off 시간대 차단된 기사 별도 안내
                    _sched_blocked = [
                        d for d in drivers
                        if d["available"] and is_driver_blocked_at(_all_schedules, d["id"], sched_time)
                    ]
                    if _sched_blocked:
                        st.info(
                            f"📅 **스케줄 Off 기사 {len(_sched_blocked)}명 배차 자동 제외** — "
                            f"{', '.join(d['name'] for d in _sched_blocked)} "
                            f"(해당 시간대 휴무 설정)"
                        )

                    rest_hours = settings.get("rest_hours_between_jobs", 1)
                    all_orders_for_rest = orders

                    # ── 무인 자동 페널티: 사진 미업로드 기사 배차 자동 제외
                    from utils.auto_penalty import get_photo_blocked_driver_ids, get_hold_penalty_driver_ids
                    _photo_blocked = get_photo_blocked_driver_ids(orders)
                    _hold_penalty_ids = get_hold_penalty_driver_ids(orders)

                    photo_blocked_drivers = [d for d in avail_drivers if d["id"] in _photo_blocked]
                    avail_drivers = [d for d in avail_drivers if d["id"] not in _photo_blocked]

                    if photo_blocked_drivers:
                        st.warning(
                            f"📸 **사진 미업로드 기사 {len(photo_blocked_drivers)}명 배차 자동 제외** — "
                            f"{', '.join(d['name'] for d in photo_blocked_drivers)} "
                            f"(진행 중 작업 전 사진 업로드 필요)"
                        )

                    def driver_in_rest(d):
                        return _driver_needs_rest(d["id"], all_orders_for_rest, rest_hours)

                    # ── Value Dispatch: 전문분야 일치 기사 현황 안내
                    _spec_match = [d for d in avail_drivers if d.get("specialty") == work_type]
                    _spec_common = [d for d in avail_drivers if d.get("specialty") == "공통"]
                    _spec_other = [d for d in avail_drivers if d.get("specialty") not in (work_type, "공통")]
                    if _spec_match:
                        spec_icon = "📦" if work_type == "수거" else "🔨"
                        st.success(
                            f"{spec_icon} **{work_type} 전문팀 우선 배차** — "
                            f"전문 기사 {len(_spec_match)}명 (공통 {len(_spec_common)}명) 우선 배정 | "
                            f"{'철거' if work_type == '수거' else '수거'} 전문팀 {len(_spec_other)}명 대기 순위"
                        )

                    if is_demo_order:
                        def demo_sort_key(d):
                            is_direct = 1 if d.get("driver_type") == "직영" else 0
                            is_resting = 0 if driver_in_rest(d) else 1
                            score = calc_priority_score(d, work_type, all_orders_for_rest, rest_hours)
                            hold_penalty = -30 if d["id"] in _hold_penalty_ids else 0
                            spec_b = _specialty_bonus(d, work_type, avail_drivers)
                            return (is_resting, is_direct, score + hold_penalty + spec_b)
                        available = sorted(avail_drivers, key=demo_sort_key, reverse=True)
                    else:
                        def collect_sort_key(d):
                            is_resting = 0 if driver_in_rest(d) else 1
                            score = calc_priority_score(d, work_type, all_orders_for_rest, rest_hours)
                            hold_penalty = -30 if d["id"] in _hold_penalty_ids else 0
                            spec_b = _specialty_bonus(d, work_type, avail_drivers)
                            return (is_resting, score + hold_penalty + spec_b)
                        available = sorted(avail_drivers, key=collect_sort_key, reverse=True)

                    unavailable = [d for d in drivers if not driver_available_for_order(d)]

                    if not available:
                        st.warning("가용 기사 없음")
                    else:
                        cols = st.columns(min(len(available), 3))
                        for idx, d in enumerate(available[:3]):
                            with cols[idx]:
                                medal = ["🥇", "🥈", "🥉"][idx]
                                monthly = d.get("monthly_jobs", 0)
                                recent_24h = _driver_recent_jobs_24h(d["id"], all_orders_for_rest)
                                is_resting = driver_in_rest(d)
                                active_tag = "🔥 활성" if monthly >= DIRECT_THRESHOLD else ""
                                direct_badge = "🏢 직영" if d.get("driver_type") == "직영" else "🔗 외부"
                                _d_spec = d.get("specialty", "공통")
                                _d_spec_icon = {"수거": "📦", "철거": "🔨", "공통": "⚖️"}.get(_d_spec, "⚖️")
                                spec_badge = f"{_d_spec_icon} {_d_spec}전문" if _d_spec != "공통" else ""
                                priority_score = calc_priority_score(d, work_type, all_orders_for_rest, rest_hours)
                                st.markdown(f"### {medal} {d['name']} {direct_badge} {spec_badge} {active_tag}")
                                if is_resting:
                                    st.warning(f"😴 **휴식 보장 중** — 최근 완료 후 {rest_hours}시간 미경과. 배차 가능하나 권장하지 않음")
                                st.markdown(f"⭐ **{d['rating']}점**")
                                st.markdown(f"🏆 우선순위: **{priority_score}점**")
                                if recent_24h > 0:
                                    st.caption(f"⚠️ 24시간 내 {recent_24h}건 (가중치 -{min(recent_24h*8,24)}점)")
                                col_j = st.columns(2)
                                with col_j[0]:
                                    st.caption(f"수거 {d.get('collection_jobs', 0)}건")
                                with col_j[1]:
                                    st.caption(f"철거 {d.get('demolition_jobs', 0)}건")
                                st.markdown(f"이달 {monthly}건 | 누적 {d['completed_jobs']}건")
                                st.markdown(f"가용 {d['available_from']}~{d['available_to']}")

                                if is_demo_order and team_size_needed >= 2:
                                    st.caption("👥 2인 1조 배차 — 보조 기사도 선택하세요")
                                    other_drivers = [x for x in available if x["id"] != d["id"]]
                                    second_options = ["(보조 기사 선택)"] + [x["name"] for x in other_drivers[:5]]
                                    second_choice = st.selectbox(
                                        "보조 기사",
                                        second_options,
                                        key=f"second_{order['id']}_{d['id']}"
                                    )
                                    second_driver = next(
                                        (x for x in other_drivers if x["name"] == second_choice), None
                                    )
                                    if st.button("👥 2인 배차 확정", key=f"assign_{order['id']}_{d['id']}"):
                                        confirmed_price = order.get("manager_quote") if order.get("manager_quote_confirmed") else order["base_fee"]
                                        update_order(order["id"], {
                                            "driver_id": d["id"],
                                            "second_driver_id": second_driver["id"] if second_driver else None,
                                            "status": "dispatched",
                                            "base_fee": confirmed_price,
                                        })
                                        team_str = f"{d['name']}" + (f" + {second_driver['name']}" if second_driver else "")
                                        dispatch_msg = (
                                            f"[순삭 본사] {order['customer']}님, 철거 작업팀({team_str})이 배정되었습니다.\n"
                                            f"작업 일시: {order['scheduled_time']}\n"
                                            f"확정 견적: ₩{confirmed_price:,}\n"
                                            f"문의사항은 본사로 연락 주세요."
                                            + ACCOUNT_WARNING
                                        )
                                        add_notification({
                                            "order_id": order["id"],
                                            "customer": order["customer"],
                                            "customer_phone": order["customer_phone"],
                                            "type": "기사배정완료",
                                            "message": dispatch_msg,
                                            "sender": "순삭 본사 시스템",
                                        })
                                        add_journey_notification({
                                            "order_id": order["id"],
                                            "customer": order["customer"],
                                            "customer_phone": order["customer_phone"],
                                            "type": "🚗 기사 배정 완료",
                                            "message": dispatch_msg,
                                        })
                                        mark_notification_sent(order["id"], "notif_dispatched")
                                        st.success(f"✅ {team_str} {team_size_needed}인 배차 완료!")
                                        st.rerun()
                                else:
                                    if st.button("배차 확정", key=f"assign_{order['id']}_{d['id']}"):
                                        confirmed_price = order.get("manager_quote") if order.get("manager_quote_confirmed") else order["base_fee"]
                                        update_order(order["id"], {
                                            "driver_id": d["id"],
                                            "status": "dispatched",
                                            "base_fee": confirmed_price,
                                        })
                                        dispatch_msg = (
                                            f"[순삭 본사] {order['customer']}님, 담당 작업팀이 배정되었습니다.\n"
                                            f"작업 일시: {order['scheduled_time']}\n"
                                            f"문의사항은 본사로 연락 주세요."
                                            + ACCOUNT_WARNING
                                        )
                                        add_notification({
                                            "order_id": order["id"],
                                            "customer": order["customer"],
                                            "customer_phone": order["customer_phone"],
                                            "type": "기사배정완료",
                                            "message": dispatch_msg,
                                            "sender": "순삭 본사 시스템",
                                        })
                                        add_journey_notification({
                                            "order_id": order["id"],
                                            "customer": order["customer"],
                                            "customer_phone": order["customer_phone"],
                                            "type": "🚗 기사 배정 완료",
                                            "message": dispatch_msg,
                                        })
                                        mark_notification_sent(order["id"], "notif_dispatched")
                                        st.success(f"✅ {d['name']} 기사 배차 완료!")
                                        st.rerun()

                if unavailable:
                    with st.expander("🔴 가용 불가 기사"):
                        for d in unavailable:
                            st.markdown(f"- {d['name']} ({d['available_from']}~{d['available_to']})")

    st.divider()
    st.subheader("📋 전체 배차 현황 — 실시간 이동/작업 상태")

    def realtime_status(o):
        """출발/도착 데이터로 실시간 상태 아이콘 결정"""
        s = o.get("status", "")
        dep = o.get("departed_at")
        arr = o.get("arrived_at")
        delay_min = o.get("departure_delay_minutes")
        if s == "pending":
            return "⏳ 대기"
        if s == "dispatched":
            return "📍 배차완료"
        if s == "in_progress":
            if dep and not arr:
                base = "🚗 이동 중"
                if delay_min is not None and delay_min >= 30:
                    base += f" 🔴 {delay_min}분 지연!"
                return base
            if dep and arr:
                base = "🔨 작업 중"
                delay_min2 = o.get("departure_delay_minutes")
                if delay_min2 is not None and delay_min2 >= 30:
                    base += f" 🔴 {delay_min2}분 지연"
                return base
            return "🔄 진행중"
        if s == "completed":
            return "✅ 완료"
        if s == "cancelled":
            return "❌ 취소"
        return s

    rows = []
    delay_alerts = []
    for o in sorted(orders, key=lambda x: x["scheduled_time"], reverse=True):
        drv = get_driver_by_id(o.get("driver_id"))
        dep_at = o.get("departed_at")
        dep_display = dep_at[11:16] if dep_at else "—"
        arr_at = o.get("arrived_at")
        arr_display = arr_at[11:16] if arr_at else "—"
        delay_min = o.get("departure_delay_minutes")

        if delay_min is not None and delay_min >= 30 and o["status"] != "completed":
            delay_alerts.append({
                "id": o["id"],
                "customer": o["customer"],
                "driver": drv["name"] if drv else "?",
                "delay_min": delay_min,
            })

        exp_min = o.get("expected_travel_min")
        actual_min = o.get("actual_travel_min")

        if exp_min and actual_min:
            from utils.maps import efficiency_label as _eff
            eff_str, _ = _eff(exp_min, actual_min)
        elif actual_min is not None:
            eff_str = f"실제 {actual_min}분"
        elif exp_min is not None:
            eff_str = f"예상 {exp_min}분"
        else:
            eff_str = "—"

        # 지연 패널티 자동 분류
        delay_flag = o.get("delay_flag", False)
        actual_travel = o.get("actual_travel_min")
        photo_before_at = o.get("photo_before_at")
        penalty_label = "—"
        if o["status"] == "completed":
            penalty_label = "✅ 정상 완료"
        elif delay_flag and actual_travel is not None and actual_travel >= 30:
            penalty_label = f"🔴 패널티 대상 ({actual_travel}분)"
        elif actual_travel is not None:
            penalty_label = f"🟢 정상 ({actual_travel}분)"
        elif photo_before_at and dep_at:
            try:
                from datetime import datetime as _dt
                dep_dt2 = _dt.strptime(dep_at, "%Y-%m-%d %H:%M:%S")
                arr_dt2 = _dt.strptime(photo_before_at, "%Y-%m-%d %H:%M:%S")
                mins = int((arr_dt2 - dep_dt2).total_seconds() / 60)
                penalty_label = f"{'🔴 패널티' if mins >= 30 else '🟢 정상'} ({mins}분)"
            except Exception:
                pass

        rows.append({
            "주문": f"#{o['id']}",
            "고객": o["customer"],
            "작업": "🔨 철거" if o.get("work_type") == "철거" else "📦 수거",
            "기사": drv["name"] if drv else "미배차",
            "예약": o["scheduled_time"],
            "기본요금": f"₩{o['base_fee']:,}",
            "실시간 상태": realtime_status(o),
            "출발": dep_display,
            "도착(사진)": photo_before_at[11:16] if photo_before_at else arr_display,
            "예상(분)": str(exp_min) if exp_min is not None else "—",
            "실제(분)": str(actual_min) if actual_min is not None else "—",
            "이동 효율": eff_str,
            "지연 패널티": penalty_label,
            "사진": "✅" if (o.get("photo_before") and o.get("photo_after")) else "⚠️",
            "현장보고": "🚨" if o.get("field_report") else "—",
        })

    if delay_alerts:
        st.markdown("---")
        st.markdown("#### 🔴 지연 패널티 대상 목록")
        for alert in delay_alerts:
            st.error(
                f"🔴 **지연 패널티 대상** — 주문 #{alert['id']} ({alert['customer']}) | "
                f"기사 **{alert['driver']}** | 이동 시간 **{alert['delay_min']}분** "
                f"(계약 기준 30분 초과) | **정산 시 수당 자동 차감**"
            )

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ──────────────── Tab 2: 매니저 모니터링 ────────────────
with tab2:
    if is_cs() or is_executor():
        st.error("🚫 **접근 권한 없음** — 매니저 모니터링 탭은 매니저/대표 전용입니다.")
        st.stop()

    st.subheader("👔 매니저 모니터링 — 고단가 건 직접 개입")
    st.warning(
        "🔒 **가격 변경 권한 없음** — 이 탭에서 매니저는 현황 모니터링 및 고단가 상담 개입만 가능합니다. "
        "가격 결정은 CS가 확정한 기준가를 따릅니다."
    )

    orders = get_orders()
    drivers = get_drivers()

    # ── 기사 실시간 영업/휴무 현황 (관리자 대시보드)
    from utils.schedule import get_current_driver_status
    from data.db import get_driver_schedules
    _all_scheds = get_driver_schedules()
    st.subheader("🗺️ 기사 실시간 영업 현황")
    _status_cols = st.columns(min(len(drivers), 4))
    for _i, _drv in enumerate(drivers):
        _status = get_current_driver_status(_all_scheds, _drv)
        _is_on = _status["status"] == "영업중"
        _color = "#e8f5e9" if _is_on else "#ffebee"
        _border = "#2e7d32" if _is_on else "#c62828"
        _icon = "🟢" if _is_on else "🔴"
        _col_i = _i % min(len(drivers), 4)
        with _status_cols[_col_i]:
            st.markdown(
                f"<div style='background:{_color};border-left:4px solid {_border};"
                f"padding:8px 12px;border-radius:6px;margin-bottom:8px'>"
                f"<b>{_icon} {_drv['name']}</b><br>"
                f"<span style='font-size:12px;color:#555'>{_status['status']}</span>"
                + (f"<br><span style='font-size:11px;color:#888'>{_status['reason']}</span>" if _status.get('reason') else "")
                + (f"<br><span style='font-size:11px;color:#1565c0'>{_status['until']}</span>" if _status.get('until') else "")
                + "</div>",
                unsafe_allow_html=True,
            )
    # ── 기사 휴무 설정 이력 로그 (무단 이탈 방지)
    from data.db import get_schedule_logs
    _sched_logs = get_schedule_logs()
    if _sched_logs:
        with st.expander(f"📋 기사 휴무 설정 이력 ({len(_sched_logs)}건) — 무단 이탈 방지 로그", expanded=False):
            _log_rows = []
            for _lg in reversed(_sched_logs[-50:]):
                _did = _lg.get("driver_id")
                _d = next((x for x in drivers if x["id"] == _did), None)
                _action_label = "차단 등록" if _lg.get("action") == "block_added" else "차단 해제"
                _btype = "전일 휴무" if _lg.get("is_all_day") else (
                    f"{_lg.get('start_hour',0):02d}:00~{_lg.get('end_hour',0):02d}:00"
                )
                _log_rows.append({
                    "시각": _lg.get("logged_at", "—"),
                    "기사": _d["name"] if _d else f"ID:{_did}",
                    "액션": _action_label,
                    "날짜": _lg.get("date", "—"),
                    "유형": _btype,
                    "사유": _lg.get("reason", "—"),
                    "역할": _lg.get("role", "—"),
                })
            if _log_rows:
                import pandas as _pdlog
                st.dataframe(_pdlog.DataFrame(_log_rows), use_container_width=True, hide_index=True)
    # ── 근태 불량 자동 감지 & 대표 카톡 알림 ──────────────────────────────────
    import calendar as _mgrcal
    from datetime import date as _mgrdate
    _today_mgr = _mgrdate.today()
    if _today_mgr.day >= 15:   # 15일 이후에만 체크
        from utils.schedule import get_monthly_block_count
        from utils.notifications import notify_poor_attendance
        _year_month = _today_mgr.strftime("%Y-%m")
        _poor_drivers = []
        for _drv in drivers:
            if _drv.get("driver_type") != "직영":
                continue
            _mjobs = _drv.get("monthly_jobs", 0)
            if _mjobs >= DIRECT_THRESHOLD * 0.30:
                continue
            _blk_cnt = get_monthly_block_count(get_driver_schedules(), _drv["id"], _year_month)
            if _blk_cnt < 5:
                continue
            _poor_drivers.append({"driver": _drv, "jobs": _mjobs, "blocks": _blk_cnt})

        if _poor_drivers:
            st.subheader("⚠️ 근태 불량 감지 — 의무 면담 필요")
            for _pd_item in _poor_drivers:
                _pd_drv = _pd_item["driver"]
                _pd_jobs = _pd_item["jobs"]
                _pd_blks = _pd_item["blocks"]
                _attain = round(_pd_jobs / DIRECT_THRESHOLD * 100, 1)
                with st.container():
                    _warn_c1, _warn_c2 = st.columns([3, 1])
                    with _warn_c1:
                        st.markdown(
                            f"<div style='background:#fff3e0;border-left:4px solid #e65100;"
                            f"padding:10px 14px;border-radius:6px;margin-bottom:8px'>"
                            f"<b>🚨 {_pd_drv['name']}</b> — 달성률 {_attain}% ({_pd_jobs}/{DIRECT_THRESHOLD}건) "
                            f"| 이달 Off 차단 {_pd_blks}회<br>"
                            f"<span style='font-size:12px;color:#bf360c'>"
                            f"15일 경과 + 달성률 30% 미달 + 잦은 Off → 의무 면담 필요</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    with _warn_c2:
                        if st.button(f"📲 카톡 알림 발송", key=f"poor_notif_{_pd_drv['id']}"):
                            _nr = notify_poor_attendance(_pd_drv, _pd_jobs, DIRECT_THRESHOLD, _pd_blks)
                            if _nr.get("success"):
                                st.success("✅ 대표 카톡 알림 발송 완료")
                            else:
                                st.warning(f"⚠️ 알림 미발송 (웹훅 미설정): {_nr.get('error','—')}")

    st.divider()

    # 현장 상황 보고 알림
    field_reports = [o for o in orders if o.get("field_report")]
    if field_reports:
        st.error(f"🚨 현장 상황 보고 {len(field_reports)}건 — 즉시 검토 필요!")
        for o in field_reports:
            fr = o.get("field_report", {})
            drv = get_driver_by_id(o.get("driver_id"))
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"**주문 #{o['id']} — {o['customer']}** | "
                    f"{o.get('work_type','수거')} | ₩{o['base_fee']:,}\n\n"
                    f"기사: {drv['name'] if drv else '—'} | 보고: **{fr.get('description','—')}**\n\n"
                    f"보고 시각: {fr.get('reported_at','—')}"
                )
            with col2:
                if st.button("📞 CS 에스컬레이션 완료", key=f"mgr_esc_{o['id']}"):
                    updated_fr = dict(fr)
                    updated_fr["manager_reviewed"] = True
                    updated_fr["manager_reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    update_order(o["id"], {"field_report": updated_fr})
                    st.success("에스컬레이션 처리 완료")
                    st.rerun()
        st.divider()

    # 고단가 건
    high_value_orders = [
        o for o in orders
        if (o["base_fee"] >= HIGH_VALUE_THRESHOLD or o.get("work_type") == "철거")
        and o["status"] not in ("cancelled",)
    ]
    st.subheader(f"⚡ 고단가 / 철거 건 ({len(high_value_orders)}건)")
    st.caption(f"₩{HIGH_VALUE_THRESHOLD:,} 이상 또는 철거 작업 — 매니저 직접 개입 가능")

    if not high_value_orders:
        st.info("현재 고단가 건이 없습니다.")
    else:
        for o in sorted(high_value_orders, key=lambda x: x["base_fee"], reverse=True):
            drv = get_driver_by_id(o.get("driver_id"))
            status_map_local = {
                "pending": "⏳ 대기", "dispatched": "📍 배차완료",
                "in_progress": "🔄 진행중", "completed": "✅ 완료",
            }
            already_intervened = o.get("manager_closed")
            with st.expander(
                f"{'👔✅' if already_intervened else '👔'} 주문 #{o['id']} — {o['customer']} | "
                f"{o.get('work_type','수거')} | ₩{o['base_fee']:,} | "
                f"{status_map_local.get(o['status'], o['status'])}"
            ):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**고객:** {o['customer']}")
                    st.markdown(f"**연락처:** {mask_phone(o['customer_phone'], 'admin')}")
                    st.markdown(f"**현장:** {o['pickup']}")
                with col2:
                    st.markdown(f"**기본요금 (CS 확정가):**")
                    st.markdown(
                        f"<div style='font-size:22px;font-weight:bold;color:#1a1a1a'>"
                        f"₩{o['base_fee']:,}</div>",
                        unsafe_allow_html=True
                    )
                    st.caption("🔒 변경 불가 — CS 확정가")
                    st.markdown(f"**기사:** {drv['name'] if drv else '미배차'}")
                with col3:
                    st.markdown(f"**예약:** {o['scheduled_time']}")
                    if o.get("cs_memo"):
                        st.info(f"CS 메모: {o['cs_memo']}")
                    if o.get("cs_items"):
                        st.markdown(f"**품목:** {', '.join(o['cs_items'][:3])}")

                # ──── 철거 건 전용: 매니저 견적 확정 ────
                if o.get("work_type") == "철거":
                    st.markdown("---")
                    st.markdown("#### 🔨 철거 건 현장 조건")
                    dc1, dc2, dc3 = st.columns(3)
                    with dc1:
                        st.markdown(f"**범위:** {o.get('demolition_scope','—')}")
                        st.markdown(f"**면적:** {o.get('demolition_area','—')}평")
                        st.markdown(f"**층수:** {o.get('floor_number','—')}층")
                    with dc2:
                        st.markdown(f"**엘리베이터:** {'✅' if o.get('has_elevator') else '❌ 없음'}")
                        st.markdown(f"**사다리차:** {'🚛 필요' if o.get('has_ladder_car') else '불필요'}")
                        st.markdown(f"**팀 구성:** 👥 {o.get('team_size',1)}인 1조")
                    with dc3:
                        wt = o.get("waste_types", [])
                        st.markdown(f"**폐기물:** {', '.join(wt) if wt else '—'}")
                        if o.get("has_asbestos"):
                            st.error("☢️ 석면 의심 — 특수 처리 필요!")
                        else:
                            st.markdown("**석면:** 해당없음")
                        st.markdown(f"**CS 기초 견적:** ₩{o['base_fee']:,}")

                    # ──── 견적 사진 업로드 (현장 3장 이상 필수) ────
                    PHOTO_REQUIRED = 3
                    st.markdown(f"#### 📸 현장 견적 사진 업로드 (필수: **{PHOTO_REQUIRED}장 이상**)")
                    _est_photos = list(o.get("estimate_photos", []))
                    # 구버전 단일 사진 마이그레이션
                    if not _est_photos and o.get("estimate_photo_path") and os.path.exists(o["estimate_photo_path"]):
                        _est_photos = [o["estimate_photo_path"]]

                    _photo_count = len(_est_photos)
                    if _photo_count >= PHOTO_REQUIRED:
                        st.success(f"✅ 현장 사진 {_photo_count}장 업로드 완료 — 견적 확정 가능")
                    else:
                        remaining_photos = PHOTO_REQUIRED - _photo_count
                        st.warning(
                            f"⚠️ 현장 사진 {_photo_count}장 업로드됨 — "
                            f"**{remaining_photos}장 추가 필요** (최소 {PHOTO_REQUIRED}장 이상이어야 견적 확정 가능)"
                        )

                    # 업로드된 사진 미리보기
                    if _est_photos:
                        _ph_cols = st.columns(min(len(_est_photos), 5))
                        for _pi, _ep in enumerate(_est_photos):
                            with _ph_cols[_pi]:
                                if os.path.exists(_ep):
                                    st.image(_ep, caption=f"현장사진 {_pi+1}", use_container_width=True)
                                    if st.button("🗑️", key=f"est_del_{o['id']}_{_pi}", help="이 사진 삭제"):
                                        _new_photos = [p for i, p in enumerate(_est_photos) if i != _pi]
                                        update_order(o["id"], {
                                            "estimate_photos": _new_photos,
                                            "estimate_photo_path": _new_photos[0] if _new_photos else None,
                                        })
                                        st.rerun()

                    # 추가 사진 업로드
                    if _photo_count < 5:
                        est_files = st.file_uploader(
                            f"현장 사진 추가 (JPG/PNG, 현재 {_photo_count}장 / 최대 5장)",
                            type=["jpg", "jpeg", "png"],
                            accept_multiple_files=True,
                            key=f"est_photo_{o['id']}",
                        )
                        if est_files and st.button("📤 사진 저장", key=f"est_save_{o['id']}"):
                            from utils.ai_vision import save_photo
                            _saved = list(_est_photos)
                            for _ef in est_files:
                                if len(_saved) >= 5:
                                    break
                                ext = _ef.name.rsplit(".", 1)[-1].lower()
                                path = save_photo(o["id"], f"estimate_{len(_saved)}", _ef.read(), ext)
                                _saved.append(path)
                            update_order(o["id"], {
                                "estimate_photos": _saved,
                                "estimate_photo_path": _saved[0] if _saved else None,
                            })
                            st.success(f"✅ {len(est_files)}장 저장 완료! (총 {len(_saved)}장)")
                            st.rerun()

                    _quote_unlocked = _photo_count >= PHOTO_REQUIRED
                    st.markdown("#### 💰 매니저 최종 견적 확정")
                    if not _quote_unlocked:
                        st.error(
                            f"🔒 **견적 확정 잠금** — 현장 사진 {PHOTO_REQUIRED}장 이상 업로드 후 활성화됩니다. "
                            f"(현재 {_photo_count}장)"
                        )
                    if o.get("manager_quote_confirmed"):
                        st.success(
                            f"✅ **견적 확정 완료** — 확정 견적: ₩{o.get('manager_quote', 0):,} "
                            f"| 발송: {'✅ 발송됨' if o.get('manager_quote_sent') else '⏳ 발송 전'}"
                        )
                    elif _quote_unlocked:
                        col_q1, col_q2 = st.columns([2, 1])
                        with col_q1:
                            _quote_val = int(o.get("manager_quote") or o["base_fee"])
                            mgr_quote_val = st.number_input(
                                "최종 견적 금액 (매니저 확정) *",
                                min_value=min(10000, _quote_val),
                                max_value=10000000,
                                value=_quote_val,
                                step=50000,
                                key=f"mgr_quote_{o['id']}"
                            )
                            st.caption(
                                f"CS 기초 견적 ₩{o['base_fee']:,} 기준 | "
                                f"확정 후 고객에게 공식 견적서 알림톡이 자동 발송됩니다"
                            )
                        with col_q2:
                            if st.button("✅ 견적 확정 & 발송", key=f"mgr_quote_confirm_{o['id']}", type="primary"):
                                quote_msg = (
                                    f"[순삭 본사] {o['customer']}님, 철거 공식 견적서를 안내드립니다. 📋\n\n"
                                    f"■ 철거 범위: {o.get('demolition_scope','—')}\n"
                                    f"■ 면적: {o.get('demolition_area','—')}평 / {o.get('floor_number','—')}층\n"
                                    f"■ 팀 구성: {o.get('team_size',1)}인 1조\n"
                                    f"■ 폐기물 처리: {', '.join(o.get('waste_types', []))}\n\n"
                                    f"■ **최종 확정 견적: ₩{mgr_quote_val:,}**\n\n"
                                    f"본 견적에 동의하시면 회신 부탁드립니다.\n"
                                    f"감사합니다. 순삭 본사 드림"
                                )
                                update_order(o["id"], {
                                    "manager_quote": int(mgr_quote_val),
                                    "manager_quote_confirmed": True,
                                    "manager_quote_sent": True,
                                    "manager_closed": True,
                                    # ↓ 정산 엔진 기준가 동기화: manager_quote가 곧 확정 매출
                                    "base_fee": int(mgr_quote_val),
                                })
                                add_notification({
                                    "order_id": o["id"],
                                    "customer": o["customer"],
                                    "customer_phone": o["customer_phone"],
                                    "type": "철거_견적서",
                                    "message": quote_msg,
                                    "sender": "순삭 본사 시스템",
                                })
                                add_journey_notification({
                                    "order_id": o["id"],
                                    "customer": o["customer"],
                                    "customer_phone": o["customer_phone"],
                                    "type": "📋 철거 견적서 발송",
                                    "message": quote_msg,
                                })
                                mark_notification_sent(o["id"], "notif_reserved")
                                st.success(f"✅ 견적 ₩{mgr_quote_val:,} 확정! 고객에게 공식 견적서 알림톡 발송 완료!")
                                st.rerun()

                st.markdown("---")
                # 매니저 직접 상담 개입 처리
                if already_intervened:
                    st.success("✅ 매니저 직접 개입 완료 — 인센티브 정산 대상")
                else:
                    if o["status"] == "completed":
                        st.info("완료된 건입니다. 매니저 개입 여부를 확인하세요.")
                        if st.button("👔 이 건 매니저 직접 성사 처리", key=f"mgr_close_{o['id']}"):
                            update_order(o["id"], {"manager_closed": True})
                            st.success("✅ 매니저 직접 성사 처리 완료! 인센티브 정산에 반영됩니다.")
                            st.rerun()
                    elif o["status"] in ("pending", "dispatched", "in_progress"):
                        with st.expander("📞 매니저 직접 상담 개입"):
                            mgr_note = st.text_area(
                                "상담 개입 내용",
                                placeholder="고객과 직접 통화 후 확인한 내용 기록...",
                                key=f"mgr_note_{o['id']}"
                            )
                            if st.button("👔 직접 상담 개입 완료 처리", key=f"mgr_intervene_{o['id']}"):
                                update_order(o["id"], {
                                    "manager_closed": True,
                                    "cs_memo": (o.get("cs_memo", "") + f"\n[매니저 개입] {mgr_note}").strip()
                                })
                                st.success("✅ 매니저 직접 개입 처리 완료!")
                                st.rerun()

    st.divider()

    # 전체 배차 현황 (읽기 전용)
    st.subheader("📊 전체 배차 현황 (읽기 전용)")
    status_map2 = {
        "pending": "⏳ 대기", "dispatched": "📍 배차완료",
        "in_progress": "🔄 진행중", "completed": "✅ 완료", "cancelled": "❌ 취소",
    }
    rows2 = []
    for o in sorted(orders, key=lambda x: x["scheduled_time"], reverse=True):
        drv = get_driver_by_id(o.get("driver_id"))
        rows2.append({
            "주문": f"#{o['id']}",
            "고객": o["customer"],
            "작업": "🔨 철거" if o.get("work_type") == "철거" else "📦 수거",
            "기사": drv["name"] if drv else "미배차",
            "예약": o["scheduled_time"],
            "기본요금(CS확정)": f"₩{o['base_fee']:,}",
            "상태": status_map2.get(o["status"], o["status"]),
            "CS접수": "🎧" if o.get("cs_confirmed") else "—",
            "매니저개입": "👔" if o.get("manager_closed") else "—",
            "현장보고": "🚨" if o.get("field_report") else "—",
            "사진": "✅" if (o.get("photo_before") and o.get("photo_after")) else "⚠️",
        })
    if rows2:
        st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)

# ──────────────── Tab 3: 주문 등록 (비상용) ────────────────
with tab3:
    st.subheader("신규 주문 등록 (비상 직접 등록)")
    st.info("💡 정상적인 신규 주문은 **CS 상담센터**에서 접수하세요. 이 탭은 비상 상황 전용입니다.")
    with st.form("new_order_form"):
        col1, col2 = st.columns(2)
        with col1:
            customer = st.text_input("고객명", placeholder="홍길동")
            customer_phone = st.text_input("고객 연락처", placeholder="010-0000-0000")
            pickup = st.text_input("출발지 주소", placeholder="서울 강남구 역삼동 123")
            work_type = st.selectbox("작업 유형", ["수거", "철거"])
        with col2:
            destination = st.text_input("목적지 주소", placeholder="서울 서초구 반포동 456")
            scheduled_time = st.text_input("예약 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M"))
            base_fee = st.number_input("기본요금 (원)", min_value=0, step=5000, value=50000)

        submitted = st.form_submit_button("📝 주문 등록", type="primary")
        if submitted:
            if not all([customer, customer_phone, pickup, destination]):
                st.error("모든 항목을 입력해주세요.")
            else:
                order_id = add_order({
                    "customer": customer,
                    "customer_phone": customer_phone,
                    "pickup": pickup,
                    "destination": destination,
                    "scheduled_time": scheduled_time,
                    "driver_id": None,
                    "status": "pending",
                    "base_fee": int(base_fee),
                    "extra_fee": 0,
                    "extra_fee_status": None,
                    "payment_confirmed": False,
                    "work_type": work_type,
                    "cs_confirmed": False,
                    "manager_closed": False,
                })
                st.success(f"✅ 주문 #{order_id} ({work_type}) 등록 완료!")
                st.rerun()

# ──────────────── Tab 4: 기사 관리 ────────────────
with tab4:
    if is_cs() or is_executor():
        st.error("🚫 **접근 권한 없음** — 기사 관리 탭은 매니저/대표 전용입니다.")
        st.stop()

    st.subheader("기사 등록 / 수정")
    drivers = get_drivers()

    with st.expander("➕ 신규 기사 등록"):
        st.caption("* 표시는 필수 입력 항목입니다.")
        with st.form("new_driver_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("이름 *")
                phone = st.text_input("연락처 *", placeholder="010-0000-0000")
                license_type = st.selectbox("면허 종류", ["1종보통", "2종보통", "1종대형"])
                driver_type = st.selectbox("기사 유형", ["직영", "외부"])
            with col2:
                avail_from = st.text_input("가용 시작", value="08:00")
                avail_to = st.text_input("가용 종료", value="20:00")
                available = st.checkbox("현재 가용 상태", value=True)
                monthly_jobs = st.number_input("이달 완료 건수", min_value=0, value=0)

            st.divider()
            st.markdown("**🎯 전문분야 및 담당 지역**")
            spec_reg_col1, spec_reg_col2 = st.columns(2)
            with spec_reg_col1:
                driver_specialty = st.selectbox(
                    "전문분야 *",
                    ["공통", "수거", "철거"],
                    help=(
                        "수거: 수거 작업 전용 (수거 주문 시 최우선 배차)\n"
                        "철거: 철거 작업 전용 (철거 주문 시 최우선 배차)\n"
                        "공통: 두 유형 모두 배차 가능"
                    ),
                )
            with spec_reg_col2:
                _drv_regions = settings.get("regions", ["본사", "세종"])
                driver_region = st.selectbox(
                    "담당 지역 *",
                    _drv_regions,
                    help="세종 지역 수거 전용 기사는 '수거' + '세종' 조합으로 설정",
                )
            if driver_specialty == "수거":
                st.info("📦 **수거 전용** — 수거 주문 발생 시 +25점 우선 배차 보너스 자동 적용. 철거 주문 시 대기 순위 하향.")
            elif driver_specialty == "철거":
                st.info("🔨 **철거 전용** — 철거 주문 발생 시 +20점 우선 배차 보너스 자동 적용. 수거 주문 시 대기 순위 하향.")
            else:
                st.info("⚖️ **공통** — 수거/철거 모두 중립 배차 대상입니다.")

            st.divider()
            st.markdown("**💼 정산 세무 유형 (필수)**")
            tax_type_label = st.selectbox(
                "정산 유형 *",
                ["개인(3.3%)", "사업자(부가세 포함)"],
                help="개인: 3.3% 원천세 공제 후 실지급 | 사업자: 공급가 + 부가세 분리, 총 지급액 고정"
            )
            tax_type = "business" if "사업자" in tax_type_label else "individual"

            biz_cols = st.columns(3)
            with biz_cols[0]:
                business_reg_no = st.text_input(
                    "사업자등록번호",
                    placeholder="000-00-00000",
                    disabled=(tax_type == "individual"),
                )
            with biz_cols[1]:
                business_type = st.text_input(
                    "업태",
                    placeholder="예: 운수업",
                    disabled=(tax_type == "individual"),
                )
            with biz_cols[2]:
                business_category = st.text_input(
                    "종목",
                    placeholder="예: 화물운송",
                    disabled=(tax_type == "individual"),
                )

            if tax_type == "individual":
                st.info("👤 **개인(3.3%)** — 지급 시 사업소득세 3% + 지방소득세 0.3% 자동 공제")
            else:
                st.info("🏢 **사업자(부가세 포함)** — 총 지급액 = Base 고정 (공급가 + 부가세 분리, 추가 부가세 지급 없음)")

            submitted = st.form_submit_button("등록", type="primary")
            if submitted:
                if not name or not phone:
                    st.error("이름과 연락처는 필수 입력입니다.")
                elif tax_type == "business" and not business_reg_no:
                    st.error("사업자 유형 선택 시 사업자등록번호는 필수입니다.")
                else:
                    from datetime import datetime as _dt
                    _joined_now = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_driver({
                        "id": next_driver_id(),
                        "name": name,
                        "phone": phone,
                        "rating": 4.5,
                        "available": available,
                        "available_from": avail_from,
                        "available_to": avail_to,
                        "completed_jobs": 0,
                        "license": license_type,
                        "driver_type": driver_type,
                        "specialty": driver_specialty,
                        "region": driver_region,
                        "joined_at": _joined_now,
                        "monthly_jobs": int(monthly_jobs),
                        "collection_jobs": 0,
                        "demolition_jobs": 0,
                        "avg_satisfaction": None,
                        "tax_type": tax_type,
                        "business_reg_no": business_reg_no,
                        "business_type": business_type,
                        "business_category": business_category,
                        "tax_invoice_requested": False,
                    })
                    spec_label = {"수거": "📦 수거 전용", "철거": "🔨 철거 전용", "공통": "⚖️ 공통"}.get(driver_specialty, driver_specialty)
                    st.success(f"✅ {name} 기사 ({driver_type} / {spec_label} / {driver_region} / {tax_type_label}) 등록 완료!")
                    st.rerun()

    st.divider()
    st.markdown("**기사 목록**")
    for d in sorted(drivers, key=lambda x: x["rating"], reverse=True):
        col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 1, 1])
        with col1:
            _tax_badge = "🏢" if d.get("tax_type") == "business" else "👤"
            _tax_tip = "사업자" if d.get("tax_type") == "business" else "개인3.3%"
            _spec = d.get("specialty", "공통")
            _spec_icon = {"수거": "📦", "철거": "🔨", "공통": "⚖️"}.get(_spec, "⚖️")
            st.markdown(
                f"{'🟢' if d['available'] else '🔴'} **{d['name']}** ({d.get('driver_type', '직영')}) "
                f"{_spec_icon} {_spec} | {_tax_badge} {_tax_tip}"
            )
        with col2:
            monthly = d.get("monthly_jobs", 0)
            active_icon = "🔥" if monthly >= DIRECT_THRESHOLD else ""
            threshold_warn = f" ⚠️ {DIRECT_THRESHOLD-monthly}건 부족" if monthly < DIRECT_THRESHOLD and d.get("driver_type") == "직영" else ""
            st.markdown(f"⭐ {d['rating']} | 이달 {monthly}건{active_icon}{threshold_warn}")
        with col3:
            st.markdown(f"📦 수거 {d.get('collection_jobs', 0)}건 | 🔨 철거 {d.get('demolition_jobs', 0)}건")
        with col4:
            monthly_edit = st.number_input(
                "이달건수", min_value=0,
                value=int(d.get("monthly_jobs", 0)),
                key=f"monthly_{d['id']}",
                label_visibility="collapsed"
            )
            if monthly_edit != d.get("monthly_jobs", 0):
                d["monthly_jobs"] = monthly_edit
                save_driver(d)
                st.rerun()
        with col5:
            toggle = st.toggle("가용", value=d["available"], key=f"toggle_{d['id']}")
            if toggle != d["available"]:
                d["available"] = toggle
                save_driver(d)
                st.rerun()

# ──────────────── Tab 5: 배차 우선순위 현황 ────────────────
with tab5:
    st.subheader("📊 기사별 배차 우선순위 점수 현황")
    st.caption("작업 유형별로 점수를 계산합니다. 수거 많이 한 기사는 철거 우선, 철거 많이 한 기사는 수거 우선 배정됩니다.")

    drivers = get_drivers()
    view_type = st.radio("기준 작업 유형", ["철거", "수거"], horizontal=True)

    rows = []
    for d in drivers:
        score = calc_priority_score(d, view_type)
        collection = d.get("collection_jobs", 0)
        demolition = d.get("demolition_jobs", 0)
        monthly = d.get("monthly_jobs", 0)
        at_risk = monthly < DIRECT_THRESHOLD and d.get("driver_type") == "직영"
        rows.append({
            "기사명": d["name"],
            "유형": d.get("driver_type", "직영"),
            "수거 완료": f"{collection}건",
            "철거 완료": f"{demolition}건",
            "이달 완료": f"{monthly}건",
            f"'{view_type}' 우선순위 점수": f"{score}점",
            "운영비 위험": "⚠️ 40건 미달" if at_risk else "✅ 정상",
            "상태": "🟢 가용" if d["available"] else "🔴 불가",
        })

    rows_sorted = sorted(
        rows, key=lambda x: float(x[f"'{view_type}' 우선순위 점수"].replace("점", "")), reverse=True
    )
    st.dataframe(pd.DataFrame(rows_sorted), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("⚠️ 조건부 운영비 위험 기사")
    at_risk_drivers = [d for d in drivers if d.get("monthly_jobs", 0) < DIRECT_THRESHOLD and d.get("driver_type") == "직영"]
    if not at_risk_drivers:
        st.success(f"✅ 모든 직영 기사가 {DIRECT_THRESHOLD}건 이상 달성 중입니다.")
    else:
        for d in at_risk_drivers:
            monthly = d.get("monthly_jobs", 0)
            remaining = DIRECT_THRESHOLD - monthly
            st.warning(
                f"⚠️ **{d['name']}** — 이달 {monthly}건 완료 | "
                f"운영비 전액 기준까지 **{remaining}건 부족** | "
                f"현재 기준: ₩750,000 (50% 차감)"
            )

show_legal_warning()
