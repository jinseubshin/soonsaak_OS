import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (
    get_orders, get_drivers, get_driver_by_id,
    add_journey_notification, get_journey_notifications,
    add_review, get_reviews,
    add_crm_followup, get_crm_followups, update_crm_followup,
    mark_notification_sent, update_order
)
from utils.footer import show_legal_warning
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(page_title="고객 여정 매니저 — 순삭 OS", page_icon="🗺️", layout="wide")
st.title("🗺️ 고객 여정 매니저")
st.caption("예약 확정 → 배차 → 도착 5분 전 → 완료 → 리뷰 유도 → 재방문 CRM 전 단계 자동화")

ACCOUNT_WARNING = (
    "\n\n⚠️ [필수 안내] 본사 공식 계좌 외 기사에게 직접 현금 지급 시 "
    "AS 및 보상이 불가합니다. 모든 결제는 본사 공식 채널을 이용해 주세요."
)

NOTIF_TEMPLATES = {
    "notif_reserved": {
        "label": "📅 예약 확정",
        "field": "notif_reserved",
        "template": lambda o, d: (
            f"[순삭] 안녕하세요, {o['customer']}님! "
            f"{'수거' if o.get('work_type','수거') == '수거' else '철거'} 예약이 확정되었습니다. "
            f"작업일시: {o['scheduled_time']} | 작업 전 현장 사진을 한 번 더 확인해 주세요."
            + ACCOUNT_WARNING
        ),
        "condition": lambda o: True,
    },
    "notif_dispatched": {
        "label": "🚗 기사 배정 완료",
        "field": "notif_dispatched",
        "template": lambda o, d: (
            f"[순삭] {o['customer']}님, 담당 {'기사' if d else '팀'}이 배정되었습니다. "
            f"{('담당: ' + d['name'] + ' | ') if d else ''}"
            f"작업 당일 법인폰으로 연락드립니다. 궁금하신 점은 본사로 문의해 주세요."
            + ACCOUNT_WARNING
        ),
        "condition": lambda o: o.get("driver_id") is not None,
    },
    "notif_eta": {
        "label": "🔔 도착 5분 전",
        "field": "notif_eta",
        "template": lambda o, d: (
            f"[순삭] {o['customer']}님, 곧 도착합니다! "
            f"미리 마중 준비 부탁드립니다. "
            f"{'담당: ' + d['name'] if d else '담당팀'}이 약 5분 후 현장에 도착 예정입니다."
            + ACCOUNT_WARNING
        ),
        "condition": lambda o: o["status"] == "in_progress",
    },
    "notif_completed": {
        "label": "✅ 작업 완료",
        "field": "notif_completed",
        "template": lambda o, d: (
            f"[순삭] {o['customer']}님, 작업이 깔끔하게 완료되었습니다! "
            f"전/후 사진은 순삭 OS 시스템에서 확인하실 수 있습니다. "
            f"이용해 주셔서 감사합니다 🙏"
            + ACCOUNT_WARNING
        ),
        "condition": lambda o: o["status"] == "completed",
    },
    "notif_review_sent": {
        "label": "⭐ 리뷰 요청 (완료 1시간 후)",
        "field": "notif_review_sent",
        "template": lambda o, d: (
            f"[순삭] {o['customer']}님, 오늘 서비스는 만족하셨나요? "
            f"평점과 후기를 남겨주시면 다음에 사용 가능한 쿠폰을 드립니다! 💝 "
            f"[리뷰 작성하기] — 소중한 의견이 큰 힘이 됩니다."
            + ACCOUNT_WARNING
        ),
        "condition": lambda o: o["status"] == "completed" and not o.get("review_written"),
    },
    "notif_review_reminded": {
        "label": "🔁 리뷰 리마인드 (24시간 후)",
        "field": "notif_review_reminded",
        "template": lambda o, d: (
            f"[순삭] {o['customer']}님, 지난 번 서비스 후기를 아직 남기지 않으셨네요. "
            f"딱 1분이면 됩니다! 평점과 짧은 후기만으로도 쿠폰을 드립니다 🎁"
            + ACCOUNT_WARNING
        ),
        "condition": lambda o: (
            o["status"] == "completed"
            and not o.get("review_written")
            and o.get("notif_review_sent")
        ),
    },
}

CRM_TEMPLATE = (
    "[순삭] {name}님, 순삭수거를 이용하신 지 3개월이 지났습니다. "
    "정기 수거가 필요하신가요? 재방문 고객 할인을 제공해 드립니다! "
    "편한 시간에 연락 주시면 빠르게 안내드리겠습니다 😊"
    + ACCOUNT_WARNING
)

# ─────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ 여정 현황",
    "📲 알림 발송",
    "⭐ 리뷰 관리",
    "📞 재방문 CRM",
    "📊 통계",
])

orders = get_orders()
all_notifs = get_journey_notifications()
reviews = get_reviews()
crm_followups = get_crm_followups()

# ──────────────── Tab 1: 여정 현황 ────────────────
with tab1:
    st.subheader("주문별 고객 여정 진행 현황")

    status_labels = {
        "pending": "⏳ 대기", "dispatched": "📍 배차완료",
        "in_progress": "🔄 진행중", "completed": "✅ 완료", "cancelled": "❌ 취소",
    }

    STEPS = [
        ("예약확정", "notif_reserved"),
        ("기사배정", "notif_dispatched"),
        ("5분전", "notif_eta"),
        ("완료알림", "notif_completed"),
        ("리뷰요청", "notif_review_sent"),
        ("리마인드", "notif_review_reminded"),
        ("CRM예약", "notif_crm_scheduled"),
    ]

    for o in sorted(orders, key=lambda x: x["scheduled_time"], reverse=True):
        drv = get_driver_by_id(o.get("driver_id"))
        review_done = o.get("review_written", False)

        with st.container():
            c1, c2 = st.columns([2, 5])
            with c1:
                st.markdown(f"**주문 #{o['id']}** — {o['customer']}")
                st.caption(f"{'🔨 철거' if o.get('work_type') == '철거' else '📦 수거'} | {o['scheduled_time']}")
                st.caption(status_labels.get(o["status"], o["status"]))
            with c2:
                step_cols = st.columns(len(STEPS))
                for idx, (step_label, field) in enumerate(STEPS):
                    done = o.get(field, False)
                    with step_cols[idx]:
                        if done:
                            st.markdown(f"<div style='text-align:center;color:green;font-size:11px'>✅<br>{step_label}</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div style='text-align:center;color:#aaa;font-size:11px'>⬜<br>{step_label}</div>", unsafe_allow_html=True)
            if review_done:
                score = o.get("satisfaction_score", "—")
                st.caption(f"⭐ 리뷰 완료 — {score}점 | {'🎟️ 쿠폰 발급됨' if o.get('coupon_issued') else '쿠폰 미발급'}")
            st.divider()

# ──────────────── Tab 2: 알림 발송 ────────────────
with tab2:
    st.subheader("📲 단계별 알림톡 발송 관리")
    st.info(
        "💬 실제 서비스에서는 n8n 또는 카카오 알림톡 API와 연동됩니다. "
        "지금은 발송 내역을 기록하고 메시지를 미리보기할 수 있습니다."
    )

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        order_options = [f"#{o['id']} — {o['customer']} ({o.get('work_type', '수거')})" for o in orders]
        sel_order_str = st.selectbox("주문 선택", order_options)
    sel_order_id = int(sel_order_str.split("#")[1].split(" ")[0])
    sel_order = next((o for o in orders if o["id"] == sel_order_id), None)

    if sel_order:
        drv = get_driver_by_id(sel_order.get("driver_id"))
        st.markdown(f"**고객:** {sel_order['customer']} | **연락처:** {sel_order['customer_phone']}")

        st.divider()
        for key, cfg in NOTIF_TEMPLATES.items():
            field = cfg["field"]
            already_sent = sel_order.get(field, False)
            can_send = cfg["condition"](sel_order)

            with st.container():
                c1, c2, c3 = st.columns([1, 4, 1])
                with c1:
                    if already_sent:
                        st.success("✅ 발송됨")
                    elif can_send:
                        st.info("📤 발송 가능")
                    else:
                        st.warning("⏸ 대기 중")
                with c2:
                    msg = cfg["template"](sel_order, drv)
                    # Show truncated message
                    short_msg = msg.split("\n\n")[0]
                    st.markdown(f"**{cfg['label']}**")
                    st.caption(short_msg[:120] + "..." if len(short_msg) > 120 else short_msg)
                with c3:
                    btn_label = "재발송" if already_sent else "📤 발송"
                    disabled = not can_send and not already_sent
                    if st.button(btn_label, key=f"send_{sel_order_id}_{field}", disabled=disabled):
                        full_msg = cfg["template"](sel_order, drv)
                        add_journey_notification({
                            "order_id": sel_order_id,
                            "customer": sel_order["customer"],
                            "customer_phone": sel_order["customer_phone"],
                            "type": cfg["label"],
                            "message": full_msg,
                        })
                        mark_notification_sent(sel_order_id, field)
                        st.success(f"✅ {cfg['label']} 발송 완료!")
                        st.rerun()

        # 메시지 전체 미리보기
        with st.expander("📋 메시지 전체 미리보기"):
            for key, cfg in NOTIF_TEMPLATES.items():
                st.markdown(f"**{cfg['label']}**")
                st.code(cfg["template"](sel_order, drv), language=None)
                st.divider()

    st.divider()
    st.subheader("📬 최근 발송 이력")
    recent = sorted(all_notifs, key=lambda x: x.get("sent_at", ""), reverse=True)[:15]
    if not recent:
        st.info("발송된 알림이 없습니다.")
    else:
        rows = []
        for n in recent:
            rows.append({
                "발송시각": n.get("sent_at", "—")[:16],
                "주문": f"#{n.get('order_id', '—')}",
                "고객": n.get("customer", "—"),
                "연락처": n.get("customer_phone", "—"),
                "종류": n.get("type", "—"),
                "메시지(앞부분)": n.get("message", "")[:50] + "…",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ──────────────── Tab 3: 리뷰 관리 ────────────────
with tab3:
    st.subheader("⭐ 리뷰 관리 — 고객 만족도 & 쿠폰 발행")

    completed_orders = [o for o in orders if o["status"] == "completed"]
    no_review = [o for o in completed_orders if not o.get("review_written")]
    with_review = [o for o in completed_orders if o.get("review_written")]

    total = len(completed_orders)
    written = len(with_review)
    review_rate = written / total * 100 if total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 완료 주문", f"{total}건")
    with col2:
        st.metric("✅ 리뷰 완료", f"{written}건")
    with col3:
        target = 70
        delta_color = "normal" if review_rate >= target else "inverse"
        st.metric("📈 리뷰 작성률", f"{review_rate:.1f}%",
                  delta=f"목표 {target}%", delta_color=delta_color)
    with col4:
        coupons = sum(1 for o in completed_orders if o.get("coupon_issued"))
        st.metric("🎟️ 쿠폰 발행", f"{coupons}건")

    st.divider()

    if no_review:
        st.subheader(f"📝 리뷰 미작성 ({len(no_review)}건)")
        for o in no_review:
            drv = get_driver_by_id(o.get("driver_id"))
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                st.markdown(f"**#{o['id']} {o['customer']}** | {o.get('work_type', '수거')} | {o['scheduled_time'][:10]}")
                st.caption(f"기사: {drv['name'] if drv else '—'} | 📞 {o['customer_phone']}")
            with c2:
                remind_sent = o.get("notif_review_sent", False)
                reminded = o.get("notif_review_reminded", False)
                if reminded:
                    st.caption("🔁 리마인드 발송됨")
                elif remind_sent:
                    st.caption("📤 1차 리뷰 요청 발송됨")
                    if st.button("🔁 리마인드 발송", key=f"remind_{o['id']}"):
                        add_journey_notification({
                            "order_id": o["id"],
                            "customer": o["customer"],
                            "customer_phone": o["customer_phone"],
                            "type": "🔁 리뷰 리마인드",
                            "message": NOTIF_TEMPLATES["notif_review_reminded"]["template"](o, drv),
                        })
                        mark_notification_sent(o["id"], "notif_review_reminded")
                        st.success("리마인드 발송!")
                        st.rerun()
                else:
                    if st.button("📤 리뷰 요청 발송", key=f"review_req_{o['id']}"):
                        add_journey_notification({
                            "order_id": o["id"],
                            "customer": o["customer"],
                            "customer_phone": o["customer_phone"],
                            "type": "⭐ 리뷰 요청",
                            "message": NOTIF_TEMPLATES["notif_review_sent"]["template"](o, drv),
                        })
                        mark_notification_sent(o["id"], "notif_review_sent")
                        st.success("리뷰 요청 발송!")
                        st.rerun()
            with c3:
                with st.expander("✏️ 리뷰 직접 입력"):
                    score = st.slider("평점", 1, 5, 5, key=f"rv_score_{o['id']}")
                    comment = st.text_area("후기", key=f"rv_comment_{o['id']}", height=60)
                    issue_coupon = st.checkbox("쿠폰 발급", value=True, key=f"rv_coupon_{o['id']}")
                    if st.button("💾 저장", key=f"rv_save_{o['id']}"):
                        add_review({
                            "order_id": o["id"],
                            "customer": o["customer"],
                            "driver_id": o.get("driver_id"),
                            "score": score,
                            "comment": comment,
                            "coupon_issued": issue_coupon,
                        })
                        if issue_coupon:
                            add_journey_notification({
                                "order_id": o["id"],
                                "customer": o["customer"],
                                "customer_phone": o["customer_phone"],
                                "type": "🎟️ 쿠폰 발급",
                                "message": f"[순삭] {o['customer']}님, 소중한 리뷰 감사합니다! 다음 이용 시 사용 가능한 쿠폰을 발급해 드렸습니다 🎁",
                            })
                        st.success("✅ 리뷰 저장됨!")
                        st.rerun()

    if with_review:
        st.divider()
        st.subheader(f"✅ 리뷰 완료 ({len(with_review)}건)")
        rows = []
        for o in with_review:
            rows.append({
                "주문": f"#{o['id']}",
                "고객": o["customer"],
                "작업": o.get("work_type", "수거"),
                "평점": f"{'⭐' * int(o.get('satisfaction_score') or 0)} ({o.get('satisfaction_score', '—')}점)",
                "후기": (o.get("satisfaction_comment") or "—")[:30],
                "쿠폰": "🎟️ 발급됨" if o.get("coupon_issued") else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ──────────────── Tab 4: 재방문 CRM ────────────────
with tab4:
    st.subheader("📞 재방문 유도 CRM — 3개월 자동 안부 메시지")
    st.info(
        "수거 완료 후 3개월 경과 시 재방문 안부 메시지를 자동 예약합니다. "
        "발송 시점이 되면 '발송 가능' 상태로 변경됩니다."
    )

    now = datetime.now()
    completed = [o for o in orders if o["status"] == "completed" and o.get("payment_confirmed")]

    # 자동으로 CRM 대상 감지 및 등록
    existing_crm_order_ids = {f.get("order_id") for f in crm_followups}
    for o in completed:
        if o["id"] in existing_crm_order_ids:
            continue
        if o.get("notif_crm_scheduled"):
            continue
        try:
            completed_dt = datetime.strptime(o["created_at"], "%Y-%m-%d %H:%M")
        except Exception:
            completed_dt = now - timedelta(days=1)
        followup_date = completed_dt + timedelta(days=90)
        add_crm_followup({
            "order_id": o["id"],
            "customer": o["customer"],
            "customer_phone": o["customer_phone"],
            "work_type": o.get("work_type", "수거"),
            "followup_date": followup_date.strftime("%Y-%m-%d"),
            "sent": False,
            "message": CRM_TEMPLATE.format(name=o["customer"]),
        })
        mark_notification_sent(o["id"], "notif_crm_scheduled")

    crm_followups = get_crm_followups()

    if not crm_followups:
        st.info("CRM 예약된 고객이 없습니다. 입금 확인된 완료 주문이 있으면 자동 등록됩니다.")
    else:
        pending = [f for f in crm_followups if not f.get("sent")]
        sent = [f for f in crm_followups if f.get("sent")]

        col1, col2 = st.columns(2)
        with col1:
            st.metric("📅 발송 대기", f"{len(pending)}건")
        with col2:
            st.metric("✅ 발송 완료", f"{len(sent)}건")

        st.divider()
        if pending:
            st.subheader("📅 발송 대기 목록")
            for idx, f in enumerate(crm_followups):
                if f.get("sent"):
                    continue
                try:
                    followup_dt = datetime.strptime(f.get("followup_date", ""), "%Y-%m-%d")
                    is_due = now >= followup_dt
                    days_left = (followup_dt - now).days
                except Exception:
                    is_due = False
                    days_left = 90

                c1, c2, c3 = st.columns([3, 3, 1])
                with c1:
                    st.markdown(f"**{f['customer']}** | 📞 {f['customer_phone']}")
                    st.caption(f"주문 #{f.get('order_id', '—')} | {f.get('work_type', '수거')}")
                with c2:
                    if is_due:
                        st.success(f"✅ 발송 가능! (예정일: {f.get('followup_date', '—')})")
                    else:
                        st.info(f"⏳ {days_left}일 후 발송 (예정: {f.get('followup_date', '—')})")
                with c3:
                    btn_disabled = not is_due
                    if st.button("📤 발송", key=f"crm_send_{idx}", disabled=btn_disabled):
                        add_journey_notification({
                            "order_id": f.get("order_id"),
                            "customer": f["customer"],
                            "customer_phone": f["customer_phone"],
                            "type": "📞 재방문 CRM",
                            "message": f["message"],
                        })
                        update_crm_followup(idx, {"sent": True, "sent_at": now.strftime("%Y-%m-%d %H:%M")})
                        st.success("CRM 안부 메시지 발송 완료!")
                        st.rerun()

                with st.expander("메시지 미리보기"):
                    st.code(f.get("message", ""), language=None)
                st.divider()

        if sent:
            st.subheader("✅ 발송 완료 목록")
            rows = []
            for f in sent:
                rows.append({
                    "고객": f["customer"],
                    "연락처": f["customer_phone"],
                    "작업": f.get("work_type", "—"),
                    "예정일": f.get("followup_date", "—"),
                    "발송일": f.get("sent_at", "—")[:10] if f.get("sent_at") else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ──────────────── Tab 5: 통계 ────────────────
with tab5:
    st.subheader("📊 고객 여정 통합 통계")

    total_orders = len(orders)
    completed_cnt = len([o for o in orders if o["status"] == "completed"])
    notif_counts = {
        "예약확정": sum(1 for o in orders if o.get("notif_reserved")),
        "기사배정": sum(1 for o in orders if o.get("notif_dispatched")),
        "5분전": sum(1 for o in orders if o.get("notif_eta")),
        "완료알림": sum(1 for o in orders if o.get("notif_completed")),
        "리뷰요청": sum(1 for o in orders if o.get("notif_review_sent")),
        "리마인드": sum(1 for o in orders if o.get("notif_review_reminded")),
        "CRM예약": sum(1 for o in orders if o.get("notif_crm_scheduled")),
    }

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("전체 주문", total_orders)
    with col2:
        st.metric("완료 주문", completed_cnt)
    with col3:
        review_rate = len(reviews) / max(completed_cnt, 1) * 100
        st.metric("리뷰 작성률", f"{review_rate:.1f}%", delta="목표 70%",
                  delta_color="normal" if review_rate >= 70 else "inverse")

    st.divider()
    st.subheader("알림톡 단계별 발송 현황")
    notif_df = pd.DataFrame([
        {"단계": k, "발송 건수": v, "발송률": f"{v/max(total_orders,1)*100:.0f}%"}
        for k, v in notif_counts.items()
    ])
    st.dataframe(notif_df, use_container_width=True, hide_index=True)

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("⭐ 최근 리뷰")
        if reviews:
            for rv in reversed(reviews[-5:]):
                stars = "⭐" * int(rv.get("score", 0))
                st.markdown(f"{stars} **{rv.get('customer', '—')}** — {(rv.get('comment') or '후기 없음')[:40]}")
        else:
            st.info("등록된 리뷰가 없습니다.")

    with col_b:
        st.subheader("📞 CRM 현황")
        crm_total = len(crm_followups)
        crm_sent = sum(1 for f in crm_followups if f.get("sent"))
        crm_pending = crm_total - crm_sent
        st.metric("CRM 등록", f"{crm_total}건")
        st.metric("CRM 발송 완료", f"{crm_sent}건")
        st.metric("CRM 대기 중", f"{crm_pending}건")

        avg_score = None
        if reviews:
            scores = [r.get("score") for r in reviews if r.get("score")]
            if scores:
                avg_score = sum(scores) / len(scores)
        if avg_score:
            st.metric("평균 고객 만족도", f"{avg_score:.1f}점 / 5점")

show_legal_warning()
