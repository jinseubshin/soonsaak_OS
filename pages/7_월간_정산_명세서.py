import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (get_orders, get_drivers, get_settings, get_driver_by_id,
                     get_ace_bonuses, get_manager_settlements, add_manager_settlement)
from utils.rbac import render_role_selector, require_role, role_badge, is_executor, is_cs
from utils.footer import show_legal_warning
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="월간 정산 명세서 — 순삭 OS", page_icon="📋", layout="wide")
render_role_selector()

# ── 실행팀 / CS 접근 차단
if is_executor() or is_cs():
    st.error("🚫 **이 페이지는 Owner · 매니저 전용입니다.**")
    st.stop()

require_role("owner", "manager_sejong", "manager_bonsa")

st.title("📋 월간 정산 명세서")
st.caption(f"매니저 정산 + 실행팀 정산 + Ace Bonus + 세무 합산 종합 명세서 {role_badge()}")

settings = get_settings()
DRIVER_RATIO = settings["driver_ratio"]
CS_RATIO = settings["cs_ratio"]
SUCCESS_FEE_RATIO = settings["success_fee_ratio"]
DISPATCH_FEE = settings["dispatch_fee"]
WITHHOLDING = settings["withholding_tax_rate"]
DIRECT_THRESHOLD = settings.get("direct_team_threshold", 40)
FULL_COST = settings.get("direct_team_full_cost", 1500000)
HALF_COST = settings.get("direct_team_half_cost", 750000)
MANAGER_BASE = settings.get("manager_base_cost", 1500000)
ACTIVE_THRESHOLD = settings.get("active_driver_threshold", 60)
DEMO_MIN = settings.get("demolition_incentive_min", 50000)
DEMO_MAX = settings.get("demolition_incentive_max", 100000)

now = datetime.now()
orders = get_orders()
drivers = get_drivers()
ace_bonuses = get_ace_bonuses()

# ─── 월 선택
col_period, _ = st.columns([1, 3])
with col_period:
    year = st.number_input("년도", min_value=2024, max_value=2030, value=now.year)
    month = st.selectbox("월", list(range(1, 13)), index=now.month - 1)

month_label = f"{year}년 {month}월"
st.markdown(f"## 📅 {month_label} 정산 명세서")
st.divider()

# ─── 완료된 주문 필터 (당월)
def is_this_month(o):
    try:
        d = datetime.strptime(o.get("scheduled_time", ""), "%Y-%m-%d %H:%M")
        return d.year == year and d.month == month
    except Exception:
        return True

month_orders = [o for o in orders if is_this_month(o) and o["status"] == "completed"]

# ──────────────────────────────────────────
# SECTION 1: 매니저(이사급) 정산
# ──────────────────────────────────────────
st.header("👔 1. 매니저(이사급) 정산")

with st.container():
    mcol1, mcol2, mcol3 = st.columns(3)

    with mcol1:
        st.subheader("기본 운영비")
        st.metric("월 기본 운영비", f"₩{MANAGER_BASE:,}")
        st.caption("계약 고정 지급")

    with mcol2:
        st.subheader("철거 인센티브")
        demolition_orders = [o for o in month_orders if o.get("work_type") == "철거"]
        demo_count = len(demolition_orders)
        st.caption(f"이달 철거 건수: **{demo_count}건**")
        st.caption(f"단가 범위: ₩{DEMO_MIN//1000:,}k ~ ₩{DEMO_MAX//1000:,}k / 건")

        demo_unit = st.number_input(
            "철거 인센티브 단가 (원/건)",
            min_value=DEMO_MIN,
            max_value=DEMO_MAX,
            value=DEMO_MIN,
            step=5000,
            key="demo_unit"
        )
        demo_incentive = demo_count * demo_unit
        st.metric("철거 인센티브 합계", f"₩{demo_incentive:,}")

    with mcol3:
        st.subheader("실행팀 유지 보충 보너스")
        active_drivers = [d for d in drivers if d.get("monthly_jobs", 0) >= ACTIVE_THRESHOLD]
        active_count = len(active_drivers)
        st.caption(f"월 {ACTIVE_THRESHOLD}건 이상 활성 실행팀: **{active_count}명**")

        if active_count >= 3:
            retention_bonus = 200000
            bonus_label = "3명 이상 → ₩200,000"
        elif active_count == 2:
            retention_bonus = 100000
            bonus_label = "2명 → ₩100,000"
        else:
            retention_bonus = 0
            bonus_label = f"1명 이하 ({active_count}명) → 미발생"

        st.metric("실행팀 유지 보너스", f"₩{retention_bonus:,}")
        st.caption(bonus_label)
        if active_drivers:
            st.caption(f"활성 실행팀: {', '.join(d['name'] for d in active_drivers)}")

    st.divider()
    manager_total = MANAGER_BASE + demo_incentive + retention_bonus
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("기본 운영비", f"₩{MANAGER_BASE:,}")
    with m2:
        st.metric("철거 인센티브", f"₩{demo_incentive:,}")
    with m3:
        st.metric("유지 보충 보너스", f"₩{retention_bonus:,}")
    with m4:
        st.metric("**매니저 총 지급액**", f"₩{manager_total:,}", delta="이번달")

st.divider()

# ──────────────────────────────────────────
# SECTION 2: 실행팀 정산 (블루/옐로우/레드/그린)
# ──────────────────────────────────────────
st.header("🚗 2. 실행팀 정산")

# 실행팀 4개 팀 정의 (팀 코드 → 표시 이름)
EXEC_TEAMS = {
    "블루":   "🔵 블루팀",
    "옐로우": "🟡 옐로우팀",
    "레드":   "🔴 레드팀",
    "그린":   "🟢 그린팀",
}

direct_drivers = [d for d in drivers if d.get("driver_type") == "직영"]

driver_settle = {}
for o in month_orders:
    drv = get_driver_by_id(o.get("driver_id"))
    if not drv or drv.get("driver_type") != "직영":
        continue
    did = drv["id"]
    if did not in driver_settle:
        driver_settle[did] = {
            "driver": drv,
            "jobs": 0,
            "allowance_total": 0,
            "penalty_total": 0,
            "flagged_jobs": 0,
            "delayed_jobs": 0,
            "demolition_jobs": 0,
            "collection_jobs": 0,
        }

    driver_settle[did]["jobs"] += 1
    if o.get("work_type") == "철거":
        driver_settle[did]["demolition_jobs"] += 1
    else:
        driver_settle[did]["collection_jobs"] += 1

    if o.get("arbitrary_fee_flag"):
        driver_settle[did]["flagged_jobs"] += 1
    else:
        allowance = o.get("job_allowance", 0)
        penalty = o.get("penalty_amount", 0)
        driver_settle[did]["allowance_total"] += allowance
        driver_settle[did]["penalty_total"] += penalty

    if o.get("delay_flag"):
        driver_settle[did]["delayed_jobs"] += 1

if not driver_settle and not direct_drivers:
    st.info("실행팀이 없거나 이달 완료 주문이 없습니다.")
else:
    direct_total = 0
    rows = []
    for did, s in driver_settle.items():
        drv = s["driver"]
        monthly = drv.get("monthly_jobs", 0)
        op_cost = FULL_COST if monthly >= DIRECT_THRESHOLD else HALF_COST
        op_label = f"₩{op_cost:,}" + (" ✅" if monthly >= DIRECT_THRESHOLD else f" ⚠️({monthly}건/{DIRECT_THRESHOLD}건미달→50%)")

        net_allowance = max(0, s["allowance_total"] - s["penalty_total"])
        ace = sum(b["amount"] for b in ace_bonuses if b.get("driver_id") == did)
        subtotal = op_cost + net_allowance + ace
        withholding = subtotal * WITHHOLDING
        net_total = subtotal - withholding
        direct_total += net_total

        # 팀 컬러 표시
        team_color = drv.get("team_color", "")
        team_label = EXEC_TEAMS.get(team_color, "—")

        rows.append({
            "팀": team_label,
            "팀장명": drv["name"],
            "이달 완료": f"{monthly}건",
            "수거건": f"{s['collection_jobs']}건",
            "철거건": f"{s['demolition_jobs']}건",
            "지연건": f"{s['delayed_jobs']}건 ⏰" if s["delayed_jobs"] else "—",
            "적발건": f"{s['flagged_jobs']}건 🚨" if s["flagged_jobs"] else "—",
            "조건부운영비": op_label,
            "건당수당합계": f"₩{s['allowance_total']:,}",
            "패널티차감": f"-₩{s['penalty_total']:,}" if s["penalty_total"] else "—",
            "순수당": f"₩{net_allowance:,}",
            "Ace Bonus": f"₩{ace:,}" if ace else "—",
            "소계": f"₩{subtotal:,}",
            "원천징수(3.3%)": f"-₩{withholding:,.0f}",
            "실지급액": f"₩{net_total:,.0f}",
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        for did, s in driver_settle.items():
            drv = s["driver"]
            if s["flagged_jobs"] > 0:
                penalty_amount = sum(
                    o.get("penalty_amount", 0)
                    for o in month_orders
                    if o.get("driver_id") == did and o.get("arbitrary_fee_flag")
                )
                st.error(
                    f"🚨 **{drv['name']}** — 임의추가요금 {s['flagged_jobs']}건 적발 | "
                    f"수당 0원 처리 + **₩{penalty_amount:,.0f} 3배 배상 청구 경고 발동**"
                )
            if s["delayed_jobs"] > 0:
                st.warning(f"⏰ **{drv['name']}** — 지연 {s['delayed_jobs']}건 발생, 패널티 차감 적용됨")

        for d in direct_drivers:
            if d["id"] not in driver_settle:
                monthly = d.get("monthly_jobs", 0)
                op_cost = FULL_COST if monthly >= DIRECT_THRESHOLD else HALF_COST
                st.info(
                    f"ℹ️ **{d['name']}** — 이달 확인된 완료 주문 없음 | "
                    f"월 {monthly}건 → 운영비 ₩{op_cost:,} {'(전액)' if monthly >= DIRECT_THRESHOLD else '(50%)'}"
                )

st.divider()

# ──────────────────────────────────────────
# SECTION 3: Ace Bonus 합산
# ──────────────────────────────────────────
st.header("🏆 3. Ace Bonus 지급 현황")

month_ace = [b for b in ace_bonuses if
             b.get("created_at", "")[:7] == f"{year}-{month:02d}"]

if not month_ace:
    st.info("이달 지급된 Ace Bonus가 없습니다.")
else:
    ace_rows = [{"팀장명": b["driver_name"], "지급액": f"₩{b['amount']:,}", "사유": b.get("reason", "—"),
                 "지급일시": b.get("created_at", "—")} for b in month_ace]
    st.dataframe(pd.DataFrame(ace_rows), use_container_width=True, hide_index=True)
    total_ace_month = sum(b["amount"] for b in month_ace)
    st.metric("이달 Ace Bonus 총액", f"₩{total_ace_month:,}")

st.divider()

# ──────────────────────────────────────────
# SECTION 4: 종합 정산 요약
# ──────────────────────────────────────────
st.header("📊 4. 종합 정산 요약")

confirmed_orders = [o for o in month_orders if o.get("payment_confirmed")]
total_revenue = sum(
    o["base_fee"] + (o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0)
    for o in confirmed_orders
)
cs_revenue = total_revenue * CS_RATIO
success_fee_revenue = total_revenue * SUCCESS_FEE_RATIO

total_allowance_all = sum(
    max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0))
    for o in month_orders if not o.get("arbitrary_fee_flag")
)
total_ace_all = sum(b["amount"] for b in ace_bonuses)
total_direct_op = sum(
    (FULL_COST if d.get("monthly_jobs", 0) >= DIRECT_THRESHOLD else HALF_COST)
    for d in direct_drivers
)
withholding_total = (total_allowance_all + total_direct_op + total_ace_all) * WITHHOLDING
total_out = manager_total + total_direct_op + total_allowance_all + total_ace_all

s1, s2, s3, s4 = st.columns(4)
with s1:
    st.metric("📥 총 확정 매출", f"₩{total_revenue:,}")
with s2:
    st.metric("📤 CS 수익", f"₩{cs_revenue:,.0f}")
with s3:
    st.metric("📤 성공보수", f"₩{success_fee_revenue:,.0f}")
with s4:
    st.metric("📦 완료 주문 수", f"{len(month_orders)}건")

st.divider()

o1, o2, o3, o4, o5 = st.columns(5)
with o1:
    st.metric("👔 매니저 지급", f"₩{manager_total:,}")
with o2:
    st.metric("🚗 실행팀 운영비", f"₩{total_direct_op:,}")
with o3:
    st.metric("🔧 건당 수당 합계", f"₩{total_allowance_all:,}")
with o4:
    st.metric("🏆 Ace Bonus 합계", f"₩{total_ace_all:,}")
with o5:
    st.metric("🧾 원천징수 합계", f"-₩{withholding_total:,.0f}")

st.divider()

net_profit = total_revenue - total_out
profit_color = "normal" if net_profit >= 0 else "inverse"

final_col1, final_col2, final_col3 = st.columns(3)
with final_col1:
    st.metric("💸 총 지출 (인건비 계)", f"₩{total_out:,}")
with final_col2:
    st.metric("🧾 원천징수 대상액", f"₩{(total_allowance_all + total_direct_op + total_ace_all):,}")
with final_col3:
    st.metric("💰 순이익 (매출 - 인건비)", f"₩{net_profit:,.0f}",
              delta=f"{'흑자' if net_profit >= 0 else '적자'}", delta_color=profit_color)

st.divider()

# ─── 리스크 요약
risky_flagged = sum(1 for o in month_orders if o.get("arbitrary_fee_flag"))
risky_delayed = sum(1 for o in month_orders if o.get("delay_flag"))
penalty_deducted = sum(o.get("penalty_amount", 0) for o in month_orders)
demo_count_summary = sum(1 for o in month_orders if o.get("work_type") == "철거")
collection_count = sum(1 for o in month_orders if o.get("work_type") == "수거")

st.subheader("⚠️ 리스크 & 품질 요약")
r1, r2, r3, r4, r5 = st.columns(5)
with r1:
    st.metric("🚨 임의추가요금 적발", f"{risky_flagged}건", delta_color="inverse" if risky_flagged else "off")
with r2:
    st.metric("⏰ 지연 발생", f"{risky_delayed}건", delta_color="inverse" if risky_delayed else "off")
with r3:
    st.metric("💸 패널티 차감 합계", f"₩{penalty_deducted:,}", delta_color="inverse" if penalty_deducted else "off")
with r4:
    st.metric("📦 수거 건수", f"{collection_count}건")
with r5:
    st.metric("🔨 철거 건수", f"{demo_count_summary}건")

st.divider()

# ─── 저장 버튼
st.subheader("💾 정산 명세서 저장")
if st.button("📥 이달 정산 명세서 저장", type="primary"):
    add_manager_settlement({
        "period": f"{year}-{month:02d}",
        "manager_base": MANAGER_BASE,
        "demo_incentive": demo_incentive,
        "retention_bonus": retention_bonus,
        "manager_total": manager_total,
        "direct_op_cost": total_direct_op,
        "allowance_total": total_allowance_all,
        "ace_bonus_total": total_ace_all,
        "withholding_total": withholding_total,
        "total_revenue": total_revenue,
        "net_profit": net_profit,
        "flagged_jobs": risky_flagged,
        "delayed_jobs": risky_delayed,
    })
    st.success(f"✅ {month_label} 정산 명세서가 저장되었습니다!")

saved = get_manager_settlements()
if saved:
    st.subheader("📂 저장된 정산 이력")
    saved_rows = []
    for rec in reversed(saved[-10:]):
        saved_rows.append({
            "정산 기간": rec.get("period", "—"),
            "매니저 지급": f"₩{rec.get('manager_total', 0):,}",
            "실행팀 운영비": f"₩{rec.get('direct_op_cost', 0):,}",
            "총 매출": f"₩{rec.get('total_revenue', 0):,}",
            "순이익": f"₩{rec.get('net_profit', 0):,}",
            "적발건": f"{rec.get('flagged_jobs', 0)}건",
            "저장일시": rec.get("created_at", "—"),
        })
    st.dataframe(pd.DataFrame(saved_rows), use_container_width=True, hide_index=True)

show_legal_warning()
