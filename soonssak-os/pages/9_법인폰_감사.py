import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (
    get_drivers, get_orders, get_subcontractors, get_waiting_executors,
    save_phone_logs, get_phone_logs, get_settings
)
from utils.footer import show_legal_warning
import pandas as pd
from datetime import datetime
import io

st.set_page_config(page_title="법인폰 감사 — 순삭 OS", page_icon="📵", layout="wide")
st.title("📵 법인폰 로그 감사 시스템")

settings = get_settings()
managers = settings.get("managers", [])
regions = settings.get("regions", ["본사", "세종"])

# 현재 뷰 모드 (어드민 vs 세종 매니저)
view_mode = st.sidebar.radio(
    "보기 모드",
    ["🏢 전체 (대표/관리자)", "🗺️ 세종 지역 매니저"],
    help="역할에 따라 표시 범위가 다릅니다"
)
is_sejong_view = view_mode == "🗺️ 세종 지역 매니저"
view_region = "세종" if is_sejong_view else None

# 법적 고지 (전체 공통)
st.error(
    "🔒 **법인폰 로그는 회사의 자산이며 상시 모니터링 대상입니다 (계약서 제48조).** "
    "등록되지 않은 번호와의 통화 및 업무 시간 외 반복 통화는 자동으로 '부정 의심'으로 분류됩니다. "
    "업무 투명성을 위해 모든 법인폰 통화 기록은 본사에서 관리합니다."
)

if is_sejong_view:
    st.warning(
        "🗺️ **세종 지역 매니저 뷰** — 세종 법인폰(B) 로그와 세종 지역 고객 DB만 표시됩니다.\n\n"
        "⚖️ 법인폰 로그는 회사의 자산이며 운영 투명성을 위해 관리됩니다 (계약서 제48조 준수)."
    )

tab1, tab2, tab3, tab4 = st.tabs([
    "📂 로그 업로드", "🔍 자동 대조 분석", "🚨 부정 의심 리포트", "🗺️ 지역별 통화 현황"
])


def get_all_registered_numbers(region_filter=None):
    registered = {}
    for d in get_drivers():
        if region_filter and d.get("region") != region_filter:
            continue
        ph = d.get("phone", "").replace("-", "").replace(" ", "")
        if ph:
            registered[ph] = {"name": d["name"], "type": "직영기사",
                               "raw": d.get("phone", ""), "region": d.get("region", "본사")}
    for o in get_orders():
        if region_filter and o.get("region") != region_filter:
            continue
        ph = o.get("customer_phone", "").replace("-", "").replace(" ", "")
        if ph:
            registered[ph] = {"name": o["customer"], "type": "고객",
                               "raw": o.get("customer_phone", ""), "region": o.get("region", "본사")}
    for sc in get_subcontractors():
        ph = sc.get("phone", "").replace("-", "").replace(" ", "")
        if ph:
            registered[ph] = {"name": sc["name"], "type": "외주파트너",
                               "raw": sc.get("phone", ""), "region": "전체"}
    for we in get_waiting_executors():
        ph = we.get("phone", "").replace("-", "").replace(" ", "")
        if ph:
            registered[ph] = {"name": we["name"], "type": "대기실행자",
                               "raw": we.get("phone", ""), "region": "전체"}
    # 매니저 법인폰 등록
    for m in managers:
        ph = m.get("corporate_phone", "").replace("-", "").replace(" ", "")
        if ph:
            registered[ph] = {"name": m["name"], "type": "매니저(법인폰)",
                               "raw": m.get("corporate_phone", ""), "region": m.get("region", "본사")}
    return registered


def is_off_hours(time_str):
    try:
        t = datetime.strptime(str(time_str).strip(), "%H:%M")
        return t.hour < 8 or t.hour >= 22
    except Exception:
        try:
            t = datetime.strptime(str(time_str).strip(), "%H:%M:%S")
            return t.hour < 8 or t.hour >= 22
        except Exception:
            return False


def parse_duration_seconds(dur_str):
    try:
        dur_str = str(dur_str).strip()
        if ":" in dur_str:
            parts = dur_str.split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        return int(dur_str)
    except Exception:
        return 0


def get_manager_by_phone(phone_raw):
    for m in managers:
        cp = m.get("corporate_phone", "").replace("-", "").replace(" ", "")
        if cp and cp == phone_raw:
            return m
    return None


# ──────────────── Tab 1: 로그 업로드 ────────────────
with tab1:
    st.subheader("📂 법인폰 통화 로그 CSV 업로드")

    st.markdown("""
    **CSV 형식 안내:**
    | 날짜 | 시간 | 발수신 | 번호 | 통화시간 |
    |------|------|--------|------|---------|
    | 2026-04-01 | 09:30 | 발신 | 010-1234-5678 | 00:03:22 |

    컬럼명: `date`, `time`, `direction`, `number`, `duration`
    """)

    # 매니저 법인폰 선택
    st.markdown("#### 📱 어느 매니저의 법인폰 로그인가요?")
    if not managers:
        st.warning("등록된 매니저가 없습니다. 설정 > 지역 및 매니저 등록에서 먼저 등록하세요.")
    else:
        mgr_options = {f"{m['name']} ({m['region']}) — {m.get('corporate_phone','—')}": m for m in managers}
        if is_sejong_view:
            mgr_options = {k: v for k, v in mgr_options.items() if v["region"] == "세종"}
        selected_mgr_key = st.selectbox("담당 매니저 선택 *", list(mgr_options.keys()))
        selected_mgr = mgr_options[selected_mgr_key]
        upload_region = selected_mgr["region"]
        upload_mgr_id = selected_mgr["id"]

        st.info(
            f"📌 선택된 법인폰: **{selected_mgr['name']}** 매니저 | "
            f"지역: **{upload_region}** | 번호: **{selected_mgr.get('corporate_phone','—')}**\n\n"
            f"업로드된 로그는 **[{upload_region} 리드]** 로 자동 태깅됩니다."
        )

        if upload_region == "세종":
            st.warning(
                "⚖️ **세종 법인폰(B) 로그 업로드 안내**\n\n"
                "이 법인폰의 통화 로그는 세종 지역 고객 DB와 자동 대조됩니다. "
                "법인폰 로그는 회사의 자산이며 운영 투명성을 위해 관리됩니다 (계약서 제48조 준수)."
            )

    st.divider()

    uploaded = st.file_uploader("CSV 파일 업로드", type=["csv"])
    if uploaded and managers:
        try:
            df = pd.read_csv(uploaded)
            df.columns = [c.strip().lower() for c in df.columns]
            col_map = {
                "date": ["date", "날짜", "일자"],
                "time": ["time", "시간"],
                "direction": ["direction", "발수신", "구분"],
                "number": ["number", "번호", "전화번호"],
                "duration": ["duration", "통화시간", "시간"],
            }
            renamed = {}
            for std, variants in col_map.items():
                for v in variants:
                    if v in df.columns:
                        renamed[v] = std
                        break
            df = df.rename(columns=renamed)
            required = ["date", "time", "number"]
            if not all(c in df.columns for c in required):
                st.error(f"필수 컬럼 누락: {required}")
            else:
                logs = df.to_dict("records")
                # 지역 + 매니저 자동 태깅
                for log in logs:
                    log["region"] = upload_region
                    log["manager_id"] = upload_mgr_id
                    log["corporate_phone"] = selected_mgr.get("corporate_phone", "")
                save_phone_logs(logs)
                tagged_count = len([l for l in logs if l.get("region") == "세종"])
                st.success(
                    f"✅ {len(logs)}건의 로그 업로드 완료!\n\n"
                    f"🗺️ [{upload_region} 리드] 자동 태깅: **{len(logs)}건**"
                )
                st.dataframe(df.head(10), use_container_width=True)
        except Exception as e:
            st.error(f"파일 파싱 오류: {e}")

    st.divider()
    st.subheader("📝 샘플 데이터 생성 (테스트용)")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("🎲 본사 법인폰 샘플 로그 생성"):
            sample_logs = [
                {"date": "2026-04-01", "time": "09:30", "direction": "발신",
                 "number": "010-1234-5678", "duration": "00:02:11",
                 "region": "본사", "manager_id": 1, "corporate_phone": "010-0000-0001"},
                {"date": "2026-04-01", "time": "14:00", "direction": "수신",
                 "number": "010-9999-0001", "duration": "00:01:05",
                 "region": "본사", "manager_id": 1, "corporate_phone": "010-0000-0001"},
                {"date": "2026-04-01", "time": "23:15", "direction": "발신",
                 "number": "010-9999-9999", "duration": "00:07:33",
                 "region": "본사", "manager_id": 1, "corporate_phone": "010-0000-0001"},
            ]
            existing = get_phone_logs()
            save_phone_logs(existing + sample_logs)
            st.success("✅ 본사 법인폰 샘플 3건 생성됨!")
            st.rerun()
    with col_s2:
        if st.button("🎲 세종 법인폰(B) 샘플 로그 생성"):
            sample_logs = [
                {"date": "2026-04-02", "time": "10:00", "direction": "수신",
                 "number": "044-100-0001", "duration": "00:03:00",
                 "region": "세종", "manager_id": 2, "corporate_phone": "010-0000-0002"},
                {"date": "2026-04-02", "time": "22:45", "direction": "발신",
                 "number": "010-9999-0002", "duration": "00:11:20",
                 "region": "세종", "manager_id": 2, "corporate_phone": "010-0000-0002"},
                {"date": "2026-04-03", "time": "02:00", "direction": "발신",
                 "number": "010-7777-0000", "duration": "00:12:00",
                 "region": "세종", "manager_id": 2, "corporate_phone": "010-0000-0002"},
            ]
            existing = get_phone_logs()
            save_phone_logs(existing + sample_logs)
            st.success("✅ 세종 법인폰 샘플 3건 생성됨!")
            st.rerun()

    existing_logs = get_phone_logs()
    if existing_logs:
        filtered_logs = [l for l in existing_logs if not is_sejong_view or l.get("region") == "세종"]
        st.info(f"현재 저장된 로그: **{len(existing_logs)}건** 전체 | **{len(filtered_logs)}건** 표시 중")
        if not is_sejong_view and st.button("🗑️ 로그 전체 삭제"):
            save_phone_logs([])
            st.success("삭제 완료")
            st.rerun()


# ──────────────── Tab 2: 자동 대조 분석 ────────────────
with tab2:
    st.subheader("🔍 시스템 번호 자동 대조")

    logs = get_phone_logs()
    if not logs:
        st.warning("업로드된 로그가 없습니다. '로그 업로드' 탭에서 먼저 업로드하세요.")
    else:
        # 세종 뷰이면 세종 로그만
        if is_sejong_view:
            logs = [l for l in logs if l.get("region") == "세종"]
            st.info("🗺️ 세종 법인폰(B) 로그만 표시됩니다.")
        else:
            # 지역 필터 옵션
            region_filter_opt = st.selectbox("지역 필터", ["전체"] + regions)
            if region_filter_opt != "전체":
                logs = [l for l in logs if l.get("region") == region_filter_opt]

        registered = get_all_registered_numbers(region_filter="세종" if is_sejong_view else None)
        st.info(f"📋 등록 번호: **{len(registered)}개** | 로그: **{len(logs)}건**")

        if logs:
            analysis = []
            _new_unregistered = []  # 이번 분석에서 새로 감지된 미등록 번호
            for log in logs:
                raw_num = str(log.get("number", "")).replace("-", "").replace(" ", "")
                reg = registered.get(raw_num)
                duration_sec = parse_duration_seconds(log.get("duration", 0))
                off_hr = is_off_hours(log.get("time", "12:00"))
                log_region = log.get("region", "—")
                mgr_id = log.get("manager_id")
                mgr = next((m for m in managers if m["id"] == mgr_id), None)

                flags = []
                if not reg:
                    flags.append("미등록 번호")
                    _new_unregistered.append({
                        "phone": log.get("number", "—"),
                        "contact_name": "미등록",
                        "driver_name": mgr["name"] if mgr else "—",
                        "log_key": f"{log.get('date','')}-{log.get('number','')}",
                    })
                if off_hr:
                    flags.append("업무시간 외(22시~8시)")
                if duration_sec >= 300:
                    flags.append(f"장시간 통화({duration_sec//60}분)")

                analysis.append({
                    "날짜": log.get("date", "—"),
                    "시간": log.get("time", "—"),
                    "발수신": log.get("direction", "—"),
                    "번호": log.get("number", "—"),
                    "통화시간": log.get("duration", "—"),
                    "지역": f"[{log_region} 리드]" if log_region else "—",
                    "매니저": mgr["name"] if mgr else "—",
                    "등록여부": f"✅ {reg['type']} ({reg['name']})" if reg else "❌ 미등록",
                    "이상징후": " | ".join(flags) if flags else "—",
                    "_risk": len(flags),
                })

            df_all = pd.DataFrame(analysis)
            st.dataframe(
                df_all.drop(columns=["_risk"]),
                use_container_width=True,
                hide_index=True
            )

            # ── 미등록 번호 카카오 알림
            if _new_unregistered:
                uniq_phones = {u["log_key"]: u for u in _new_unregistered}
                st.warning(
                    f"📱 **미등록 번호 {len(uniq_phones)}건** 감지됨 — "
                    f"대표님께 카카오 알림을 발송하세요."
                )
                if st.button("📲 미등록 번호 알림 즉시 발송", key="send_unregistered_notif"):
                    from utils.notifications import notify_unregistered_phone
                    sent_cnt = 0
                    for item in uniq_phones.values():
                        try:
                            notify_unregistered_phone(
                                phone=item["phone"],
                                contact_name=item["contact_name"],
                                driver_name=item["driver_name"],
                            )
                            sent_cnt += 1
                        except Exception:
                            pass
                    st.success(f"✅ 미등록 번호 알림 {sent_cnt}건 발송 완료")

            # 세종 리드 요약
            sejong_leads = [a for a in analysis if "[세종 리드]" in a.get("지역", "")]
            if sejong_leads:
                st.info(f"🗺️ **세종 리드 자동 분류:** {len(sejong_leads)}건 — 세종 법인폰으로 접수된 통화")


# ──────────────── Tab 3: 부정 의심 리포트 ────────────────
with tab3:
    st.subheader("🚨 부정 의심 리포트")

    logs = get_phone_logs()
    if not logs:
        st.warning("업로드된 로그가 없습니다.")
    else:
        if is_sejong_view:
            logs = [l for l in logs if l.get("region") == "세종"]
        registered = get_all_registered_numbers(region_filter="세종" if is_sejong_view else None)

        suspicious = []
        for log in logs:
            raw_num = str(log.get("number", "")).replace("-", "").replace(" ", "")
            reg = registered.get(raw_num)
            duration_sec = parse_duration_seconds(log.get("duration", 0))
            off_hr = is_off_hours(log.get("time", "12:00"))
            log_region = log.get("region", "—")
            mgr_id = log.get("manager_id")
            mgr = next((m for m in managers if m["id"] == mgr_id), None)

            flags = []
            risk_level = "낮음"
            if not reg:
                flags.append("미등록 번호")
                risk_level = "중간"
            if off_hr:
                flags.append("업무시간 외(22시~8시)")
                risk_level = "높음"
            if duration_sec >= 300:
                flags.append(f"장시간 통화({duration_sec//60}분)")
                if risk_level != "높음":
                    risk_level = "중간"
            if not reg and off_hr:
                risk_level = "매우높음"
            if not reg and off_hr and duration_sec >= 300:
                risk_level = "🚨 위험"

            if flags:
                suspicious.append({
                    "날짜": log.get("date", "—"),
                    "시간": log.get("time", "—"),
                    "발수신": log.get("direction", "—"),
                    "번호": log.get("number", "—"),
                    "통화시간": log.get("duration", "—"),
                    "지역": f"[{log_region} 리드]" if log_region else "—",
                    "매니저": mgr["name"] if mgr else "—",
                    "이상징후": " | ".join(flags),
                    "위험도": risk_level,
                })

        if not suspicious:
            st.success("✅ 부정 의심 통화 없음")
        else:
            risk_colors = {
                "🚨 위험": "🔴", "매우높음": "🟠", "높음": "🟡", "중간": "🟡", "낮음": "🟢"
            }
            risk_order = {"🚨 위험": 5, "매우높음": 4, "높음": 3, "중간": 2, "낮음": 1}
            suspicious_sorted = sorted(suspicious, key=lambda x: risk_order.get(x["위험도"], 0), reverse=True)

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("🚨 부정 의심 건", f"{len(suspicious)}건")
            with col_m2:
                high_risk = len([s for s in suspicious if s["위험도"] in ("🚨 위험", "매우높음")])
                st.metric("🔴 고위험", f"{high_risk}건")
            with col_m3:
                sejong_suspicious = len([s for s in suspicious if "세종" in s.get("지역", "")])
                st.metric("🗺️ 세종 의심", f"{sejong_suspicious}건")
            with col_m4:
                off_hr_cnt = len([s for s in suspicious if "업무시간 외" in s.get("이상징후", "")])
                st.metric("🌙 업무시간 외", f"{off_hr_cnt}건")

            df_sus = pd.DataFrame(suspicious_sorted)
            st.dataframe(df_sus, use_container_width=True, hide_index=True)

            csv_buf = io.StringIO()
            df_sus.to_csv(csv_buf, index=False, encoding="utf-8-sig")
            st.download_button(
                "📥 부정 의심 리포트 다운로드 (CSV)",
                csv_buf.getvalue().encode("utf-8-sig"),
                file_name=f"suspicious_report_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )


# ──────────────── Tab 4: 지역별 통화 현황 ────────────────
with tab4:
    st.subheader("🗺️ 지역별 통화 현황")

    logs_all = get_phone_logs()
    if not logs_all:
        st.warning("업로드된 로그가 없습니다.")
    else:
        if is_sejong_view:
            logs_all = [l for l in logs_all if l.get("region") == "세종"]

        # 지역별 집계
        region_stats = {}
        for log in logs_all:
            r = log.get("region") or "미분류"
            if r not in region_stats:
                region_stats[r] = {"건수": 0, "업무외": 0, "미등록": 0}
            region_stats[r]["건수"] += 1

            registered_all = get_all_registered_numbers()
            raw_num = str(log.get("number", "")).replace("-", "").replace(" ", "")
            if raw_num not in registered_all:
                region_stats[r]["미등록"] += 1
            if is_off_hours(log.get("time", "12:00")):
                region_stats[r]["업무외"] += 1

        if region_stats:
            rows = []
            for region_name, stats in region_stats.items():
                mgr_names = [m["name"] for m in managers if m["region"] == region_name]
                rows.append({
                    "지역": region_name,
                    "총 통화": stats["건수"],
                    "미등록 번호": stats["미등록"],
                    "업무시간 외": stats["업무외"],
                    "담당 매니저": ", ".join(mgr_names) if mgr_names else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # 매니저별 법인폰 현황
            st.markdown("#### 📱 매니저별 법인폰 할당 현황")
            for m in managers:
                if is_sejong_view and m["region"] != "세종":
                    continue
                m_logs = [l for l in logs_all if l.get("manager_id") == m["id"]]
                status_badge = "🟢 활성" if m_logs else "⚫ 로그 없음"
                col_ma, col_mb, col_mc, col_md = st.columns(4)
                with col_ma:
                    st.markdown(f"**{m['name']}** ({m['role']})")
                with col_mb:
                    st.markdown(f"🗺️ {m['region']}")
                with col_mc:
                    st.markdown(f"📱 `{m.get('corporate_phone', '—')}`")
                with col_md:
                    st.markdown(f"{status_badge} | 통화 {len(m_logs)}건")

show_legal_warning()
