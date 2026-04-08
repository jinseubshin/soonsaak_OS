import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (get_subcontractors, get_subcontractor_jobs, save_subcontractor,
                     add_subcontractor_job, update_subcontractor_job, get_settings,
                     next_subcontractor_id, get_subcontractor_by_id, get_orders)
from utils.footer import show_legal_warning
from utils.masks import mask_phone
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="외주 파트너 — 순삭 OS", page_icon="🤝", layout="wide")
st.title("🤝 외주 파트너 관리")
st.caption("외주처 등록 · 연락처 마스킹 · 7일 보류금(10%) 자동 관리")

st.info(
    "🔒 **보안 정책:** 매니저는 외주처의 연락처를 직접 열람할 수 없습니다. "
    "모든 배정은 시스템 내 '배정 버튼'으로만 처리되며, 소통은 **법인폰**으로만 가능합니다."
)

settings = get_settings()
RETENTION_DAYS = settings.get("retention_days", 7)
RETENTION_RATE = settings.get("retention_rate", 0.10)

tab1, tab2, tab3, tab4 = st.tabs([
    "🏢 파트너 목록", "➕ 파트너 등록", "💰 외주비 정산 (보류금)", "📊 분석"
])

# ──────────────── Tab 1: 파트너 목록 ────────────────
with tab1:
    st.subheader("외주 파트너 목록")
    st.caption("🔒 연락처는 관리자(대표)만 확인 가능합니다. 매니저에게는 마스킹 처리됩니다.")

    subcontractors = get_subcontractors()
    role = st.radio("열람 권한", ["매니저", "관리자(대표)"], horizontal=True, key="role_select")
    is_admin = role == "관리자(대표)"

    if not subcontractors:
        st.info("등록된 외주 파트너가 없습니다.")
    else:
        for sc in subcontractors:
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    status_icon = "🟢" if sc.get("active") else "🔴"
                    st.markdown(f"### {status_icon} {sc['name']}")
                    st.markdown(f"📞 연락처: **{mask_phone(sc['phone'], 'admin' if is_admin else 'manager')}**")
                    st.markdown(f"📍 지역: {sc.get('region', '—')}")
                    st.markdown(f"🔧 전문: {'🔨 철거' if sc.get('specialty') == '철거' else '📦 수거'}")
                with col2:
                    st.markdown(f"⭐ 평점: **{sc.get('rating', '—')}**")
                    sat = sc.get("avg_satisfaction")
                    st.markdown(f"😊 고객만족도: **{sat if sat else '미집계'}**")
                    st.markdown(f"💰 단가: ₩{sc.get('unit_price_min', 0):,} ~ ₩{sc.get('unit_price_max', 0):,}")
                    st.markdown(f"📅 등록: {sc.get('registered_at', '—')}")
                with col3:
                    if st.button("📋 작업 배정", key=f"assign_sc_{sc['id']}"):
                        st.session_state[f"assign_sc_{sc['id']}"] = True
                    active = sc.get("active", True)
                    if st.button("⏸ 비활성" if active else "▶ 활성화", key=f"toggle_sc_{sc['id']}"):
                        sc["active"] = not active
                        save_subcontractor(sc)
                        st.rerun()

                if st.session_state.get(f"assign_sc_{sc['id']}"):
                    st.divider()
                    st.markdown(f"**{sc['name']} — 작업 배정**")
                    orders = get_orders()
                    available_orders = [o for o in orders if o["status"] in ("pending", "dispatched")]
                    if not available_orders:
                        st.warning("배정 가능한 주문이 없습니다.")
                    else:
                        sel_order = st.selectbox(
                            "주문 선택",
                            options=[f"#{o['id']} — {o['customer']} ({o.get('work_type', '수거')})" for o in available_orders],
                            key=f"sel_order_{sc['id']}"
                        )
                        order_idx = int(sel_order.split("#")[1].split(" ")[0]) - 1
                        sel_o = available_orders[order_idx] if order_idx < len(available_orders) else None

                        if sel_o:
                            amount = st.number_input(
                                "외주비 (원)",
                                min_value=sc.get("unit_price_min", 0),
                                max_value=sc.get("unit_price_max", 1000000),
                                value=sc.get("unit_price_min", 50000),
                                step=5000,
                                key=f"amount_{sc['id']}"
                            )
                            retention = int(amount * RETENTION_RATE)
                            net = amount - retention
                            st.info(
                                f"💰 외주비 ₩{amount:,} → **보류금(10%) ₩{retention:,}** 차감 → "
                                f"즉시 지급 ₩{net:,} | {RETENTION_DAYS}일 후 클레임 없으면 보류금 해제"
                            )
                            if st.button("✅ 배정 확정", key=f"confirm_{sc['id']}"):
                                add_subcontractor_job({
                                    "subcontractor_id": sc["id"],
                                    "subcontractor_name": sc["name"],
                                    "order_id": sel_o["id"],
                                    "total_amount": int(amount),
                                    "retention_amount": retention,
                                    "net_amount": net,
                                    "status": "retention_pending",
                                    "photo_before": None,
                                    "photo_after": None,
                                    "photo_cleanup": None,
                                    "claim_reported": False,
                                })
                                st.success(f"✅ {sc['name']} 배정 완료! 보류금 {RETENTION_DAYS}일 후 해제 예정")
                                st.session_state[f"assign_sc_{sc['id']}"] = False
                                st.rerun()
                st.divider()

# ──────────────── Tab 2: 파트너 등록 ────────────────
with tab2:
    st.subheader("신규 외주 파트너 등록")
    with st.form("sc_form"):
        col1, col2 = st.columns(2)
        with col1:
            sc_name = st.text_input("업체명", placeholder="한국이삿짐센터")
            sc_phone = st.text_input("연락처 (관리자만 열람)", placeholder="010-0000-0000")
            sc_specialty = st.selectbox("전문 분야", ["수거", "철거"])
            sc_region = st.text_input("담당 지역", placeholder="서울/경기")
        with col2:
            sc_unit_min = st.number_input("단가 최소 (원)", min_value=0, value=20000, step=5000)
            sc_unit_max = st.number_input("단가 최대 (원)", min_value=0, value=100000, step=5000)
            sc_rating = st.slider("초기 평점", 1.0, 5.0, 4.0, 0.1)

        submitted = st.form_submit_button("🤝 파트너 등록", type="primary")
        if submitted:
            if not all([sc_name, sc_phone]):
                st.error("업체명과 연락처는 필수입니다.")
            else:
                save_subcontractor({
                    "id": next_subcontractor_id(),
                    "name": sc_name,
                    "phone": sc_phone,
                    "specialty": sc_specialty,
                    "unit_price_min": int(sc_unit_min),
                    "unit_price_max": int(sc_unit_max),
                    "region": sc_region,
                    "rating": sc_rating,
                    "avg_satisfaction": None,
                    "active": True,
                    "registered_at": datetime.now().strftime("%Y-%m-%d"),
                })
                st.success(f"✅ {sc_name} 등록 완료!")
                st.rerun()

# ──────────────── Tab 3: 외주비 정산 (보류금) ────────────────
with tab3:
    st.subheader(f"💰 외주비 정산 — 보류금 관리 (7일 보류, 10% 차감)")
    st.info(
        f"📌 보류금 정책: 외주비의 {int(RETENTION_RATE*100)}%를 {RETENTION_DAYS}일간 보류 후, "
        "클레임 없을 시 자동 지급 활성화"
    )

    jobs = get_subcontractor_jobs()
    if not jobs:
        st.info("외주비 정산 내역이 없습니다.")
    else:
        now = datetime.now()
        for job in jobs:
            sc = get_subcontractor_by_id(job.get("subcontractor_id"))
            sc_name = job.get("subcontractor_name", sc["name"] if sc else "—")

            try:
                due_dt = datetime.strptime(job.get("retention_due_date", ""), "%Y-%m-%d %H:%M")
                retention_released = now >= due_dt
                days_left = max(0, (due_dt - now).days)
            except Exception:
                retention_released = False
                days_left = RETENTION_DAYS

            claim = job.get("claim_reported", False)
            status = job.get("status", "retention_pending")

            with st.container():
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.markdown(f"**{sc_name}** — 주문 #{job.get('order_id', '—')}")
                    st.caption(f"등록: {job.get('created_at', '—')}")
                with col2:
                    st.markdown(f"총액: **₩{job.get('total_amount', 0):,}**")
                    st.markdown(f"즉시지급: ₩{job.get('net_amount', 0):,}")
                    st.markdown(f"보류금: ₩{job.get('retention_amount', 0):,}")
                with col3:
                    if claim:
                        st.error(f"🚨 클레임 신고됨 — 보류금 지급 보류")
                    elif status == "paid":
                        st.success("✅ 보류금 지급 완료")
                    elif retention_released:
                        st.success(f"✅ 보류 기간 종료 — 지급 가능!")
                        if st.button("💸 보류금 지급 처리", key=f"pay_retention_{job['id']}"):
                            update_subcontractor_job(job["id"], {"status": "paid"})
                            st.success("보류금 지급 처리 완료!")
                            st.rerun()
                    else:
                        st.warning(f"⏳ 보류 중 (잔여 {days_left}일) — 만료일: {job.get('retention_due_date', '—')[:10]}")

                    if not claim and status != "paid":
                        if st.button("🚨 클레임 신고", key=f"claim_{job['id']}"):
                            update_subcontractor_job(job["id"], {"claim_reported": True})
                            st.error("클레임 신고됨 — 보류금 지급 중단")
                            st.rerun()

                st.markdown("**📷 작업 완료 보고서**")
                photo_cols = st.columns(3)
                photos = [
                    ("작업 전", "photo_before"),
                    ("작업 후", "photo_after"),
                    ("정리 정돈", "photo_cleanup")
                ]
                for pidx, (label, field) in enumerate(photos):
                    with photo_cols[pidx]:
                        val = job.get(field)
                        if val:
                            st.success(f"✅ {label}")
                        else:
                            st.error(f"⚠️ {label} 미업로드")
                            up = st.file_uploader(f"{label} 사진", type=["jpg", "png", "jpeg"],
                                                  key=f"sc_photo_{job['id']}_{field}",
                                                  label_visibility="collapsed")
                            if up and st.button(f"저장", key=f"save_{job['id']}_{field}"):
                                update_subcontractor_job(job["id"], {field: up.name})
                                st.success(f"{label} 저장됨")
                                st.rerun()
                st.divider()

# ──────────────── Tab 4: 분석 ────────────────
with tab4:
    st.subheader("외주 파트너 분석")
    subcontractors = get_subcontractors()
    jobs = get_subcontractor_jobs()

    if not subcontractors:
        st.info("등록된 외주 파트너가 없습니다.")
    else:
        rows = []
        for sc in subcontractors:
            sc_jobs = [j for j in jobs if j.get("subcontractor_id") == sc["id"]]
            total_paid = sum(j.get("total_amount", 0) for j in sc_jobs if j.get("status") == "paid")
            pending_retention = sum(j.get("retention_amount", 0) for j in sc_jobs if j.get("status") == "retention_pending")
            claims = sum(1 for j in sc_jobs if j.get("claim_reported"))
            rows.append({
                "파트너명": sc["name"],
                "전문": sc.get("specialty", "—"),
                "지역": sc.get("region", "—"),
                "평점": sc.get("rating", "—"),
                "만족도": sc.get("avg_satisfaction", "미집계"),
                "총 배정건": len(sc_jobs),
                "지급 완료": f"₩{total_paid:,}",
                "보류금 잔액": f"₩{pending_retention:,}",
                "클레임": f"{claims}건" if claims else "—",
                "상태": "🟢 활성" if sc.get("active") else "🔴 비활성",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

show_legal_warning()
