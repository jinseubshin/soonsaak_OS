import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import get_orders, get_drivers, get_settings, update_order, save_settings
from utils.footer import show_legal_warning
from utils.masks import mask_phone
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="지역 관리 — 순삭 OS", page_icon="🗺️", layout="wide")
st.title("🗺️ 멀티 지역 관리")
st.caption("지역별 리드 현황 · 기사 배정 · 정산 요약 · 매니저 권한 분리")

settings = get_settings()
managers = settings.get("managers", [])
regions = settings.get("regions", ["본사", "세종"])
region_labels = settings.get("region_labels", {})

MARKETING_CHANNELS = ["당근마켓", "네이버 플레이스", "카카오 채널", "인스타그램/SNS", "지인 추천", "블로그/기사", "기타"]

# ── 뷰 모드
view_mode = st.sidebar.radio(
    "보기 모드",
    ["🏢 전체 (대표/관리자)"] + [f"🗺️ {r} 지역 매니저" for r in regions if r != "본사"],
    help="역할에 따라 열람 범위가 제한됩니다"
)

if view_mode == "🏢 전체 (대표/관리자)":
    active_region = None
    is_admin = True
else:
    active_region = view_mode.replace("🗺️ ", "").replace(" 지역 매니저", "")
    is_admin = False
    st.info(
        f"🗺️ **{active_region} 지역 매니저 뷰** — "
        f"{active_region} 지역 리드와 담당 기사만 표시됩니다.\n\n"
        f"⚖️ 법인폰 로그는 회사의 자산이며 운영 투명성을 위해 관리됩니다 (계약서 제48조 준수)."
    )

orders = get_orders()
drivers = get_drivers()

# 지역 필터 적용
if not is_admin and active_region:
    orders = [o for o in orders if o.get("region") == active_region]
    drivers = [d for d in drivers if d.get("region") == active_region]

# ── 탭 구성 (관리자: 5탭 / 지역 매니저: 4탭)
if is_admin:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 지역 대시보드",
        "📋 지역별 리드 현황",
        "👷 지역 기사 현황",
        "💰 지역 정산 요약",
        "📈 세종 ROI 추적",
    ])
else:
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 지역 대시보드",
        "📋 지역별 리드 현황 (수거/철거)",
        "👷 지역 기사 현황",
        "💰 지역 정산 요약",
    ])
    tab5 = None


# ──────────────── Tab 1: 지역 대시보드 ────────────────
with tab1:
    if is_admin:
        st.subheader("📊 전체 지역 현황 (대표/관리자)")

        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        with col_h1:
            st.metric("등록 지역", f"{len(regions)}개")
        with col_h2:
            st.metric("총 매니저", f"{len(managers)}명")
        with col_h3:
            st.metric("총 주문", f"{len(orders)}건")
        with col_h4:
            st.metric("총 기사", f"{len(drivers)}명")

        st.divider()

        # 지역별 현황 카드
        region_cols = st.columns(min(len(regions), 3))
        for idx, region in enumerate(regions):
            with region_cols[idx % min(len(regions), 3)]:
                r_orders = [o for o in get_orders() if o.get("region") == region]
                r_drivers = [d for d in get_drivers() if d.get("region") == region]
                r_managers = [m for m in managers if m["region"] == region]
                r_pending = len([o for o in r_orders if o["status"] == "pending"])
                r_completed = len([o for o in r_orders if o["status"] == "completed"])
                r_collection = len([o for o in r_orders if o.get("work_type") == "수거"])
                r_demolition = len([o for o in r_orders if o.get("work_type") == "철거"])
                r_revenue = sum(
                    (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
                    for o in r_orders if o.get("payment_confirmed")
                )

                labels = region_labels.get(region, {})
                base_cost_label = labels.get("manager_base_cost", "운영비")

                st.markdown(
                    f"<div style='background:#f0f4ff;border-radius:12px;padding:16px;"
                    f"border-left:4px solid #4c8df5'>"
                    f"<h3 style='margin:0'>🗺️ {region}</h3>"
                    f"<p style='margin:4px 0;color:#555'>매니저: {', '.join([m['name'] for m in r_managers]) or '미배정'}</p>"
                    f"<hr style='margin:8px 0'>"
                    f"<p>📋 전체 주문: <b>{len(r_orders)}건</b></p>"
                    f"<p>📦 수거: <b>{r_collection}건</b> | 🔨 철거: <b>{r_demolition}건</b></p>"
                    f"<p>⏳ 대기 중: <b>{r_pending}건</b></p>"
                    f"<p>✅ 완료: <b>{r_completed}건</b></p>"
                    f"<p>👷 담당 기사: <b>{len(r_drivers)}명</b></p>"
                    f"<p>💰 확정 매출: <b>₩{r_revenue:,}</b></p>"
                    f"<p style='font-size:12px;color:#888'>정산 명칭: {base_cost_label}</p>"
                    f"</div>",
                    unsafe_allow_html=True
                )

        st.divider()

        # 신규 주문에 지역 수동 배정
        st.subheader("🏷️ 주문 지역 배정")
        st.caption("CS 접수 시 지역이 지정되지 않은 주문을 수동으로 지역에 배정합니다.")
        region_assign_all = get_orders()
        assign_opts = {f"#{o['id']} {o['customer']} ({o['status']})": o for o in region_assign_all}
        if assign_opts:
            sel_assign = st.selectbox("주문 선택", list(assign_opts.keys()))
            sel_order = assign_opts[sel_assign]
            sel_region = st.selectbox("배정 지역", regions, index=regions.index(sel_order.get("region", regions[0])) if sel_order.get("region") in regions else 0)
            if st.button("지역 배정 저장"):
                update_order(sel_order["id"], {"region": sel_region})
                st.success(f"주문 #{sel_order['id']} → {sel_region} 지역 배정 완료!")
                st.rerun()
    else:
        # 세종 매니저 뷰: 자기 지역 요약 + 수거/철거 분리 현황
        st.subheader(f"📊 {active_region} 지역 현황")

        _reg_collection = [o for o in orders if o.get("work_type") == "수거"]
        _reg_demolition = [o for o in orders if o.get("work_type") == "철거"]

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("📦 수거 총", f"{len(_reg_collection)}건")
        with col2:
            st.metric("🔨 철거 총", f"{len(_reg_demolition)}건")
        with col3:
            st.metric("⏳ 대기", f"{len([o for o in orders if o['status']=='pending'])}건")
        with col4:
            st.metric("🔄 진행 중", f"{len([o for o in orders if o['status']=='in_progress'])}건")
        with col5:
            st.metric("✅ 완료", f"{len([o for o in orders if o['status']=='completed'])}건")
        with col6:
            st.metric("👷 담당 기사", f"{len(drivers)}명")

        r_managers = [m for m in managers if m["region"] == active_region]
        if r_managers:
            st.markdown("**담당 매니저:**")
            for m in r_managers:
                st.markdown(f"- {m['name']} ({m['role']}) — 법인폰: `{m.get('corporate_phone','—')}`")

        labels = region_labels.get(active_region, {})
        base_cost_label = labels.get("manager_base_cost", "운영비")
        st.caption(f"📌 정산 명칭 — {base_cost_label} (설정에서 변경 가능)")


# ──────────────── Tab 2: 지역별 리드 현황 ────────────────
with tab2:
    status_map = {
        "pending": "⏳ 대기", "dispatched": "📍 배차",
        "in_progress": "🔄 진행중", "completed": "✅ 완료", "cancelled": "❌ 취소",
    }

    if is_admin:
        # ── 관리자: 전체 리드 조회 (기존 방식)
        st.subheader("📋 전체 지역 리드 현황")
        region_filter_sel = st.selectbox("지역 필터", ["전체"] + regions)
        display_orders = get_orders()
        if region_filter_sel and region_filter_sel != "전체":
            display_orders = [o for o in display_orders if o.get("region") == region_filter_sel]

        if not display_orders:
            st.info("해당 지역 주문이 없습니다.")
        else:
            rows = []
            for o in sorted(display_orders, key=lambda x: x.get("scheduled_time", ""), reverse=True):
                phone_masked = mask_phone(o["customer_phone"], "admin")
                confirmed_price = o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"]
                rows.append({
                    "주문": f"#{o['id']}",
                    "고객": o["customer"],
                    "연락처": phone_masked,
                    "지역": o.get("region", "본사"),
                    "작업": "🔨 철거" if o.get("work_type") == "철거" else "📦 수거",
                    "유입경로": o.get("marketing_channel") or "—",
                    "예약": o.get("scheduled_time", "—")[:16],
                    "금액": f"₩{confirmed_price:,}",
                    "상태": status_map.get(o["status"], o["status"]),
                    "견적확정": "✅" if o.get("manager_quote_confirmed") else ("🔨" if o.get("work_type") == "철거" else "—"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    else:
        # ── 세종 매니저 뷰: 수거 / 철거 탭 분리
        st.subheader(f"📋 {active_region} 지역 리드 현황 — 수거 / 철거 분리 관리")
        st.caption(f"세종 지역은 수거와 철거 모두 취급합니다. 각 탭에서 해당 작업 유형의 리드를 관리하세요.")

        sub_col, sub_demo = st.tabs(["📦 수거 관리", "🔨 철거 관리"])

        def _order_rows(order_list):
            rows = []
            for o in sorted(order_list, key=lambda x: x.get("scheduled_time", ""), reverse=True):
                phone_masked = mask_phone(o["customer_phone"], "manager")
                confirmed_price = o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"]
                rows.append({
                    "주문": f"#{o['id']}",
                    "고객": o["customer"],
                    "연락처": phone_masked,
                    "유입경로": o.get("marketing_channel") or "—",
                    "예약": o.get("scheduled_time", "—")[:16],
                    "금액": f"₩{confirmed_price:,}",
                    "상태": status_map.get(o["status"], o["status"]),
                    "수당": f"₩{o.get('job_allowance', 0):,}",
                })
            return rows

        # 수거 탭
        with sub_col:
            _coll_orders = [o for o in orders if o.get("work_type") == "수거"]
            _coll_pending = [o for o in _coll_orders if o["status"] == "pending"]
            _coll_done = [o for o in _coll_orders if o["status"] == "completed"]
            _coll_rev = sum(
                (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
                for o in _coll_orders if o.get("payment_confirmed")
            )
            _coll_allow = sum(o.get("job_allowance", 0) for o in _coll_done)

            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("📦 수거 전체", f"{len(_coll_orders)}건")
            with c2: st.metric("⏳ 대기", f"{len(_coll_pending)}건")
            with c3: st.metric("✅ 완료", f"{len(_coll_done)}건")
            with c4: st.metric("💰 확정 매출", f"₩{_coll_rev:,}")

            st.caption(f"기사 수당 합계: ₩{_coll_allow:,}")

            if not _coll_orders:
                st.info("세종 지역 수거 건이 없습니다.")
            else:
                _coll_filter = st.selectbox(
                    "상태 필터",
                    ["전체", "⏳ 대기", "📍 배차", "🔄 진행중", "✅ 완료", "❌ 취소"],
                    key="coll_filter"
                )
                _filtered_coll = _coll_orders
                if _coll_filter != "전체":
                    _rev_status = {v: k for k, v in status_map.items()}
                    _fs = _rev_status.get(_coll_filter)
                    if _fs:
                        _filtered_coll = [o for o in _coll_orders if o["status"] == _fs]
                st.dataframe(pd.DataFrame(_order_rows(_filtered_coll)), use_container_width=True, hide_index=True)

        # 철거 탭
        with sub_demo:
            _demo_orders = [o for o in orders if o.get("work_type") == "철거"]
            _demo_pending = [o for o in _demo_orders if o["status"] == "pending"]
            _demo_done = [o for o in _demo_orders if o["status"] == "completed"]
            _demo_rev = sum(
                (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
                for o in _demo_orders if o.get("payment_confirmed")
            )
            _demo_allow = sum(o.get("job_allowance", 0) for o in _demo_done)
            _demo_unconfirmed = [o for o in _demo_orders if not o.get("manager_quote_confirmed")]

            d1, d2, d3, d4 = st.columns(4)
            with d1: st.metric("🔨 철거 전체", f"{len(_demo_orders)}건")
            with d2:
                st.metric(
                    "📋 견적 미확정",
                    f"{len(_demo_unconfirmed)}건",
                    delta=f"즉시 확정 필요" if _demo_unconfirmed else None,
                    delta_color="inverse" if _demo_unconfirmed else "normal"
                )
            with d3: st.metric("✅ 완료", f"{len(_demo_done)}건")
            with d4: st.metric("💰 확정 매출", f"₩{_demo_rev:,}")

            st.caption(f"기사 수당 합계: ₩{_demo_allow:,}")

            if _demo_unconfirmed:
                st.warning(f"⚠️ 매니저 견적 미확정 {len(_demo_unconfirmed)}건 — 현장 조건 확인 후 즉시 견적을 확정해주세요.")

            if not _demo_orders:
                st.info("세종 지역 철거 건이 없습니다.")
            else:
                _demo_filter = st.selectbox(
                    "상태 필터",
                    ["전체", "⏳ 대기", "📍 배차", "🔄 진행중", "✅ 완료", "❌ 취소"],
                    key="demo_filter"
                )
                _filtered_demo = _demo_orders
                if _demo_filter != "전체":
                    _rev_status2 = {v: k for k, v in status_map.items()}
                    _fs2 = _rev_status2.get(_demo_filter)
                    if _fs2:
                        _filtered_demo = [o for o in _demo_orders if o["status"] == _fs2]
                st.dataframe(pd.DataFrame(_order_rows(_filtered_demo)), use_container_width=True, hide_index=True)

        # 세종 통합 실적 요약
        st.divider()
        st.markdown(f"#### 🎯 {active_region} 통합 실적 — 수거 + 철거 합산")
        _total_orders = orders
        _total_done = [o for o in _total_orders if o["status"] == "completed"]
        _total_rev = sum(
            (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
            for o in _total_orders if o.get("payment_confirmed")
        )
        t1, t2, t3, t4 = st.columns(4)
        with t1: st.metric("전체 리드", f"{len(_total_orders)}건")
        with t2: st.metric("📦 수거 완료", f"{len(_coll_done)}건")
        with t3: st.metric("🔨 철거 완료", f"{len(_demo_done)}건")
        with t4: st.metric("💰 총 확정 매출", f"₩{_total_rev:,}")
        st.caption("📌 기사 월 40건 목표치는 수거 + 철거 통합 건수로 산정됩니다.")


# ──────────────── Tab 3: 지역 기사 현황 ────────────────
with tab3:
    st.subheader(f"👷 {'전체' if is_admin else active_region} 지역 기사 현황")

    all_drivers = get_drivers()
    region_drv_filter = st.selectbox("지역 필터", ["전체"] + regions, key="drv_filter") if is_admin else None
    display_drivers = all_drivers
    if not is_admin:
        display_drivers = [d for d in all_drivers if d.get("region") == active_region]
    elif region_drv_filter and region_drv_filter != "전체":
        display_drivers = [d for d in all_drivers if d.get("region") == region_drv_filter]

    if not display_drivers:
        st.info("해당 지역 기사가 없습니다.")
    else:
        rows_d = []
        for d in display_drivers:
            _total_monthly = d.get("monthly_jobs", 0)
            _coll_monthly = d.get("collection_jobs", 0)
            _demo_monthly = d.get("demolition_jobs", 0)
            rows_d.append({
                "기사명": d["name"],
                "지역": d.get("region", "본사"),
                "유형": d.get("driver_type", "직영"),
                "📦수거(건)": _coll_monthly,
                "🔨철거(건)": _demo_monthly,
                "이달 총(40건 목표)": f"{_total_monthly}건",
                "달성률": f"{min(100, round(_total_monthly/40*100))}%",
                "평점": f"⭐ {d.get('rating', '—')}",
                "가용": "✅" if d.get("available") else "❌",
            })
        st.dataframe(pd.DataFrame(rows_d), use_container_width=True, hide_index=True)
        st.caption("📌 달성률 = (수거건 + 철거건) ÷ 40건 목표 — 두 업무 유형 통합 계산")

        if is_admin:
            st.markdown("#### 기사 지역 변경")
            drv_opts = {f"{d['name']} (현재: {d.get('region','본사')})": d for d in all_drivers}
            sel_drv_k = st.selectbox("기사 선택", list(drv_opts.keys()))
            sel_drv = drv_opts[sel_drv_k]
            new_drv_region = st.selectbox("새 담당 지역", regions, key="new_drv_region")
            if st.button("기사 지역 변경 저장"):
                from data.db import _load, _save
                data = _load()
                for d in data["drivers"]:
                    if d["id"] == sel_drv["id"]:
                        d["region"] = new_drv_region
                _save(data)
                st.success(f"{sel_drv['name']} → {new_drv_region} 지역 변경 완료!")
                st.rerun()


# ──────────────── Tab 4: 지역 정산 요약 ────────────────
with tab4:
    st.subheader(f"💰 {'전체' if is_admin else active_region} 지역 정산 요약")

    all_orders_for_settle = get_orders()

    if is_admin:
        st.markdown("#### 지역별 정산 요약")
        settle_rows = []
        for region in regions:
            r_orders = [o for o in all_orders_for_settle if o.get("region") == region and o.get("payment_confirmed")]
            revenue = sum(
                (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
                for o in r_orders
            )
            _rc = len([o for o in r_orders if o.get("work_type") == "수거"])
            _rd = len([o for o in r_orders if o.get("work_type") == "철거"])
            labels = region_labels.get(region, {})
            base_cost_label = labels.get("manager_base_cost", "운영비")
            r_mgrs = [m for m in managers if m["region"] == region]
            settle_rows.append({
                "지역": region,
                "확정 매출": f"₩{revenue:,}",
                "완료 건수(수거)": _rc,
                "완료 건수(철거)": _rd,
                "정산 명칭": base_cost_label,
                "담당 매니저": ", ".join([m["name"] for m in r_mgrs]) or "—",
            })
        st.dataframe(pd.DataFrame(settle_rows), use_container_width=True, hide_index=True)
        st.divider()

    # 지역 상세 정산
    settle_region = active_region if not is_admin else st.selectbox("지역 선택", regions, key="settle_region_sel")
    labels = region_labels.get(settle_region, {})
    base_cost_label = labels.get("manager_base_cost", "운영비")
    incentive_label = labels.get("incentive", "인센티브")
    activity_label = labels.get("region_activity", "지역 활동비")
    allowance_label = labels.get("driver_allowance", "기사 수당")

    st.markdown(f"#### 🗺️ {settle_region} 지역 정산 상세")
    st.caption(f"항목 명칭 커스텀 적용: {base_cost_label} / {incentive_label} / {allowance_label}")

    r_orders_settled = [
        o for o in all_orders_for_settle
        if o.get("region") == settle_region and o.get("payment_confirmed")
    ]

    if not r_orders_settled:
        st.info(f"{settle_region} 지역 확정 정산 건이 없습니다.")
    else:
        total_rev = sum(
            (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
            for o in r_orders_settled
        )
        # 수거/철거 수당 분리
        coll_allow = sum(o.get("job_allowance", 0) for o in r_orders_settled if o.get("work_type") == "수거")
        demo_allow = sum(o.get("job_allowance", 0) for o in r_orders_settled if o.get("work_type") == "철거")
        total_allowance = coll_allow + demo_allow
        demo_incentive_orders = [
            o for o in r_orders_settled
            if o.get("work_type") == "철거" and o.get("manager_closed")
        ]
        demo_incentive = len(demo_incentive_orders) * settings.get("demolition_incentive_min", 50000)

        col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
        with col_s1:
            st.metric("총 확정 매출", f"₩{total_rev:,}")
        with col_s2:
            st.metric("📦 수거 수당", f"₩{coll_allow:,}")
        with col_s3:
            st.metric("🔨 철거 수당", f"₩{demo_allow:,}")
        with col_s4:
            st.metric(incentive_label, f"₩{demo_incentive:,}")
        with col_s5:
            st.metric(base_cost_label, f"₩{settings.get('manager_base_cost', 1500000):,}/월")

        st.caption(f"💡 수거·철거 수당은 건당 계약 규정에 따라 자동 분리 계산됩니다.")

        rows_s = []
        for o in r_orders_settled:
            confirmed_price = o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"]
            rows_s.append({
                "주문": f"#{o['id']}",
                "고객": o["customer"],
                "작업": "🔨 철거" if o.get("work_type") == "철거" else "📦 수거",
                "확정금액": f"₩{confirmed_price:,}",
                allowance_label: f"₩{o.get('job_allowance',0):,}",
                "매니저성사": "👔" if o.get("manager_closed") else "—",
            })
        st.dataframe(pd.DataFrame(rows_s), use_container_width=True, hide_index=True)


# ──────────────── Tab 5: 세종 ROI 추적 (관리자 전용) ────────────────
if tab5 is not None:
    with tab5:
        st.subheader("📈 세종 지역 마케팅 ROI 추적 — 대표자 대시보드")
        st.caption("세종 지역 주문에 등록된 유입 경로별 통계를 분석합니다.")

        _roi_region = st.selectbox("분석 지역", regions, index=regions.index("세종") if "세종" in regions else 0, key="roi_region_sel")
        all_roi_orders = [o for o in get_orders() if o.get("region") == _roi_region]

        if not all_roi_orders:
            st.info(f"{_roi_region} 지역 주문이 없습니다.")
        else:
            # ── 헤드라인 지표
            _roi_total = len(all_roi_orders)
            _roi_done = [o for o in all_roi_orders if o["status"] == "completed"]
            _roi_rev = sum(
                (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
                for o in all_roi_orders if o.get("payment_confirmed")
            )
            _roi_coll = len([o for o in all_roi_orders if o.get("work_type") == "수거"])
            _roi_demo = len([o for o in all_roi_orders if o.get("work_type") == "철거"])

            hc1, hc2, hc3, hc4 = st.columns(4)
            with hc1: st.metric("전체 리드", f"{_roi_total}건")
            with hc2: st.metric("📦 수거", f"{_roi_coll}건")
            with hc3: st.metric("🔨 철거", f"{_roi_demo}건")
            with hc4: st.metric("💰 확정 매출", f"₩{_roi_rev:,}")

            st.divider()

            # ── 유입 경로별 분석
            st.markdown("#### 📊 유입 경로별 실적")

            _channel_stats = {}
            for ch in MARKETING_CHANNELS + ["미등록"]:
                if ch == "미등록":
                    ch_orders = [o for o in all_roi_orders if not o.get("marketing_channel")]
                else:
                    ch_orders = [o for o in all_roi_orders if o.get("marketing_channel") == ch]

                if not ch_orders:
                    continue
                ch_done = [o for o in ch_orders if o["status"] == "completed"]
                ch_rev = sum(
                    (o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"])
                    for o in ch_orders if o.get("payment_confirmed")
                )
                ch_conv = round(len(ch_done) / max(len(ch_orders), 1) * 100, 1)
                ch_coll = len([o for o in ch_orders if o.get("work_type") == "수거"])
                ch_demo = len([o for o in ch_orders if o.get("work_type") == "철거"])
                _channel_stats[ch] = {
                    "유입": len(ch_orders),
                    "수거": ch_coll,
                    "철거": ch_demo,
                    "완료": len(ch_done),
                    "전환율": f"{ch_conv}%",
                    "확정매출": f"₩{ch_rev:,}",
                    "_rev": ch_rev,
                }

            if _channel_stats:
                _df_ch = pd.DataFrame([
                    {
                        "유입경로": k,
                        "리드 수": v["유입"],
                        "📦 수거": v["수거"],
                        "🔨 철거": v["철거"],
                        "완료": v["완료"],
                        "전환율": v["전환율"],
                        "확정 매출": v["확정매출"],
                    }
                    for k, v in sorted(_channel_stats.items(), key=lambda x: -x[1]["_rev"])
                ])
                st.dataframe(_df_ch, use_container_width=True, hide_index=True)

                # ── 최고 ROI 채널 하이라이트
                st.divider()
                st.markdown("#### 🥇 채널별 성과 하이라이트")
                _sorted_ch = sorted(_channel_stats.items(), key=lambda x: -x[1]["_rev"])
                ch_highlight_cols = st.columns(min(len(_sorted_ch), 4))
                for _ci, (ch_name, ch_data) in enumerate(_sorted_ch[:4]):
                    with ch_highlight_cols[_ci]:
                        _rank_icon = ["🥇", "🥈", "🥉", "4️⃣"][_ci]
                        st.markdown(
                            f"<div style='background:#f8f9ff;border-radius:10px;padding:12px;"
                            f"border-left:4px solid #4c8df5;text-align:center'>"
                            f"<div style='font-size:22px'>{_rank_icon}</div>"
                            f"<b>{ch_name}</b><br>"
                            f"<span style='font-size:13px'>리드 {ch_data['유입']}건</span><br>"
                            f"<span style='font-size:13px'>전환율 {ch_data['전환율']}</span><br>"
                            f"<b style='color:#4c8df5'>{ch_data['확정매출']}</b>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                # ── 유입경로 미등록 주문 관리
                _untagged = [o for o in all_roi_orders if not o.get("marketing_channel")]
                if _untagged:
                    st.divider()
                    st.warning(f"⚠️ 유입 경로 미등록 주문 {len(_untagged)}건 — CS에서 유입 경로를 입력해주세요.")
                    with st.expander(f"미등록 주문 목록 ({len(_untagged)}건)", expanded=False):
                        _utag_rows = []
                        for o in _untagged:
                            _utag_rows.append({
                                "주문": f"#{o['id']}",
                                "고객": o["customer"],
                                "작업": "🔨 철거" if o.get("work_type") == "철거" else "📦 수거",
                                "예약": o.get("scheduled_time", "—")[:16],
                                "상태": status_map.get(o["status"], o["status"]),
                            })
                        st.dataframe(pd.DataFrame(_utag_rows), use_container_width=True, hide_index=True)

                        # 일괄 채널 등록
                        st.markdown("**유입 경로 일괄 등록**")
                        _batch_ch = st.selectbox("채널 선택", MARKETING_CHANNELS, key="batch_channel_sel")
                        _batch_order_opts = {f"#{o['id']} {o['customer']}": o for o in _untagged}
                        _batch_sel = st.multiselect("주문 선택", list(_batch_order_opts.keys()), key="batch_orders_sel")
                        if st.button("📝 선택 주문에 유입경로 등록", key="batch_channel_save") and _batch_sel:
                            for _k in _batch_sel:
                                _bo = _batch_order_opts[_k]
                                update_order(_bo["id"], {"marketing_channel": _batch_ch})
                            st.success(f"✅ {len(_batch_sel)}건 → {_batch_ch} 등록 완료!")
                            st.rerun()

            # ── 월별 채널 트렌드
            st.divider()
            st.markdown("#### 📅 월별 유입 트렌드")
            _month_stats = {}
            for o in all_roi_orders:
                _sched = o.get("scheduled_time", "")[:7]  # YYYY-MM
                if not _sched:
                    continue
                _month_stats.setdefault(_sched, {"총": 0, "수거": 0, "철거": 0, "매출": 0})
                _month_stats[_sched]["총"] += 1
                if o.get("work_type") == "수거":
                    _month_stats[_sched]["수거"] += 1
                else:
                    _month_stats[_sched]["철거"] += 1
                if o.get("payment_confirmed"):
                    _confirmed = o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"]
                    _month_stats[_sched]["매출"] += _confirmed

            if _month_stats:
                _trend_rows = [
                    {
                        "월": m,
                        "총 리드": v["총"],
                        "📦 수거": v["수거"],
                        "🔨 철거": v["철거"],
                        "확정 매출": f"₩{v['매출']:,}",
                    }
                    for m, v in sorted(_month_stats.items())
                ]
                st.dataframe(pd.DataFrame(_trend_rows), use_container_width=True, hide_index=True)

show_legal_warning()
