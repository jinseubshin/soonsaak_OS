import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (get_orders, get_settings, update_order, add_notification,
                     get_driver_by_id, get_blacklist, add_blacklist, remove_blacklist_entry)
from utils.footer import show_legal_warning
from utils.rbac import render_role_selector, is_owner, is_manager, is_executor, is_cs, role_badge
import pandas as pd

st.set_page_config(page_title="리스크 관리 — 순삭 OS", page_icon="⚠️", layout="wide")
st.title("⚠️ 리스크 관리")
st.caption("추가 요금 승인/거절 처리 · 임의 추가요금 적발 · 지연 패널티 관리 · 블랙리스트")

render_role_selector()
st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")

# CS / Executor 접근 차단
if is_cs():
    st.error(
        "🚫 **CS 상담원은 리스크 관리 페이지에 접근할 수 없습니다.**\n\n"
        "추가요금 승인·패널티 처리는 매니저/대표 전용입니다."
    )
    st.stop()
if is_executor():
    st.error("🚫 **기사 모드에서는 리스크 관리 페이지에 접근할 수 없습니다.**")
    st.stop()

settings = get_settings()
DISPATCH_FEE = settings["dispatch_fee"]
DRIVER_RATIO = settings["driver_ratio"]

orders = get_orders()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🔔 추가요금 승인 대기", "🚨 임의추가요금 적발",
    "⏰ 지연 패널티", "📊 분석", "🚫 블랙리스트", "🤖 AI 사진 검증", "📲 알림 이력"
])

# ──────────────── Tab 1: 승인 대기 ────────────────
with tab1:
    pending = [o for o in orders if o.get("extra_fee_status") == "pending"]
    if not pending:
        st.success("✅ 승인 대기 중인 추가요금 요청이 없습니다.")
    else:
        st.warning(f"⚠️ {len(pending)}건의 추가요금 승인 대기 중")
        for o in pending:
            drv = get_driver_by_id(o.get("driver_id"))
            extra = o.get("extra_fee", 0)
            base = o["base_fee"]
            total_if_approved = base + extra
            driver_pay_approved = total_if_approved * DRIVER_RATIO
            driver_pay_rejected = DISPATCH_FEE * DRIVER_RATIO

            with st.container():
                st.markdown("---")
                st.markdown(f"### 📦 주문 #{o['id']} — {o['customer']}")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**고객:** {o['customer']} ({o['customer_phone']})")
                    st.markdown(f"**기사:** {drv['name'] if drv else '미배정'}")
                    st.markdown(f"**작업 유형:** {'🔨 철거' if o.get('work_type') == '철거' else '📦 수거'}")
                    st.markdown(f"**출발:** {o['pickup']}")
                with col2:
                    st.markdown(f"**기본요금:** ₩{base:,}")
                    st.markdown(f"**추가요금 요청:** ₩{extra:,}")
                    st.markdown(f"**승인 시 총액:** ₩{total_if_approved:,}")

                st.markdown("**📊 정산 시뮬레이션**")
                sim_col1, sim_col2 = st.columns(2)
                with sim_col1:
                    st.success(f"✅ **승인 시** 기사 지급: ₩{driver_pay_approved:,.0f}")
                with sim_col2:
                    st.error(f"❌ **거절 시** 기사 지급: ₩{driver_pay_rejected:,.0f} (출동비만)")

                btn_col1, btn_col2, _ = st.columns([1, 1, 2])
                with btn_col1:
                    if st.button("✅ 고객 승인 처리", key=f"approve_{o['id']}", type="primary"):
                        update_order(o["id"], {"extra_fee_status": "approved"})
                        add_notification({
                            "order_id": o["id"], "customer": o["customer"],
                            "customer_phone": o["customer_phone"], "type": "추가요금승인",
                            "message": f"[순삭] 추가 요금 ₩{extra:,} 승인 처리. 총 ₩{total_if_approved:,} 청구."
                        })
                        st.success("✅ 승인 완료!")
                        st.rerun()
                with btn_col2:
                    if st.button("❌ 고객 거절 처리", key=f"reject_{o['id']}"):
                        update_order(o["id"], {"extra_fee_status": "rejected"})
                        add_notification({
                            "order_id": o["id"], "customer": o["customer"],
                            "customer_phone": o["customer_phone"], "type": "추가요금거절",
                            "message": f"[순삭] 추가 요금 요청 거절. 출동비 ₩{DISPATCH_FEE:,}만 청구."
                        })
                        st.warning(f"❌ 거절 처리 — 출동비 ₩{DISPATCH_FEE:,}만 정산 적용")
                        st.rerun()

# ──────────────── Tab 2: 임의추가요금 적발 ────────────────
with tab2:
    st.subheader("🚨 임의 추가요금 적발 관리")
    st.error(
        "⚠️ **임의 추가요금 적발 시 해당 건 수당 0원 처리 + 3배 배상 청구 경고가 발동됩니다.**"
    )

    flagged = [o for o in orders if o.get("arbitrary_fee_flag")]
    not_flagged_completed = [o for o in orders if o["status"] == "completed" and not o.get("arbitrary_fee_flag")]

    st.subheader("현재 주문에 임의추가요금 적발 처리")
    completed_with_extra = [o for o in orders if
                            o["status"] in ("completed", "in_progress") and
                            not o.get("arbitrary_fee_flag") and
                            o.get("extra_fee_status") not in ("approved",)]

    if not completed_with_extra:
        st.info("적발 처리할 주문이 없습니다.")
    else:
        for o in completed_with_extra:
            drv = get_driver_by_id(o.get("driver_id"))
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**주문 #{o['id']}** — {o['customer']} | 기사: {drv['name'] if drv else '미배정'}")
                st.caption(f"기본요금 ₩{o['base_fee']:,} | 추가요금 ₩{o.get('extra_fee', 0):,}")
            with col2:
                st.caption(f"작업: {'🔨 철거' if o.get('work_type') == '철거' else '📦 수거'} | {o['status']}")
            with col3:
                if st.button("🚨 적발", key=f"flag_{o['id']}", type="secondary"):
                    update_order(o["id"], {
                        "arbitrary_fee_flag": True,
                        "job_allowance": 0,
                        "penalty_amount": o.get("base_fee", 0) * 3
                    })
                    drv_name = drv["name"] if drv else "미배정 기사"
                    st.error(f"🚨 적발 처리 완료! {drv_name} — 수당 0원 + 3배 배상 경고 발동")
                    st.rerun()

    if flagged:
        st.divider()
        st.subheader(f"🚨 적발 이력 ({len(flagged)}건)")
        for o in flagged:
            drv = get_driver_by_id(o.get("driver_id"))
            penalty = o.get("penalty_amount", o.get("base_fee", 0) * 3)
            st.error(
                f"🚨 **주문 #{o['id']}** | {o['customer']} | 기사: {drv['name'] if drv else '미배정'} | "
                f"수당 0원 처리 + **₩{penalty:,.0f} 3배 배상 청구 경고**"
            )

# ──────────────── Tab 3: 지연 패널티 ────────────────
with tab3:
    st.subheader("⏰ 지연 발생 주문 — 수당 차감 관리")
    st.info("지연 발생 시 해당 건 수당에서 패널티 금액을 차감합니다.")

    delayed = [o for o in orders if o.get("delay_flag")]
    if not delayed:
        st.success("✅ 지연 발생 주문이 없습니다.")
    else:
        for o in delayed:
            drv = get_driver_by_id(o.get("driver_id"))
            current_allowance = o.get("job_allowance", 0)
            current_penalty = o.get("penalty_amount", 0)
            net_allowance = max(0, current_allowance - current_penalty)

            with st.container():
                st.markdown("---")
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"**주문 #{o['id']}** — {o['customer']}")
                    st.caption(f"기사: {drv['name'] if drv else '미배정'} | 작업: {'🔨 철거' if o.get('work_type') == '철거' else '📦 수거'}")
                    st.caption(f"배정 수당: ₩{current_allowance:,} | 패널티: ₩{current_penalty:,} | 실지급 수당: ₩{net_allowance:,}")
                with col2:
                    if not o.get("arbitrary_fee_flag"):
                        new_penalty = st.number_input(
                            "패널티 차감액 (원)",
                            min_value=0,
                            value=int(current_penalty),
                            step=5000,
                            key=f"penalty_{o['id']}"
                        )
                        if st.button("💾 패널티 저장", key=f"save_penalty_{o['id']}"):
                            update_order(o["id"], {"penalty_amount": int(new_penalty)})
                            st.success("패널티 저장됨")
                            st.rerun()
                    else:
                        st.error("임의추가요금 적발 건 — 수당 0원")

# ──────────────── Tab 4: 분석 ────────────────
with tab4:
    st.subheader("리스크 분석")
    import plotly.express as px

    all_extra = [o for o in orders if o.get("extra_fee_status")]
    approved = sum(1 for o in all_extra if o["extra_fee_status"] == "approved")
    rejected = sum(1 for o in all_extra if o["extra_fee_status"] == "rejected")
    pending_count = sum(1 for o in all_extra if o["extra_fee_status"] == "pending")
    flagged_count = sum(1 for o in orders if o.get("arbitrary_fee_flag"))
    delayed_count = sum(1 for o in orders if o.get("delay_flag"))

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("✅ 승인", f"{approved}건")
    with col2:
        st.metric("❌ 거절 (출동비)", f"{rejected}건")
    with col3:
        st.metric("⏳ 대기", f"{pending_count}건")
    with col4:
        st.metric("🚨 임의추가요금 적발", f"{flagged_count}건", delta=f"-{flagged_count}" if flagged_count else None, delta_color="inverse")
    with col5:
        st.metric("⏰ 지연 발생", f"{delayed_count}건", delta=f"-{delayed_count}" if delayed_count else None, delta_color="inverse")

    if approved + rejected > 0:
        fig = px.pie(
            values=[approved, rejected, pending_count],
            names=["승인", "거절", "대기"],
            title="추가요금 요청 처리 현황",
            color_discrete_map={"승인": "#00CC96", "거절": "#EF553B", "대기": "#FFA15A"},
        )
        st.plotly_chart(fig, use_container_width=True)

        rejected_orders = [o for o in all_extra if o["extra_fee_status"] == "rejected"]
        total_dispatch_revenue = sum(DISPATCH_FEE for _ in rejected_orders)
        total_lost = sum(o["base_fee"] + o.get("extra_fee", 0) - DISPATCH_FEE for o in rejected_orders)
        st.divider()
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("출동비 정산 수익", f"₩{total_dispatch_revenue:,}")
        with col_b:
            st.metric("추가요금 미수 손실", f"₩{total_lost:,}", delta="손실", delta_color="inverse")
        with col_c:
            total_penalty = sum(o.get("penalty_amount", 0) for o in orders)
            st.metric("누적 패널티 차감액", f"₩{total_penalty:,}", delta_color="inverse")
    else:
        st.info("추가요금 처리 데이터가 없습니다.")

# ──────────────── Tab 5: 블랙리스트 ────────────────
with tab5:
    st.subheader("🚫 블랙리스트 관리 — 악성 고객 차단")
    st.info(
        "블랙리스트에 등록된 번호로 CS 상담 입력 시 **즉시 '주의' 경고가 노출**됩니다. "
        "고의적 계약 파기, 임의 추가요금 강요, 폭언/협박 고객을 등록하세요."
    )

    blacklist = get_blacklist()

    # ── 신규 등록
    with st.expander("➕ 블랙리스트 신규 등록", expanded=True):
        with st.form("blacklist_add_form", clear_on_submit=True):
            bl_col1, bl_col2 = st.columns(2)
            with bl_col1:
                bl_phone = st.text_input("고객 전화번호 *", placeholder="010-0000-0000")
                bl_name = st.text_input("고객명 (선택)", placeholder="홍길동")
            with bl_col2:
                bl_reason = st.selectbox(
                    "등록 사유 *",
                    ["폭언/협박", "임의 추가요금 강요", "고의 계약 파기", "무단 취소 반복", "사기 의심", "기타"]
                )
                bl_detail = st.text_area("상세 내용 (선택)", placeholder="구체적인 사건 내용을 기록하세요")
            bl_added_by = st.text_input("등록자", placeholder="CS 담당자명")
            submitted = st.form_submit_button("🚫 블랙리스트 등록", type="primary")
            if submitted:
                if not bl_phone:
                    st.error("전화번호를 입력하세요.")
                else:
                    ok = add_blacklist({
                        "phone": bl_phone,
                        "customer_name": bl_name,
                        "reason": bl_reason,
                        "detail": bl_detail,
                        "added_by": bl_added_by,
                    })
                    if ok:
                        st.success(f"✅ {bl_phone} 블랙리스트 등록 완료")
                        st.rerun()
                    else:
                        st.warning("⚠️ 이미 등록된 번호입니다.")

    # ── 현황 테이블
    st.markdown("---")
    st.markdown(f"#### 📋 블랙리스트 현황 — 총 {len(blacklist)}건")
    if not blacklist:
        st.info("등록된 블랙리스트가 없습니다.")
    else:
        bl_rows = []
        for b in blacklist:
            bl_rows.append({
                "전화번호": b.get("phone", "—"),
                "고객명": b.get("customer_name", "—"),
                "사유": b.get("reason", "—"),
                "상세": (b.get("detail", "") or "")[:30] + ("..." if len(b.get("detail", "") or "") > 30 else ""),
                "등록자": b.get("added_by", "—"),
                "등록일시": b.get("created_at", "—")[:16] if b.get("created_at") else "—",
            })
        st.dataframe(pd.DataFrame(bl_rows), use_container_width=True, hide_index=True)

        # ── 삭제
        st.markdown("#### 🗑️ 등록 해제")
        del_options = [f"{b['phone']} ({b.get('customer_name','—')})" for b in blacklist]
        del_target = st.selectbox("해제할 번호 선택", ["(선택)"] + del_options, key="bl_del_sel")
        if del_target != "(선택)":
            del_phone = del_target.split(" ")[0]
            if st.button("🗑️ 블랙리스트에서 해제", type="secondary", key="bl_del_btn"):
                remove_blacklist_entry(del_phone)
                st.success(f"✅ {del_phone} 해제 완료")
                st.rerun()

    # ── CS 상담 이력에서 블랙리스트 고객 탐색
    st.markdown("---")
    st.subheader("🔍 과거 상담에서 블랙리스트 고객 탐색")
    if blacklist:
        bl_phones = set(b.get("phone", "").replace("-", "").replace(" ", "") for b in blacklist)
        matched = [
            o for o in orders
            if (o.get("customer_phone") or "").replace("-", "").replace(" ", "") in bl_phones
        ]
        if matched:
            st.error(f"🔴 블랙리스트 고객이 과거 {len(matched)}건의 상담 이력에서 발견되었습니다!")
            for o in matched:
                st.warning(f"주문 #{o['id']} | {o['customer']} | {o['customer_phone']} | {o['status']} | ₩{o['base_fee']:,}")
        else:
            st.success("✅ 과거 상담 이력에서 블랙리스트 고객이 발견되지 않았습니다.")

# ──────────────── Tab 7: 알림 이력 ────────────────
with tab7:
    from utils.notifications import get_notification_log

    if not (is_owner() or is_manager()):
        st.error("🚫 Owner/Manager 전용 — 알림 이력에 접근할 수 없습니다.")
        st.stop()

    st.subheader("📲 카카오 알림 발송 이력")
    st.caption(
        "이상 징후 자동 알림(AI 사진 불일치·정산가 초과·미등록 번호)의 발송 이력입니다. "
        "설정 페이지에서 웹훅 URL을 등록하면 실제 카카오 알림이 발송됩니다."
    )

    notif_logs = get_notification_log(100)
    if not notif_logs:
        st.info("아직 발송된 알림이 없습니다.")
    else:
        _type_labels = {
            "photo_mismatch": "🤖 AI 사진 불일치",
            "settlement_overrun": "💰 정산가 초과",
            "unregistered_phone": "📱 미등록 번호",
            "test": "🧪 테스트",
        }
        n_col1, n_col2, n_col3 = st.columns(3)
        with n_col1:
            st.metric("총 알림", len(notif_logs))
        with n_col2:
            st.metric("발송 성공", len([n for n in notif_logs if n.get("success")]))
        with n_col3:
            st.metric("발송 실패", len([n for n in notif_logs if not n.get("success")]))

        st.divider()
        for n in notif_logs:
            event = n.get("event_type", "—")
            label = _type_labels.get(event, event)
            success = n.get("success")
            icon = "✅" if success else "❌"
            order_ref = f" | 주문 #{n['order_id']}" if n.get("order_id") else ""
            with st.expander(
                f"{icon} {label}{order_ref} — {n.get('sent_at','—')[:16]}"
            ):
                if not success:
                    err = n.get("error") or f"HTTP {n.get('status_code')}"
                    st.error(f"발송 실패 원인: {err}")
                    st.caption("설정 페이지에서 웹훅 URL을 확인하세요.")
                st.code(n.get("message", "—"), language=None)


# ──────────────── Tab 6: AI 사진 검증 현황 ────────────────
with tab6:
    from utils.ai_vision import score_badge, MATCH_ALERT_THRESHOLD
    import os as _os

    st.subheader("🤖 AI 사진 검증 현황")
    st.caption(
        f"철거 건 완료 사진과 견적 사진을 AI가 자동 비교합니다. "
        f"Match Score {MATCH_ALERT_THRESHOLD}점 미만은 자동 알림 처리됩니다."
    )

    demo_orders = [o for o in orders if o.get("work_type") == "철거"]
    if not demo_orders:
        st.info("철거 건이 없습니다.")
    else:
        verified = [o for o in demo_orders if o.get("photo_match_score") is not None]
        unverified_est = [o for o in demo_orders if o.get("estimate_photo_path") and not o.get("photo_match_score")]
        no_photo = [o for o in demo_orders if not o.get("estimate_photo_path")]

        kc1, kc2, kc3, kc4 = st.columns(4)
        with kc1:
            st.metric("전체 철거 건", len(demo_orders))
        with kc2:
            st.metric("AI 검증 완료", len(verified))
        with kc3:
            flagged = [o for o in verified if o.get("photo_match_flagged")]
            st.metric("🚩 불일치 의심", len(flagged), delta="주의" if flagged else None, delta_color="inverse")
        with kc4:
            st.metric("견적 사진 미업로드", len(no_photo))

        st.divider()

        if verified:
            st.subheader("✅ AI 검증 완료 건")
            for o in sorted(verified, key=lambda x: x.get("photo_match_score", 0)):
                score = o.get("photo_match_score")
                flagged_mark = "🚩 " if o.get("photo_match_flagged") else ""
                with st.expander(
                    f"{flagged_mark}주문 #{o['id']} — {o['customer']} | "
                    f"Match Score: {score}점 | {o.get('photo_match_checked_at','—')[:16]}"
                ):
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        st.markdown(score_badge(score), unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"**AI 근거:** {o.get('photo_match_reasoning','—')}")
                        flags = o.get("photo_match_flags", [])
                        if flags:
                            for fl in flags:
                                st.warning(f"⚠️ {fl}")

                    ep = o.get("estimate_photo_path")
                    cp = o.get("completion_photo_path")
                    if ep or cp:
                        img1, img2 = st.columns(2)
                        with img1:
                            if ep and _os.path.exists(ep):
                                st.image(ep, caption="견적 사진", use_container_width=True)
                            else:
                                st.caption("견적 사진 파일 없음")
                        with img2:
                            if cp and _os.path.exists(cp):
                                st.image(cp, caption="완료 사진", use_container_width=True)
                            else:
                                st.caption("완료 사진 파일 없음")

                    if o.get("photo_match_flagged"):
                        st.error("🚩 이 건은 대표 대시보드에 불일치 알림이 전송되었습니다.")

        if unverified_est:
            st.divider()
            st.subheader("⏳ 완료 사진 대기 중 (견적 사진 있음)")
            for o in unverified_est:
                st.info(
                    f"주문 #{o['id']} — {o['customer']} | {o.get('demolition_scope','—')} | "
                    f"상태: {o['status']} | 견적 사진 ✅ | 완료 사진 ⏳"
                )

        if no_photo:
            st.divider()
            st.subheader("📸 견적 사진 미업로드")
            for o in no_photo:
                st.warning(
                    f"주문 #{o['id']} — {o['customer']} | {o.get('demolition_scope','—')} | "
                    f"매니저 현장 방문 후 견적 사진을 업로드하세요"
                )

show_legal_warning()
