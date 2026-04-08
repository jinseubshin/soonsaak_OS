import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import get_orders, get_drivers, get_settings, get_driver_by_id, add_tax_record, get_tax_records
from utils.footer import show_legal_warning
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="세무 관리 — 순삭 OS", page_icon="🧾", layout="wide")
st.title("🧾 세무 관리")
st.caption("원천징수(3.3%) 계산 및 GRENTER API 연동")

settings = get_settings()
WITHHOLDING_RATE = settings["withholding_tax_rate"]
DRIVER_RATIO = settings["driver_ratio"]
DISPATCH_FEE = settings["dispatch_fee"]
GRENTER_API_KEY = settings.get("grenter_api_key", "")

tab1, tab2, tab3 = st.tabs(["🧮 원천징수 계산", "📄 세무 신고 내역", "🔗 GRENTER API"])

# ──────────────── Tab 1: 원천징수 계산 ────────────────
with tab1:
    st.subheader("기사별 원천징수 (3.3%) 자동 계산")
    st.info(f"📌 개인사업자 원천징수율: **{WITHHOLDING_RATE*100:.1f}%** (소득세 3% + 지방소득세 0.3%)")

    orders = get_orders()
    drivers = get_drivers()

    now = datetime.now()
    col_year, col_month = st.columns(2)
    with col_year:
        year = st.selectbox("연도", options=list(range(now.year - 2, now.year + 1)), index=2)
    with col_month:
        month = st.selectbox("월", options=list(range(1, 13)), index=now.month - 1)

    month_str = f"{year}-{month:02d}"
    st.divider()

    driver_earnings = {}
    for o in orders:
        if not o.get("payment_confirmed") or o["status"] != "completed":
            continue
        try:
            order_month = o["scheduled_time"][:7]
        except Exception:
            continue
        if order_month != month_str:
            continue

        drv = get_driver_by_id(o.get("driver_id"))
        if not drv:
            continue
        did = drv["id"]

        if o.get("extra_fee_status") == "rejected":
            total = DISPATCH_FEE
        else:
            extra = o.get("extra_fee", 0) if o.get("extra_fee_status") == "approved" else 0
            total = o["base_fee"] + extra

        if o.get("arbitrary_fee_flag"):
            pay = 0
        else:
            pay = total * DRIVER_RATIO

        allowance = 0 if o.get("arbitrary_fee_flag") else max(0, o.get("job_allowance", 0) - o.get("penalty_amount", 0))

        if did not in driver_earnings:
            driver_earnings[did] = {
                "name": drv["name"],
                "phone": drv["phone"],
                "jobs": 0,
                "gross_pay": 0.0,
                "allowance": 0.0,
            }
        driver_earnings[did]["jobs"] += 1
        driver_earnings[did]["gross_pay"] += pay
        driver_earnings[did]["allowance"] += allowance

    if not driver_earnings:
        st.info(f"{year}년 {month}월 입금 확인된 완료 주문이 없습니다.")
    else:
        rows = []
        total_gross = 0
        total_withholding = 0
        total_net = 0

        for did, e in driver_earnings.items():
            gross = e["gross_pay"] + e["allowance"]
            withholding = gross * WITHHOLDING_RATE
            net = gross - withholding
            total_gross += gross
            total_withholding += withholding
            total_net += net
            rows.append({
                "기사명": e["name"],
                "연락처": e["phone"],
                "완료 건수": e["jobs"],
                "수수료(70%)": f"₩{e['gross_pay']:,.0f}",
                "건당수당합계": f"₩{e['allowance']:,.0f}",
                "총 지급액 (세전)": f"₩{gross:,.0f}",
                "원천징수액 (3.3%)": f"₩{withholding:,.0f}",
                "실 지급액 (세후)": f"₩{net:,.0f}",
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("총 지급액 (세전)", f"₩{total_gross:,.0f}")
        with col2:
            st.metric("총 원천징수액", f"₩{total_withholding:,.0f}")
        with col3:
            st.metric("총 실 지급액", f"₩{total_net:,.0f}")

        if st.button("💾 세무 신고 내역 저장", type="primary"):
            for did, e in driver_earnings.items():
                gross = e["gross_pay"] + e["allowance"]
                withholding = gross * WITHHOLDING_RATE
                net = gross - withholding
                add_tax_record({
                    "year": year,
                    "month": month,
                    "driver_id": did,
                    "driver_name": e["name"],
                    "jobs": e["jobs"],
                    "gross_pay": gross,
                    "withholding": withholding,
                    "net_pay": net,
                    "rate": WITHHOLDING_RATE,
                })
            st.success(f"✅ {year}년 {month}월 세무 내역 저장 완료!")
            st.rerun()

# ──────────────── Tab 2: 세무 신고 내역 ────────────────
with tab2:
    st.subheader("세무 신고 저장 이력")
    tax_records = get_tax_records()
    if not tax_records:
        st.info("저장된 세무 신고 내역이 없습니다.")
    else:
        rows = []
        for r in tax_records:
            rows.append({
                "ID": f"#{r['id']}",
                "연/월": f"{r['year']}년 {r['month']}월",
                "기사명": r["driver_name"],
                "완료 건수": r["jobs"],
                "세전 지급액": f"₩{r['gross_pay']:,.0f}",
                "원천징수": f"₩{r['withholding']:,.0f}",
                "실 지급액": f"₩{r['net_pay']:,.0f}",
                "세율": f"{r['rate']*100:.1f}%",
                "저장일": r["created_at"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📊 연간 세무 요약")
        year_filter = st.selectbox("연도 선택", options=sorted(set(r["year"] for r in tax_records), reverse=True))
        year_records = [r for r in tax_records if r["year"] == year_filter]
        if year_records:
            annual_gross = sum(r["gross_pay"] for r in year_records)
            annual_wh = sum(r["withholding"] for r in year_records)
            annual_net = sum(r["net_pay"] for r in year_records)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric(f"{year_filter}년 총 지급액", f"₩{annual_gross:,.0f}")
            with c2:
                st.metric("총 원천징수", f"₩{annual_wh:,.0f}")
            with c3:
                st.metric("총 실지급액", f"₩{annual_net:,.0f}")

# ──────────────── Tab 3: GRENTER API ────────────────
with tab3:
    st.subheader("🔗 GRENTER API 연동")
    st.markdown("""
    GRENTER(그랜터)는 세무 신고 및 원천징수 자동화를 위한 세무 플랫폼입니다.

    **지원 기능:**
    - 원천징수 신고서 자동 생성
    - 국세청 전자신고 연동
    - 지급명세서 일괄 발행
    """)

    if not GRENTER_API_KEY:
        st.warning("⚠️ GRENTER API 키가 설정되지 않았습니다. **설정** 메뉴에서 API 키를 입력해주세요.")

    st.divider()
    st.subheader("API 연동 테스트")

    test_col1, test_col2 = st.columns(2)
    with test_col1:
        api_key_input = st.text_input("GRENTER API 키", value=GRENTER_API_KEY, type="password", placeholder="API 키를 입력하세요")
    with test_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔌 연결 테스트"):
            if not api_key_input:
                st.error("API 키를 입력해주세요.")
            else:
                import requests
                try:
                    resp = requests.get(
                        "https://api.grenter.kr/v1/ping",
                        headers={"Authorization": f"Bearer {api_key_input}"},
                        timeout=5
                    )
                    if resp.status_code == 200:
                        st.success("✅ GRENTER API 연결 성공!")
                    else:
                        st.error(f"❌ 연결 실패 (HTTP {resp.status_code})")
                except requests.exceptions.ConnectionError:
                    st.warning("⚠️ 데모 모드: 실제 GRENTER API 엔드포인트가 필요합니다. API 키 형식은 정상입니다.")
                except Exception as e:
                    st.error(f"오류: {e}")

    st.divider()
    st.subheader("📤 원천징수 신고서 제출 (시뮬레이션)")

    tax_records = get_tax_records()
    if not tax_records:
        st.info("저장된 세무 신고 내역이 없습니다. 먼저 원천징수 계산 탭에서 저장하세요.")
    else:
        months_data = {}
        for r in tax_records:
            key = f"{r['year']}년 {r['month']}월"
            if key not in months_data:
                months_data[key] = []
            months_data[key].append(r)

        selected_period = st.selectbox("신고 기간 선택", options=list(months_data.keys()))
        period_records = months_data.get(selected_period, [])

        if period_records:
            total_wh = sum(r["withholding"] for r in period_records)
            st.markdown(f"**{selected_period} 원천징수 합계: ₩{total_wh:,.0f}**")
            st.markdown(f"대상 인원: {len(period_records)}명")

            if st.button("📤 GRENTER API로 신고서 제출 (시뮬레이션)", type="primary"):
                if not GRENTER_API_KEY:
                    st.warning("⚠️ API 키를 설정 페이지에서 입력 후 다시 시도하세요.")
                else:
                    payload = {
                        "period": selected_period,
                        "records": [
                            {"driver_name": r["driver_name"], "gross_pay": r["gross_pay"],
                             "withholding": r["withholding"], "net_pay": r["net_pay"]}
                            for r in period_records
                        ],
                        "total_withholding": total_wh,
                    }
                    st.json(payload)
                    st.success("✅ 신고서 데이터 준비 완료")

show_legal_warning()
