import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import get_waiting_executors, add_waiting_executor, update_waiting_executor, get_drivers, save_driver
from utils.footer import show_legal_warning
from utils.rbac import render_role_selector, is_cs, is_executor
from utils.masks import mask_phone
from datetime import datetime
import pandas as pd

st.set_page_config(page_title="대기 실행자 — 순삭 OS", page_icon="📋", layout="wide")

render_role_selector()

if is_cs() or is_executor():
    st.error("🚫 이 페이지는 접근 권한이 없습니다.")
    st.stop()

st.title("📋 대기 실행자 관리 (Waiting List)")
st.caption("대표가 새로 발굴한 실행자를 먼저 등록 → 매니저가 배정 → 법인폰 소통 의무")

st.warning(
    "⚠️ **소통 규정:** 이 명단의 실행자와 모든 소통은 반드시 **법인폰**으로만 진행해야 합니다. "
    "개인 연락처를 통한 우회 배정은 계약 위반입니다."
)

tab1, tab2, tab3 = st.tabs(["📋 대기 명단", "➕ 실행자 등록", "✅ 직영 전환"])

with tab1:
    st.subheader("현재 대기 실행자 목록")

    role = st.radio("열람 권한", ["매니저", "관리자(대표)"], horizontal=True, key="exec_role")
    is_admin = role == "관리자(대표)"

    executors = get_waiting_executors()
    if not executors:
        st.info("등록된 대기 실행자가 없습니다.")
    else:
        status_filter = st.multiselect(
            "상태 필터",
            ["대기중", "배정됨", "직영전환", "제외"],
            default=["대기중", "배정됨"]
        )
        filtered = [e for e in executors if e.get("status", "대기중") in status_filter]

        if not filtered:
            st.info("해당 상태의 실행자가 없습니다.")
        else:
            for e in filtered:
                status = e.get("status", "대기중")
                status_icon = {"대기중": "⏳", "배정됨": "🔄", "직영전환": "✅", "제외": "❌"}.get(status, "—")
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.markdown(f"**{status_icon} {e['name']}**")
                    phone_display = mask_phone(e.get("phone", ""), "admin" if is_admin else "manager")
                    st.caption(f"📞 {phone_display} | 전문: {'🔨 철거' if e.get('specialty') == '철거' else '📦 수거'}")
                    st.caption(f"지역: {e.get('region', '—')} | 등록: {e.get('registered_at', '—')[:10]}")
                    if e.get("note"):
                        st.caption(f"📝 메모: {e['note']}")
                with col2:
                    if status == "대기중":
                        if st.button("📲 배정 처리", key=f"assign_exec_{e['id']}"):
                            update_waiting_executor(e["id"], {"status": "배정됨"})
                            st.success(f"{e['name']} 배정 처리됨")
                            st.rerun()
                with col3:
                    if status not in ("직영전환", "제외"):
                        if st.button("✅ 직영 전환", key=f"direct_{e['id']}"):
                            st.session_state[f"direct_{e['id']}"] = True
                        if st.button("❌ 제외", key=f"exclude_{e['id']}"):
                            update_waiting_executor(e["id"], {"status": "제외"})
                            st.rerun()

                if st.session_state.get(f"direct_{e['id']}"):
                    st.info(f"**{e['name']}**을 직영팀으로 전환합니다.")
                    confirm_col1, confirm_col2 = st.columns(2)
                    with confirm_col1:
                        if st.button("✅ 직영 전환 확정", key=f"confirm_direct_{e['id']}"):
                            from data.db import next_driver_id
                            new_driver = {
                                "id": next_driver_id(),
                                "name": e["name"],
                                "phone": e.get("phone", ""),
                                "rating": 4.0,
                                "available": True,
                                "available_from": "08:00",
                                "available_to": "20:00",
                                "completed_jobs": 0,
                                "license": "1종보통",
                                "driver_type": "직영",
                                "monthly_jobs": 0,
                                "collection_jobs": 0,
                                "demolition_jobs": 0,
                                "avg_satisfaction": None,
                            }
                            save_driver(new_driver)
                            update_waiting_executor(e["id"], {"status": "직영전환"})
                            st.success(f"✅ {e['name']} 직영팀 전환 완료!")
                            st.session_state[f"direct_{e['id']}"] = False
                            st.rerun()
                    with confirm_col2:
                        if st.button("취소", key=f"cancel_direct_{e['id']}"):
                            st.session_state[f"direct_{e['id']}"] = False
                            st.rerun()

                st.divider()

with tab2:
    st.subheader("새 대기 실행자 등록")
    st.caption("대표자가 직접 발굴한 실행자를 사전 등록합니다.")
    with st.form("waiting_exec_form"):
        col1, col2 = st.columns(2)
        with col1:
            exec_name = st.text_input("이름", placeholder="홍길동")
            exec_phone = st.text_input("연락처", placeholder="010-0000-0000")
            exec_specialty = st.selectbox("전문 분야", ["수거", "철거", "수거+철거"])
        with col2:
            exec_region = st.text_input("담당 지역", placeholder="서울 강남구")
            exec_note = st.text_area("메모", placeholder="경력 사항, 특이사항 등")
        submitted = st.form_submit_button("📋 대기 목록에 등록", type="primary")
        if submitted:
            if not exec_name or not exec_phone:
                st.error("이름과 연락처는 필수입니다.")
            else:
                add_waiting_executor({
                    "name": exec_name,
                    "phone": exec_phone,
                    "specialty": exec_specialty,
                    "region": exec_region,
                    "note": exec_note,
                })
                st.success(f"✅ {exec_name} 대기 목록에 등록 완료!")
                st.rerun()

with tab3:
    st.subheader("직영 전환 이력")
    executors = get_waiting_executors()
    converted = [e for e in executors if e.get("status") == "직영전환"]
    if not converted:
        st.info("직영 전환된 실행자가 없습니다.")
    else:
        rows = [{"이름": e["name"], "전문": e.get("specialty", "—"),
                 "지역": e.get("region", "—"), "등록일": e.get("registered_at", "—")[:10]}
                for e in converted]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.metric("누적 직영 전환", f"{len(converted)}명")

show_legal_warning()
