import streamlit as st
from utils.tax_calc import calc_driver_settlement, format_tax_badge, TAX_TYPE_BUSINESS
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (get_orders, get_drivers, get_settings, update_order,
                     get_driver_by_id, get_ace_bonuses, add_ace_bonus,
                     get_monthly_allowances, save_monthly_allowances,
                     get_subcontractor_jobs)
from utils.footer import show_legal_warning
from utils.rbac import render_role_selector, is_owner, is_manager, is_executor, is_cs, role_badge
import pandas as pd

st.set_page_config(page_title="정산 엔진 — 순삭 OS", page_icon="💵", layout="wide")
st.title("💵 정산 엔진")
st.caption("입금 확인 · 건당 수당 입력 · Ace Bonus · 조건부 운영비 시각화 · 본사 순익 시뮬레이터")

render_role_selector()
st.markdown(role_badge(), unsafe_allow_html=True)
st.markdown("")

# CS: 마진·정산 데이터 전체 차단
if is_cs():
    st.error(
        "🚫 **CS 상담원은 정산 엔진에 접근할 수 없습니다.**\n\n"
        "마진·수익·기사 지급 정보는 매니저/대표 전용 데이터입니다.\n"
        "사이드바에서 역할을 변경하거나 매니저에게 문의하세요."
    )
    st.stop()

# Executor: 본인 수당 명세서만 접근 가능 (전체 정산 데이터 차단)
if is_executor():
    from data.db import get_orders, get_drivers, get_driver_by_id
st.info("🚗 **실행팀 모드** — 본인 수당 명세서만 표시됩니다...")
st.subheader("📋 내 수당 명세서")
    all_orders = get_orders()
IndentationError: unexpected indent
    # 기사 이름으로 본인 주문만 필터 (기사 앱과 동일한 방식으로 매칭)
    _drv_name = st.session_state.get("_executor_name", "")
    _exec_orders = [
        o for o in all_orders
        if o.get("status") == "completed" and str(o.get("driver_id", "")) != ""
    ]
    if not _exec_orders:
        st.info("완료된 배정 건이 없습니다.")
    else:
        _exec_settings = get_settings()
        _exec_ratio = _exec_settings.get("driver_ratio", 0.70)
        for o in _exec_orders:
            _drv = get_driver_by_id(o.get("driver_id"))
            _eff = o.get("manager_quote") if (o.get("work_type") == "철거" and o.get("manager_quote_confirmed")) else o["base_fee"]
            _extra = o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0
            _total = _eff + _extra
            _pay = _total * _exec_ratio
            _penalty = o.get("penalty_amount", 0)
            _allowance = max(0, o.get("job_allowance", 0) - _penalty)
            _t = calc_driver_settlement(_pay, _drv or {})
            if _t["tax_type"] == TAX_TYPE_BUSINESS:
                _tax_str = (
                    f"공급가 ₩{int(_t['supply_amount']):,} + 부가세 ₩{int(_t['vat']):,} | "
                    f"총지급 ₩{int(_t['net_pay']):,}"
                )
            else:
                _tax_str = f"원천세 -₩{int(_t['withholding']):,} | 실지급 ₩{int(_t['net_pay']):,}"
            with st.container():
                st.markdown(
                    f"**주문 #{o['id']}** — {o['customer']} | "
                    f"지급액 **₩{_pay:,.0f}** [{_t['label']}] | {_tax_str} | "
                    f"건당수당 ₩{_allowance:,}"
                )
    show_legal_warning()
    st.stop()

settings = get_settings()
DRIVER_RATIO = settings["driver_ratio"]
CS_RATIO = settings["cs_ratio"]
SUCCESS_FEE_RATIO = settings["success_fee_ratio"]
DISPATCH_FEE = settings["dispatch_fee"]
WITHHOLDING = settings["withholding_tax_rate"]
DIRECT_THRESHOLD = settings.get("direct_team_threshold", 40)
FULL_COST = settings.get("direct_team_full_cost", 1500000)
HALF_COST = settings.get("direct_team_half_cost", 750000)
AD_COST_RATE = settings.get("ad_cost_rate", 0.10)

DEMO_INCENTIVE_MIN = settings.get("demolition_incentive_min", 50000)
DEMO_INCENTIVE_MAX = settings.get("demolition_incentive_max", 100000)
MANAGER_BASE = settings.get("manager_base_cost", 1500000)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "💰 주문별 정산",
    "🔧 건당 수당 입력",
    "📊 기사별 정산 요약",
    "🏆 Ace Bonus",
    "⚙️ 입금 확인",
    "👔 매니저 인센티브",
    "🧮 본사 순익 시뮬레이터",
])

# ──────────────── Tab 1: 주문별 정산 ────────────────
with tab1:
    st.subheader("주문별 자동 정산 계산")
    st.info(f"📌 기사 {DRIVER_RATIO*100:.0f}% | CS {CS_RATIO*100:.0f}% | 성공보수 {SUCCESS_FEE_RATIO*100:.0f}% | 출동비 ₩{DISPATCH_FEE:,}")

    orders = get_orders()
    completed_orders = [o for o in orders if o["status"] == "completed"]
    if not completed_orders:
        st.info("완료된 주문이 없습니다.")
    else:
        rows = []
        for o in completed_orders:
            drv = get_driver_by_id(o.get("driver_id"))
            extra = o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0

            # 철거 건: 매니저 확정 견적을 기준가로 사용 (하위 호환)
            if o.get("work_type") == "철거" and o.get("manager_quote_confirmed") and o.get("manager_quote"):
                effective_base = o["manager_quote"]
                base_label = "매니저확정가"
            else:
                effective_base = o["base_fee"]
                base_label = "기본요금"

            if o.get("arbitrary_fee_flag"):
                total_revenue = effective_base
                driver_pay = 0
                note = "🚨 임의추가요금 적발 → 수당0"
            elif o.get("extra_fee_status") == "rejected":
                total_revenue = DISPATCH_FEE
                driver_pay = DISPATCH_FEE * DRIVER_RATIO
                note = "거절→출동비"
            else:
                total_revenue = effective_base + extra
                driver_pay = total_revenue * DRIVER_RATIO
                note = "정상" if o.get("payment_confirmed") else "입금대기"

            penalty = o.get("penalty_amount", 0)
            job_allowance = 0 if o.get("arbitrary_fee_flag") else o.get("job_allowance", 0)
            net_allowance = max(0, job_allowance - penalty)

            # ── 정산가 초과 알림 (최초 1회만)
            if not o.get("settlement_overrun_notified") and effective_base > 0:
                overrun_check = total_revenue / effective_base
                if overrun_check > 1.10:
                    try:
                        from utils.notifications import notify_settlement_overrun
                        from data.db import update_order
                        _manager_name = "—"
                        notify_settlement_overrun(
                            order=o,
                            estimate=effective_base,
                            actual=int(total_revenue),
                            manager_name=_manager_name,
                        )
                        update_order(o["id"], {"settlement_overrun_notified": True})
                    except Exception:
                        pass

            # ── 정산 보류(Hold) 처리
            if o.get("settlement_hold") and not o.get("settlement_hold_released"):
                note = f"🔒 정산 HOLD — {o.get('settlement_hold_reason','AI 사진 불일치')}"
                driver_pay = 0  # Hold 건은 지급 0원으로 표시
                total_revenue_display = total_revenue
            else:
                total_revenue_display = total_revenue

            hold_mark = "🔒" if (o.get("settlement_hold") and not o.get("settlement_hold_released")) else ""
            # ── 세무 유형별 계산
            _tax = calc_driver_settlement(driver_pay, drv) if drv else calc_driver_settlement(driver_pay, {})
            _tax_label = _tax["label"]
            if hold_mark:
                _net_display = "🔒 보류"
                _tax_detail = "🔒 보류"
            elif _tax["tax_type"] == TAX_TYPE_BUSINESS:
                _net_display = f"₩{int(_tax['net_pay']):,}"
                _tax_detail = f"공급가 ₩{int(_tax['supply_amount']):,} / VAT ₩{int(_tax['vat']):,}"
            else:
                _net_display = f"₩{int(_tax['net_pay']):,}"
                _tax_detail = f"원천세 -₩{int(_tax['withholding']):,}"
            rows.append({
                "주문": f"{hold_mark}#{o['id']}",
                "고객": o["customer"],
                "기사": drv["name"] if drv else "미배정",
                "세무유형": _tax_label,
                "작업": o.get("work_type", "수거"),
                "기준가": f"₩{effective_base:,} ({base_label})",
                "추가요금": f"₩{extra:,}" if extra else "—",
                "총매출": f"₩{total_revenue_display:,}",
                "기사지급(70%)": f"₩{driver_pay:,.0f}" if not hold_mark else "🔒 보류",
                "세무공제내역": _tax_detail,
                "실지급": _net_display,
                "건당수당": f"₩{net_allowance:,.0f}",
                "패널티": f"-₩{penalty:,}" if penalty else "—",
                "입금": "✅" if o.get("payment_confirmed") else "❌",
                "비고": note,
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        confirmed = [o for o in completed_orders if o.get("payment_confirmed")]
        def _effective_base(o):
            if o.get("work_type") == "철거" and o.get("manager_quote_confirmed") and o.get("manager_quote"):
                return o["manager_quote"]
            return o["base_fee"]
        total_rev = sum(
            (_effective_base(o) + (o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0))
            for o in confirmed
        )

        # ── 정산 보류(Hold) 건 별도 섹션
        hold_orders = [
            o for o in completed_orders
            if o.get("settlement_hold") and not o.get("settlement_hold_released")
        ]
        if hold_orders:
            st.divider()
            st.error(f"🔒 **정산 보류(Hold) {len(hold_orders)}건** — AI 사진 불일치 자동 처리됨. 매니저/대표 승인 후 해제 가능합니다.")
            for h_o in hold_orders:
                h_drv = get_driver_by_id(h_o.get("driver_id"))
                hc1, hc2, hc3 = st.columns([3, 3, 1])
                with hc1:
                    st.markdown(
                        f"**🔒 주문 #{h_o['id']}** — {h_o['customer']} | "
                        f"기사: {h_drv['name'] if h_drv else '미배정'}"
                    )
                    st.caption(f"Hold 사유: {h_o.get('settlement_hold_reason','—')}")
                    st.caption(f"Hold 시각: {h_o.get('settlement_hold_at','—')}")
                with hc2:
                    ai_score = h_o.get("photo_match_score")
                    st.caption(f"AI Match Score: {ai_score}점" if ai_score else "AI 점수 없음")
                with hc3:
                    if is_owner() or is_manager():
                        if st.button("✅ Hold 해제", key=f"hold_release_{h_o['id']}"):
                            role = st.session_state.get("_soonssak_role", "unknown")
                            update_order(h_o["id"], {
                                "settlement_hold_released": True,
                                "settlement_hold_released_by": role,
                            })
                            st.success("정산 보류 해제 완료!")
                            st.rerun()

        st.divider()
        st.subheader("📊 정산 요약 (입금 확인 건)")
        # Hold 건 제외하고 집계
        confirmed_non_hold = [
            o for o in confirmed
            if not (o.get("settlement_hold") and not o.get("settlement_hold_released"))
        ]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("총 확정 매출", f"₩{total_rev:,.0f}")
        with col2:
            st.metric(f"기사 총 지급 ({DRIVER_RATIO*100:.0f}%)", f"₩{total_rev * DRIVER_RATIO:,.0f}")
        with col3:
            st.metric(f"CS 수익 ({CS_RATIO*100:.0f}%)", f"₩{total_rev * CS_RATIO:,.0f}")
        with col4:
            st.metric(f"성공보수 ({SUCCESS_FEE_RATIO*100:.0f}%)", f"₩{total_rev * SUCCESS_FEE_RATIO:,.0f}")

# ──────────────── Tab 2: 건당 수당 입력 ────────────────
with tab2:
    st.subheader("🔧 건당 수당 확정 입력")
    st.info(
        "**수거:** ₩20,000 ~ ₩40,000 범위 | **철거:** ₩50,000 ~ ₩200,000 범위 (1인 기준)\n\n"
        "2인 1조 철거 건은 기사별 수당을 각각 확정합니다. "
        "지연 발생 시 패널티 차감, 임의추가요금 적발 건은 수당 자동 0원 처리됩니다."
    )

    orders = get_orders()
    completed_or_progress = [o for o in orders if o["status"] in ("completed", "in_progress", "dispatched")]

    if not completed_or_progress:
        st.info("수당 입력할 주문이 없습니다.")
    else:
        for o in completed_or_progress:
            drv = get_driver_by_id(o.get("driver_id"))
            drv2 = get_driver_by_id(o.get("second_driver_id"))
            wtype = o.get("work_type", "수거")
            is_demolition = wtype == "철거"
            is_flagged = o.get("arbitrary_fee_flag", False)
            current_allowance = o.get("job_allowance", 0)
            current_penalty = o.get("penalty_amount", 0)
            team_size = o.get("team_size", 1)
            confirmed_price = o.get("manager_quote") if o.get("manager_quote_confirmed") else o["base_fee"]

            mn = 50000 if is_demolition else 20000
            mx = 200000 if is_demolition else 40000

            # 2인1조 철거 건 특별 처리
            if is_demolition and team_size >= 2 and drv2:
                st.markdown(
                    f"**주문 #{o['id']}** — {o['customer']} | 🔨 철거 "
                    f"{'₩'+str(confirmed_price//10000)+'만' if confirmed_price else ''} | "
                    f"👥 {team_size}인 1조"
                )
                if o.get("manager_quote_confirmed"):
                    st.caption(f"✅ 매니저 확정 견적: ₩{confirmed_price:,}")
                else:
                    st.caption(f"⚠️ 매니저 견적 미확정 — CS 기초 견적 기준: ₩{confirmed_price:,}")

                col_a, col_b, col_c = st.columns([1, 1, 1])
                with col_a:
                    st.markdown(f"**1조 기사 (주):** {drv['name'] if drv else '미배정'}")
                    if is_flagged:
                        st.error("🚨 수당 0원 (임의추가요금 적발)")
                        allow_1 = 0
                    else:
                        allow_1 = st.number_input(
                            f"수당 ₩{mn//1000}k~₩{mx//1000}k",
                            min_value=mn, max_value=mx,
                            value=max(mn, min(mx, current_allowance)) if current_allowance > 0 else mn,
                            step=5000, key=f"allowance_{o['id']}_1"
                        )
                with col_b:
                    st.markdown(f"**2조 기사 (보조):** {drv2['name']}")
                    if is_flagged:
                        st.error("🚨 수당 0원")
                        allow_2 = 0
                    else:
                        allow_2 = st.number_input(
                            f"보조 수당 ₩{mn//1000}k~₩{mx//1000}k",
                            min_value=mn, max_value=mx,
                            value=max(mn, min(mx, current_allowance)) if current_allowance > 0 else mn,
                            step=5000, key=f"allowance_{o['id']}_2"
                        )
                with col_c:
                    total_allow = allow_1 + allow_2
                    penalty = current_penalty
                    st.metric("총 수당 합계", f"₩{total_allow:,}")
                    st.caption(f"주기사 ₩{allow_1:,} + 보조 ₩{allow_2:,}")
                    if st.button("💾 저장", key=f"save_all_{o['id']}"):
                        update_order(o["id"], {
                            "job_allowance": int(allow_1),
                            "driver_allowance_amount": int(allow_2),
                            "penalty_amount": int(penalty),
                        })
                        st.success(f"저장됨 — 주기사 ₩{allow_1:,} / 보조기사 ₩{allow_2:,}")
                        st.rerun()
                st.divider()

            else:
                # 1인 수거 / 철거 건
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    st.markdown(f"**주문 #{o['id']}** — {o['customer']}")
                    work_badge = "🔨 철거" if is_demolition else "📦 수거"
                    st.caption(f"기사: {drv['name'] if drv else '미배정'} | {work_badge}")
                    if is_demolition and o.get("manager_quote_confirmed"):
                        st.caption(f"✅ 매니저 확정 견적: ₩{confirmed_price:,}")
                with col2:
                    if is_flagged:
                        st.error("🚨 수당 0원\n(임의추가요금 적발)")
                        new_allowance = 0
                    else:
                        new_allowance = st.number_input(
                            f"수당 (₩{mn//1000}k~₩{mx//1000}k)",
                            min_value=mn, max_value=mx,
                            value=max(mn, min(mx, current_allowance)) if current_allowance > 0 else mn,
                            step=5000,
                            key=f"allowance_{o['id']}"
                        )
                with col3:
                    if o.get("delay_flag") and not is_flagged:
                        penalty = st.number_input(
                            "패널티 차감",
                            min_value=0,
                            value=int(current_penalty),
                            step=5000,
                            key=f"pen2_{o['id']}"
                        )
                        st.caption("⏰ 지연 발생 건")
                    else:
                        penalty = current_penalty
                        st.caption(f"패널티: ₩{penalty:,}")
                with col4:
                    if not is_flagged:
                        net = max(0, new_allowance - penalty)
                        st.metric("실지급 수당", f"₩{net:,}")
                        if st.button("💾 저장", key=f"save_all_{o['id']}"):
                            update_order(o["id"], {
                                "job_allowance": int(new_allowance),
                                "penalty_amount": int(penalty)
                            })
                            st.success("저장됨")
                            st.rerun()

# ──────────────── Tab 3: 기사별 정산 요약 ────────────────
with tab3:
   st.subheader("실행팀별 정산 요약 (직영팀 조건부 운영비 시각화 포함)")

    orders = get_orders()
    drivers = get_drivers()
    ace_bonuses = get_ace_bonuses()

    # 조건부 운영비 시각화
    st.subheader("📊 조건부 운영비 현황")
    op_cols = st.columns(min(len(drivers), 5))
    for idx, d in enumerate(drivers[:5]):
        if d.get("driver_type") != "직영":
            continue
        monthly = d.get("monthly_jobs", 0)
        at_risk = monthly < DIRECT_THRESHOLD
        pct = min(100, int(monthly / DIRECT_THRESHOLD * 100))
        with op_cols[idx % len(op_cols)]:
            if at_risk:
                st.error(f"**{d['name']}**")
                st.progress(pct / 100)
                st.caption(f"{monthly}/{DIRECT_THRESHOLD}건 ({pct}%) → ₩{HALF_COST:,} (50%)")
            else:
                st.success(f"**{d['name']}**")
                st.progress(1.0)
                st.caption(f"{monthly}건 달성 → ₩{FULL_COST:,} (전액)")

    st.divider()

    driver_summary = {}
    for o in orders:
        if o["status"] != "completed" or not o.get("payment_confirmed"):
            continue
        drv = get_driver_by_id(o.get("driver_id"))
        if not drv:
            continue
        did = drv["id"]
        extra = o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0
        if o.get("arbitrary_fee_flag"):
            total = o["base_fee"]
            pay = 0
            allowance = 0
        elif o.get("extra_fee_status") == "rejected":
            total = DISPATCH_FEE
            pay = DISPATCH_FEE * DRIVER_RATIO
            allowance = max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0))
        else:
            total = o["base_fee"] + extra
            pay = total * DRIVER_RATIO
            allowance = max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0))

        if did not in driver_summary:
            driver_summary[did] = {
                "name": drv["name"],
                "driver_type": drv.get("driver_type", "직영"),
                "tax_type": drv.get("tax_type", "individual"),
                "business_reg_no": drv.get("business_reg_no", ""),
                "driver_obj": drv,
                "jobs": 0, "monthly_jobs": drv.get("monthly_jobs", 0),
                "total_rev": 0, "total_pay": 0, "total_allowance": 0
            }
        driver_summary[did]["jobs"] += 1
        driver_summary[did]["total_rev"] += total
        driver_summary[did]["total_pay"] += pay
        driver_summary[did]["total_allowance"] += allowance

    if not driver_summary:
        st.info("입금 확인된 완료 주문이 없습니다.")
    else:
        rows = []
        for did, s in driver_summary.items():
            is_direct = s["driver_type"] == "직영"
            monthly = s["monthly_jobs"]
            at_risk = is_direct and monthly < DIRECT_THRESHOLD
            op_cost = FULL_COST if monthly >= DIRECT_THRESHOLD else HALF_COST if is_direct else 0
            op_label = f"₩{op_cost:,}" + (" ✅전액" if monthly >= DIRECT_THRESHOLD else " ⚠️50%") if is_direct else "—"

            ace = sum(b["amount"] for b in ace_bonuses if b.get("driver_id") == did)
            _drv_obj = s.get("driver_obj", {})
            _tax = calc_driver_settlement(s["total_pay"], _drv_obj)
            _is_biz = _tax["tax_type"] == TAX_TYPE_BUSINESS

            if _is_biz:
                withholding_label = "—"
                vat_label = f"₩{int(_tax['vat']):,}"
                supply_label = f"₩{int(_tax['supply_amount']):,}"
                net_pay = _tax["net_pay"] + s["total_allowance"] + ace
            else:
                withholding_label = f"-₩{int(_tax['withholding']):,}"
                vat_label = "—"
                supply_label = "—"
                net_pay = _tax["net_pay"] + s["total_allowance"] + ace

            rows.append({
                "기사명": s["name"],
                "유형": s["driver_type"],
                "세무유형": _tax["label"],
                "이달완료": f"{monthly}건 {'⚠️' if at_risk else '✅'}",
                "확인완료": f"{s['jobs']}건",
                "총 매출기여": f"₩{s['total_rev']:,.0f}",
                "지급액(70%)": f"₩{s['total_pay']:,.0f}",
                "공급가액": supply_label,
                "부가세(사업자)": vat_label,
                "원천징수(개인3.3%)": withholding_label,
                "건당수당합계": f"₩{s['total_allowance']:,.0f}",
                "조건부운영비": op_label,
                "Ace Bonus": f"₩{ace:,}" if ace else "—",
                "실지급예상": f"₩{net_pay:,.0f}",
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        at_risk_list = [s for s in driver_summary.values() if s["monthly_jobs"] < DIRECT_THRESHOLD and s["driver_type"] == "직영"]
        if at_risk_list:
            st.warning(
                f"⚠️ 월 {DIRECT_THRESHOLD}건 미달 기사 {len(at_risk_list)}명 → "
                f"조건부 운영비 50%(₩{HALF_COST:,}) 적용 | 차감액: ₩{(FULL_COST - HALF_COST) * len(at_risk_list):,}"
            )

        # ── 월간 정산 명세서 PDF 다운로드 ────────────────
        st.divider()
        st.subheader("📄 월간 정산 명세서 자동 생성")
        now_dt = __import__("datetime").datetime.now()
        month_label = now_dt.strftime("%Y년 %m월")
        pdf_target = st.selectbox(
            "명세서 생성 대상",
            ["전체 기사"] + [s["name"] for s in driver_summary.values()],
            key="pdf_target_sel"
        )

        if st.button("📥 HTML 명세서 생성 (인쇄→PDF)", type="primary", key="gen_pdf_btn"):
            # HTML 명세서 생성 (브라우저에서 인쇄 시 PDF 저장 가능)
            vat_rate = settings.get("vat_rate", 0.10)
            target_rows = rows if pdf_target == "전체 기사" else [r for r in rows if r["기사명"] == pdf_target]

            html_rows = ""
            for r in target_rows:
                ace_val = r["Ace Bonus"] if r["Ace Bonus"] != "—" else "₩0"
                tax_detail = (
                    f"공급가 {r['공급가액']} / VAT {r['부가세(사업자)']}"
                    if r["세무유형"] == "사업자(부가세 포함)"
                    else r["원천징수(개인3.3%)"]
                )
                html_rows += f"""
                <tr>
                  <td>{r['기사명']}</td><td>{r['유형']}</td>
                  <td style='color:#555'>{r['세무유형']}</td>
                  <td>{r['이달완료']}</td>
                  <td>{r['총 매출기여']}</td><td>{r['지급액(70%)']}</td>
                  <td style='color:#1565c0'>{r['건당수당합계']}</td>
                  <td>{r['조건부운영비']}</td><td>{ace_val}</td>
                  <td style='color:#c62828'>{tax_detail}</td>
                  <td style='font-weight:bold'>{r['실지급예상']}</td>
                </tr>"""

            total_net = sum(
                float(r["실지급예상"].replace("₩","").replace(",",""))
                for r in target_rows
            )
            html_content = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>순삭OS 월간 정산 명세서 — {month_label}</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; margin: 30px; color: #222; }}
  h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 10px; }}
  h2 {{ color: #283593; margin-top: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 13px; }}
  th {{ background: #1a237e; color: white; padding: 8px; text-align: center; }}
  td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: right; }}
  td:first-child, td:nth-child(2), td:nth-child(3) {{ text-align: center; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  .footer {{ margin-top: 30px; font-size: 11px; color: #888; border-top: 1px solid #ccc; padding-top: 10px; }}
  .total {{ font-weight: bold; font-size: 16px; color: #1a237e; margin-top: 10px; }}
  .tax-note {{ background: #fff8e1; padding: 10px; border-left: 4px solid #f9a825; margin: 15px 0; font-size: 13px; }}
  @media print {{ .no-print {{ display: none; }} body {{ margin: 10px; }} }}
</style></head><body>
<h1>📋 순삭 OS — {month_label} 정산 명세서</h1>
<p>생성일시: {now_dt.strftime('%Y-%m-%d %H:%M:%S')} | 대상: {pdf_target}</p>

<div class="tax-note">
  <b>세무 정보</b> | 개인 기사: 원천세 <b>3.3%</b> 자동 공제 (소득세 3% + 지방소득세 0.3%) |
  사업자 기사: Base ÷ 1.1 → 공급가액 + 부가세 분리, 총 지급 = Base 고정 (추가 부가세 없음) |
  적용 기준: 소득세법 제127조 · 부가가치세법 제32조
</div>

<h2>기사별 정산 요약</h2>
<table>
  <tr>
    <th>기사명</th><th>유형</th><th>세무유형</th><th>이달완료</th><th>총 매출기여</th>
    <th>지급액(70%)</th><th>건당수당</th><th>조건부운영비</th>
    <th>Ace Bonus</th><th>세무공제</th><th>실지급예상</th>
  </tr>
  {html_rows}
</table>

<p class="total">💰 총 실지급 예상 합계: ₩{total_net:,.0f}</p>

<div class="footer">
  본 명세서는 순삭 OS에서 자동 생성되었습니다. | 
  계약서 조건 및 세무사 확인 후 최종 지급 확정 | 
  원천징수세는 다음 달 10일까지 신고·납부 의무 있음
</div>
</body></html>"""

            st.download_button(
                label="⬇️ HTML 명세서 다운로드 (브라우저에서 인쇄→PDF 저장)",
                data=html_content.encode("utf-8"),
                file_name=f"순삭OS_{month_label}_정산명세서_{pdf_target}.html",
                mime="text/html",
                key="download_pdf_btn"
            )
            st.info("📌 다운로드 후 브라우저에서 열고 **Ctrl+P** → '대상: PDF로 저장' 선택으로 PDF 저장하세요.")

# ──────────────── Tab 4: Ace Bonus ────────────────
with tab4:
    st.subheader("🏆 Ace Bonus — 관리자 수동 지급")
    st.info("관리자가 특정 기사에게 포상 보너스를 수동으로 지급합니다. 정산서에 합산됩니다.")

    drivers = get_drivers()
    ace_bonuses = get_ace_bonuses()

    with st.form("ace_bonus_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            driver_name = st.selectbox("기사 선택", [d["name"] for d in drivers])
        with col2:
            bonus_amount = st.number_input("Ace Bonus 금액 (원)", min_value=10000, step=10000, value=50000)
        with col3:
            bonus_reason = st.text_input("지급 사유", placeholder="예: 이달 최다 완료, 고객만족도 1위")
        submitted = st.form_submit_button("🏆 Ace Bonus 지급", type="primary")
        if submitted:
            drv = next((d for d in drivers if d["name"] == driver_name), None)
            if drv:
                add_ace_bonus({
                    "driver_id": drv["id"],
                    "driver_name": drv["name"],
                    "amount": int(bonus_amount),
                    "reason": bonus_reason
                })
                st.success(f"🏆 {driver_name}에게 Ace Bonus ₩{bonus_amount:,} 지급 완료!")
                st.rerun()

    st.divider()
    st.subheader("Ace Bonus 지급 이력")
    if not ace_bonuses:
        st.info("지급된 Ace Bonus가 없습니다.")
    else:
        bonus_rows = []
        for b in reversed(ace_bonuses):
            bonus_rows.append({
                "지급일시": b.get("created_at", "—"),
                "기사명": b.get("driver_name", "—"),
                "지급액": f"₩{b['amount']:,}",
                "사유": b.get("reason", "—"),
            })
        st.dataframe(pd.DataFrame(bonus_rows), use_container_width=True, hide_index=True)
        total_ace = sum(b["amount"] for b in ace_bonuses)
        st.metric("누적 Ace Bonus 지급액", f"₩{total_ace:,}")

# ──────────────── Tab 5: 입금 확인 ────────────────
with tab5:
    st.subheader("입금 확인 처리")
    st.caption("입금 확인 시 정산 엔진이 활성화됩니다")

    orders = get_orders()
    unconfirmed = [o for o in orders if o["status"] == "completed" and not o.get("payment_confirmed")]

    if not unconfirmed:
        st.success("✅ 입금 미확인 건이 없습니다.")
    else:
        for o in unconfirmed:
            drv = get_driver_by_id(o.get("driver_id"))
            extra = o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0
            total = o["base_fee"] + extra if o.get("extra_fee_status") != "rejected" else DISPATCH_FEE
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**주문 #{o['id']}** — {o['customer']} | 기사: {drv['name'] if drv else '미배정'}")
                st.caption(f"{'🔨 철거' if o.get('work_type') == '철거' else '📦 수거'} | 총 청구액: ₩{total:,}")
            with col2:
                extra_status = {"approved": "✅ 추가승인", "rejected": "❌ 추가거절", "pending": "⏳ 대기"}.get(
                    o.get("extra_fee_status") or "", "—")
                st.markdown(f"기본 ₩{o['base_fee']:,} + 추가 ₩{o.get('extra_fee', 0):,} ({extra_status})")
            with col3:
                if st.button("💳 입금 확인", key=f"pay_{o['id']}", type="primary"):
                    update_order(o["id"], {"payment_confirmed": True})
                    st.success(f"✅ 주문 #{o['id']} 입금 확인!")
                    st.rerun()

# ──────────────── Tab 6: 매니저 인센티브 ────────────────
with tab6:
    st.subheader("👔 매니저 인센티브 정산")
    st.caption("기본 운영비 ₩1,500,000 + 매니저가 직접 성사시킨 철거 건당 인센티브")
    st.info(
        f"**정산 기준:**\n"
        f"- 기본 운영비: ₩{MANAGER_BASE:,} (고정)\n"
        f"- 철거 건 인센티브: 매니저 직접 성사(👔 표시) 건만 해당 | "
        f"₩{DEMO_INCENTIVE_MIN:,} ~ ₩{DEMO_INCENTIVE_MAX:,}/건\n"
        f"- ❌ 가격 변경 권한 없음 — CS 확정가 기준으로만 정산\n"
        f"- ❌ 수거 건 인센티브 없음 — 철거 직접 성사 건만 해당"
    )

    orders = get_orders()
    drivers = get_drivers()

    # 매니저 직접 성사 철거 건 집계
    manager_closed_demolitions = [
        o for o in orders
        if o.get("manager_closed") and o.get("work_type") == "철거" and o.get("payment_confirmed")
    ]
    manager_closed_others = [
        o for o in orders
        if o.get("manager_closed") and o.get("work_type") != "철거"
    ]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("👔 기본 운영비", f"₩{MANAGER_BASE:,}", delta="고정 지급")
    with col2:
        incentive_total = len(manager_closed_demolitions) * DEMO_INCENTIVE_MIN
        incentive_max = len(manager_closed_demolitions) * DEMO_INCENTIVE_MAX
        st.metric(
            "🔨 철거 인센티브 (최소)",
            f"₩{incentive_total:,}",
            delta=f"최대 ₩{incentive_max:,}"
        )
    with col3:
        total_mgr = MANAGER_BASE + incentive_total
        st.metric("💰 매니저 총 정산 (최소 기준)", f"₩{total_mgr:,}")

    st.divider()

    # 인센티브 대상 건별 테이블
    st.subheader("🔨 철거 인센티브 대상 건 (매니저 직접 성사)")
    if not manager_closed_demolitions:
        st.info("매니저 직접 성사 철거 건이 없습니다. 배차 스케줄링 > 매니저 모니터링에서 등록하세요.")
    else:
        rows = []
        for o in manager_closed_demolitions:
            drv = get_driver_by_id(o.get("driver_id"))
            rows.append({
                "주문": f"#{o['id']}",
                "고객": o["customer"],
                "기사": drv["name"] if drv else "—",
                "예약일": o["scheduled_time"][:10],
                "기본요금(CS확정)": f"₩{o['base_fee']:,}",
                "인센티브(최소)": f"₩{DEMO_INCENTIVE_MIN:,}",
                "인센티브(최대)": f"₩{DEMO_INCENTIVE_MAX:,}",
                "입금확인": "✅" if o.get("payment_confirmed") else "❌",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # 건별 인센티브 확정 입력
        st.subheader("📝 건별 인센티브 확정 입력")
        for o in manager_closed_demolitions:
            current = o.get("manager_incentive", DEMO_INCENTIVE_MIN)
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.markdown(f"**주문 #{o['id']}** — {o['customer']} | ₩{o['base_fee']:,}")
            with col2:
                new_incentive = st.number_input(
                    f"인센티브 (₩{DEMO_INCENTIVE_MIN//1000:,}k~₩{DEMO_INCENTIVE_MAX//1000:,}k)",
                    min_value=DEMO_INCENTIVE_MIN,
                    max_value=DEMO_INCENTIVE_MAX,
                    value=int(current) if current else DEMO_INCENTIVE_MIN,
                    step=5000,
                    key=f"mgr_inc_{o['id']}"
                )
            with col3:
                if st.button("💾 저장", key=f"mgr_inc_save_{o['id']}"):
                    update_order(o["id"], {"manager_incentive": int(new_incentive)})
                    st.success("저장됨")
                    st.rerun()

    st.divider()

    # 비해당 건 (수거, 직접성사 아닌 건) 안내
    if manager_closed_others:
        st.subheader("ℹ️ 인센티브 미해당 매니저 개입 건 (수거)")
        rows2 = []
        for o in manager_closed_others:
            rows2.append({
                "주문": f"#{o['id']}",
                "고객": o["customer"],
                "작업": o.get("work_type", "수거"),
                "요금": f"₩{o['base_fee']:,}",
                "비고": "수거건 — 인센티브 해당 없음",
            })
        st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📊 매니저 정산 최종 요약")
    confirmed_incentives = sum(
        o.get("manager_incentive", DEMO_INCENTIVE_MIN) for o in manager_closed_demolitions
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("기본 운영비", f"₩{MANAGER_BASE:,}")
    with c2:
        st.metric("철거 인센티브 합계", f"₩{confirmed_incentives:,}",
                  delta=f"{len(manager_closed_demolitions)}건 × 건당 인센티브")
    with c3:
        st.metric("최종 매니저 정산액", f"₩{MANAGER_BASE + confirmed_incentives:,}")

# ──────────────── Tab 7: 본사 순익 시뮬레이터 ────────────────
with tab7:
    st.subheader("🧮 본사 실질 순익 시뮬레이터")
    st.caption("[고객 견적액 − 직영/외주 수당 − 매니저 인센티브 − 광고비] = 본사 실질 순익")

    orders = get_orders()
    confirmed = [o for o in orders if o["status"] == "completed" and o.get("payment_confirmed")]
    sc_jobs = get_subcontractor_jobs()
    ace_bonuses = get_ace_bonuses()
    drivers = get_drivers()

    total_revenue = sum(
        (o["base_fee"] + (o["extra_fee"] if o.get("extra_fee_status") == "approved" else 0))
        for o in confirmed
    )
    total_driver_pay = sum(
        (o["base_fee"] + (o["extra_fee"] if o.get("extra_fee_status") == "approved" else 0)) * DRIVER_RATIO
        for o in confirmed if not o.get("arbitrary_fee_flag")
    )
    total_allowance = sum(
        max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0))
        for o in confirmed if not o.get("arbitrary_fee_flag")
    )
    total_sc_cost = sum(j.get("total_amount", 0) for j in sc_jobs if j.get("status") != "claim_reported")
    total_ace = sum(b["amount"] for b in ace_bonuses)

    # 매니저 인센티브 (기본 운영비)
    manager_base = settings.get("manager_base_cost", 1500000)

    # 직영팀 운영비
    direct_op_cost = sum(
        FULL_COST if d.get("monthly_jobs", 0) >= DIRECT_THRESHOLD else HALF_COST
        for d in drivers if d.get("driver_type") == "직영"
    )

    ad_cost = total_revenue * AD_COST_RATE
    total_cost = total_driver_pay + total_allowance + total_sc_cost + total_ace + manager_base + direct_op_cost + ad_cost
    net_profit = total_revenue - total_cost

    st.divider()
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("💰 수익 구성 상세")
        items = [
            ("고객 총 견적액 (확정 매출)", total_revenue, "green"),
            ("— 기사 지급 (70%)", -total_driver_pay, "red"),
            ("— 건당 수당 합계", -total_allowance, "red"),
            ("— 외주 파트너 비용", -total_sc_cost, "red"),
            ("— Ace Bonus", -total_ace, "red"),
            ("— 매니저 기본 운영비", -manager_base, "red"),
            ("— 직영팀 조건부 운영비", -direct_op_cost, "red"),
            (f"— 광고비 ({AD_COST_RATE*100:.0f}%)", -ad_cost, "red"),
        ]
        for label, amount, color in items:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"{'✅' if color == 'green' else '🔻'} {label}")
            with c2:
                formatted = f"₩{abs(amount):,.0f}"
                if color == "red":
                    st.markdown(f"**-{formatted}**")
                else:
                    st.markdown(f"**+{formatted}**")
        st.divider()
        profit_color = "normal" if net_profit >= 0 else "inverse"
        st.metric(
            "🏦 본사 실질 순익",
            f"₩{net_profit:,.0f}",
            delta=f"{net_profit/max(total_revenue,1)*100:.1f}% 마진" if total_revenue > 0 else "—",
            delta_color=profit_color
        )

    with col2:
        st.subheader("⚙️ 가정치 수정")
        sim_revenue = st.number_input("예상 매출 (시뮬레이션)", value=int(total_revenue), step=100000)
        sim_driver_pct = st.slider("기사 지급 비율", 50, 80, int(DRIVER_RATIO * 100)) / 100
        sim_ad_rate = st.slider("광고비 비율 (%)", 0, 30, int(AD_COST_RATE * 100)) / 100
        sim_sc = st.number_input("외주 비용", value=int(total_sc_cost), step=50000)
        sim_manager = st.number_input("매니저 운영비", value=int(manager_base), step=100000)

        sim_driver = sim_revenue * sim_driver_pct
        sim_ad = sim_revenue * sim_ad_rate
        sim_net = sim_revenue - sim_driver - total_allowance - sim_sc - total_ace - sim_manager - direct_op_cost - sim_ad

        st.divider()
        st.metric("📊 시뮬레이션 순익", f"₩{sim_net:,.0f}",
                  delta=f"{sim_net/max(sim_revenue,1)*100:.1f}% 마진" if sim_revenue > 0 else "—",
                  delta_color="normal" if sim_net >= 0 else "inverse")

show_legal_warning()
