"""
순삭 OS — 모바일 전용 매니저 뷰
법인폰 접속 최적화: 내 지역 리드 / 현장 견적 입력 / 담당 기사 위치
- 타 지역 데이터 및 본사 전체 마진 정보 원천 차단
- RBAC: Manager 이상 전용
"""
import streamlit as st
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.db import (get_orders, get_drivers, get_settings, update_order,
                      save_driver, add_supply_request)
from utils.rbac import (render_role_selector, is_owner, is_manager, is_manager_only,
                         manager_region, is_cs, is_executor, role_badge)
from utils.ai_vision import save_photo

st.set_page_config(
    page_title="모바일 매니저 — 순삭 OS",
    page_icon="📱",
    layout="centered",     # 모바일 최적화: centered
    initial_sidebar_state="collapsed",
)

render_role_selector()

# ── RBAC: Manager 이상만 접근
if is_cs() or is_executor():
    st.error("🚫 **접근 권한 없음** — 모바일 매니저 화면은 매니저/대표 전용입니다.")
    st.stop()

st.markdown(
    """
<div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);
     color:white;border-radius:12px;padding:16px 20px;margin-bottom:12px;text-align:center">
<h3 style="margin:0;color:#e0e0ff">📱 순삭 OS — 모바일 매니저</h3>
<p style="margin:4px 0 0 0;font-size:0.85em;color:#aaaacc">법인폰 전용 · 내 지역 데이터만 표시</p>
</div>
""",
    unsafe_allow_html=True,
)

# ── 내 담당 지역 확인
settings = get_settings()

# Owner면 지역 선택 가능, Manager는 역할에 따라 고정
if is_owner():
    _regions = ["전체"] + settings.get("regions", ["본사", "세종"])
    _my_region = st.selectbox("🗂️ 지역 선택", _regions)
elif is_manager_only():
    # manager_region()이 세종/본사를 자동 반환
    _my_region = manager_region()
    st.markdown(
        f"<div style='background:#e8f5e9;border-left:4px solid #2e7d32;border-radius:8px;"
        f"padding:8px 14px;font-size:14px'>"
        f"📍 <b>담당 지역 고정:</b> {_my_region} — 타 지역 데이터 자동 차단</div>",
        unsafe_allow_html=True)
else:
    _my_region = "전체"

orders = get_orders()
drivers = get_drivers()

# ── 지역 필터 (Manager: 내 지역만 / Owner: 선택 지역)
if _my_region != "전체":
    orders = [o for o in orders if o.get("region", "본사") == _my_region]
    drivers = [d for d in drivers if d.get("region", "본사") == _my_region]

st.divider()

# ══════════════════════════════════════════════════════════════════════
# Tab 구성: 역할에 따라 다르게 렌더링
#  - 매니저: 4탭 (내 지역 리드 / 현장 견적 / 출발 전 체크 / 담당 기사)
#  - Owner : 3탭 (내 지역 리드 / 현장 견적 / 담당 기사) — 체크리스트 없음
# ══════════════════════════════════════════════════════════════════════
_is_mgr = is_manager_only()

if _is_mgr:
    tab_leads, tab_quote, tab_check, tab_drivers = st.tabs([
        "📋 내 지역 리드",
        "💰 현장 견적 입력",
        "🧰 출발 전 체크",
        "🗺️ 담당 기사 위치",
    ])
else:
    tab_leads, tab_quote, tab_drivers = st.tabs([
        "📋 내 지역 리드",
        "💰 현장 견적 입력",
        "🗺️ 담당 기사 위치",
    ])
    tab_check = None

# ──────────────── Tab 1: 내 지역 리드 ────────────────
with tab_leads:
    st.subheader(f"📋 {_my_region if _my_region != '전체' else '전체'} 지역 주문 리드")

    _status_filter = st.selectbox(
        "상태 필터",
        ["전체", "⏳ 대기중", "📍 배차완료", "🔄 진행중", "✅ 완료"],
        key="lead_status_filter",
    )
    _status_map = {
        "⏳ 대기중": "pending",
        "📍 배차완료": "dispatched",
        "🔄 진행중": "in_progress",
        "✅ 완료": "completed",
    }
    _filtered_orders = orders
    if _status_filter != "전체":
        _target_status = _status_map.get(_status_filter)
        _filtered_orders = [o for o in orders if o["status"] == _target_status]

    if not _filtered_orders:
        st.info("해당 조건의 주문이 없습니다.")
    else:
        for o in sorted(_filtered_orders, key=lambda x: x["created_at"], reverse=True):
            _work_icon = "🔨" if o.get("work_type") == "철거" else "📦"
            _status_labels = {
                "pending": "⏳ 대기중", "dispatched": "📍 배차완료",
                "in_progress": "🔄 진행중", "completed": "✅ 완료", "cancelled": "❌ 취소",
            }
            _status_label = _status_labels.get(o["status"], o["status"])

            with st.container():
                st.markdown(
                    f"**{_work_icon} #{o['id']} — {o['customer']}** | {_status_label}"
                )
                _c1, _c2 = st.columns(2)
                with _c1:
                    st.caption(f"📍 {o.get('pickup','—')}")
                    st.caption(f"🕐 {o.get('scheduled_time','—')}")
                with _c2:
                    st.caption(f"💰 ₩{o['base_fee']:,}")
                    _drv = next((d for d in drivers if d["id"] == o.get("driver_id")), None)
                    st.caption(f"🚗 {_drv['name'] if _drv else '미배차'}")
                st.markdown("---")

# ──────────────── Tab 2: 현장 견적 입력 ────────────────
with tab_quote:
    st.subheader("💰 현장 견적 입력")
    st.caption("철거 건 현장 방문 후 사진 3장 업로드 + 견적 확정")

    PHOTO_REQUIRED = 3
    _demo_orders = [
        o for o in orders
        if o.get("work_type") == "철거" and not o.get("manager_quote_confirmed")
    ]

    if not _demo_orders:
        st.success("✅ 모든 철거 건 견적 확정 완료")
    else:
        _order_opts = {f"#{o['id']} — {o['customer']} (₩{o['base_fee']:,})": o for o in _demo_orders}
        _selected_label = st.selectbox("주문 선택", list(_order_opts.keys()))
        _sel_order = _order_opts[_selected_label]

        st.markdown(f"**고객:** {_sel_order['customer']} | **주소:** {_sel_order.get('pickup','—')}")
        st.markdown(f"**범위:** {_sel_order.get('demolition_scope','—')} | **CS 기초견적:** ₩{_sel_order['base_fee']:,}")

        # 사진 업로드 (3장 필수)
        st.markdown(f"#### 📸 현장 사진 업로드 (필수: {PHOTO_REQUIRED}장 이상)")
        _est_photos = list(_sel_order.get("estimate_photos", []))
        if not _est_photos and _sel_order.get("estimate_photo_path"):
            if os.path.exists(_sel_order["estimate_photo_path"]):
                _est_photos = [_sel_order["estimate_photo_path"]]

        _pc = len(_est_photos)
        if _pc >= PHOTO_REQUIRED:
            st.success(f"✅ 사진 {_pc}장 — 견적 확정 가능")
        else:
            st.warning(f"⚠️ {_pc}장 업로드됨 — {PHOTO_REQUIRED - _pc}장 추가 필요")

        # 미리보기
        if _est_photos:
            _pcols = st.columns(min(_pc, 3))
            for _pi, _ep in enumerate(_est_photos[:3]):
                with _pcols[_pi]:
                    if os.path.exists(_ep):
                        st.image(_ep, caption=f"사진 {_pi+1}", use_container_width=True)

        # 추가 업로드
        if _pc < 5:
            _up_files = st.file_uploader(
                f"사진 추가 ({_pc}/{PHOTO_REQUIRED}장)",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"mob_est_{_sel_order['id']}",
            )
            if _up_files and st.button("📤 사진 저장", key=f"mob_save_{_sel_order['id']}"):
                _saved = list(_est_photos)
                for _uf in _up_files:
                    if len(_saved) >= 5:
                        break
                    ext = _uf.name.rsplit(".", 1)[-1].lower()
                    path = save_photo(_sel_order["id"], f"estimate_{len(_saved)}", _uf.read(), ext)
                    _saved.append(path)
                update_order(_sel_order["id"], {
                    "estimate_photos": _saved,
                    "estimate_photo_path": _saved[0] if _saved else None,
                })
                st.success(f"✅ {len(_up_files)}장 저장!")
                st.rerun()

        st.markdown("---")

        # 견적 금액 확정 (사진 3장 이상일 때만 활성화)
        if _pc >= PHOTO_REQUIRED:
            _quote_val = int(_sel_order.get("manager_quote") or _sel_order["base_fee"])
            _new_quote = st.number_input(
                "최종 견적 금액 (원)",
                min_value=10000,
                max_value=10000000,
                value=_quote_val,
                step=50000,
                key=f"mob_quote_{_sel_order['id']}",
            )
            if st.button("✅ 견적 확정 & 발송", type="primary", key=f"mob_confirm_{_sel_order['id']}"):
                update_order(_sel_order["id"], {
                    "manager_quote": int(_new_quote),
                    "manager_quote_confirmed": True,
                    "manager_quote_sent": True,
                    "manager_closed": True,
                    "base_fee": int(_new_quote),
                })
                st.success(f"✅ 견적 ₩{_new_quote:,} 확정 완료!")
                st.rerun()
        else:
            st.button(
                f"🔒 견적 확정 잠김 (사진 {PHOTO_REQUIRED}장 필요)",
                disabled=True,
            )

# ──────────────── Tab 3: 출발 전 비품 체크리스트 (매니저 전용) ────────────────
if tab_check is not None:
 with tab_check:
    st.subheader("🧰 출발 전 순삭 키트 체크")
    st.caption("현장 출발 전 5가지 항목을 모두 확인하세요. 전체 완료 시 고객 주소가 활성화됩니다.")

    # ── 주문 선택 (배차완료 or 대기중)
    _dept_orders = [
        o for o in orders
        if o["status"] in ("pending", "dispatched")
    ]

    if not _dept_orders:
        st.info("📭 출발 예정 주문이 없습니다.")
    else:
        _dept_opts = {
            f"#{o['id']} — {o['customer']} | {o.get('scheduled_time','—')} | "
            f"{'🔨 철거' if o.get('work_type') == '철거' else '📦 수거'}": o
            for o in sorted(_dept_orders, key=lambda x: x.get("scheduled_time",""))
        }
        _sel_dept_label = st.selectbox("출발 주문 선택", list(_dept_opts.keys()),
                                       key="dept_order_sel")
        _sel_dept = _dept_opts[_sel_dept_label]

        _oid = _sel_dept["id"]
        _addr = _sel_dept.get("pickup", "")

        st.markdown("")
        st.markdown(
            f"""
<div style="background:#fff3e0;border-left:5px solid #e65100;border-radius:10px;
     padding:12px 16px;margin-bottom:12px">
<b style="font-size:16px">📍 현장 주소</b><br>
<span style="font-size:15px;font-weight:600">{_addr if _addr else '주소 없음'}</span><br>
<span style="font-size:13px;color:#666">고객: {_sel_dept.get('customer','—')} | ₩{_sel_dept.get('base_fee',0):,}</span>
</div>
""", unsafe_allow_html=True)

        # ── 5가지 체크리스트 항목
        st.markdown("#### ✅ 순삭 키트 체크리스트")
        st.markdown(
            "<div style='background:#f3e5f5;border-radius:8px;padding:10px 14px;"
            "margin-bottom:10px;font-size:13px;color:#4a148c'>"
            "⚠️ <b>모든 항목 체크 완료 후 내비게이션 버튼이 활성화됩니다.</b></div>",
            unsafe_allow_html=True)

        _CHECKLIST = [
            ("🧤", "장갑",          "작업용 면장갑 / 고무장갑 각 1켤레 이상"),
            ("📏", "줄자",          "5m 이상 줄자 지참 여부"),
            ("🛡️", "보양재",        "바닥 보호용 보양지/보양재 충분한 수량"),
            ("📱", "법인폰 충전",    "법인폰 배터리 60% 이상 (충전 케이블 포함)"),
            ("📋", "작업지시서",     "현장 작업지시서 또는 고객 확인서 지참"),
        ]

        _all_checked = True
        for _ci, (_icon, _name, _desc) in enumerate(_CHECKLIST):
            _ck_key = f"_ck_{_oid}_{_ci}"
            _checked = st.checkbox(
                f"{_icon} **{_name}** — {_desc}",
                key=_ck_key,
                value=st.session_state.get(_ck_key, False),
            )
            if not _checked:
                _all_checked = False

        st.markdown("")

        # ── 완료 상태 표시 + 내비게이션 버튼
        if _all_checked:
            st.success("✅ **모든 항목 완료!** 지금 바로 출발하세요.")
            _map_url = (
                f"https://map.kakao.com/link/search/{_addr}"
                if _addr else ""
            )
            _google_url = (
                f"https://www.google.com/maps/search/?api=1&query={_addr}"
                if _addr else ""
            )
            nav_c1, nav_c2 = st.columns(2)
            with nav_c1:
                if _addr:
                    st.link_button(
                        "🗺️ 카카오맵으로 출발",
                        _map_url,
                        type="primary",
                        use_container_width=True,
                    )
                else:
                    st.button("🗺️ 주소 없음 (출발 불가)", disabled=True, use_container_width=True)
            with nav_c2:
                if _addr:
                    st.link_button(
                        "🌍 구글맵으로 출발",
                        _google_url,
                        use_container_width=True,
                    )
        else:
            _remaining = sum(
                1 for _ci in range(len(_CHECKLIST))
                if not st.session_state.get(f"_ck_{_oid}_{_ci}", False)
            )
            st.warning(f"🔒 **{_remaining}개 항목 미완료** — 체크 후 내비게이션이 활성화됩니다.")
            st.button(
                "🔒 내비게이션 잠김 (체크리스트 완료 필요)",
                disabled=True,
                use_container_width=True,
            )

    st.divider()

    # ── 비품 보충 신청 섹션
    st.markdown("#### 📦 비품 보충 신청")
    st.markdown(
        "<div style='background:#e8f5e9;border-left:4px solid #388e3c;border-radius:8px;"
        "padding:8px 14px;font-size:13px;color:#1b5e20;margin-bottom:10px'>"
        "📌 <b>신청 후 Owner 대시보드 '비품 관리' 탭에 숫자로만 표시됩니다.</b>"
        " 푸시 알림은 발송되지 않습니다.</div>",
        unsafe_allow_html=True)

    _SUPPLY_ITEMS = ["보양재", "장갑 (면장갑)", "장갑 (고무장갑)", "줄자",
                     "작업지시서 양식", "청소봉투", "포장테이프", "기타"]

    with st.form("supply_request_form", clear_on_submit=True):
        _sel_items = st.multiselect(
            "부족한 소모품 선택 (복수 선택 가능)",
            _SUPPLY_ITEMS,
            placeholder="신청할 비품을 선택하세요",
        )
        _qty_note = st.text_input(
            "수량/상세 메모 (예: 보양재 2팩, 장갑 10켤레)",
            placeholder="수량과 필요 이유를 간단히 입력하세요",
        )
        _urgency = st.radio(
            "긴급도",
            ["일반", "긴급"],
            horizontal=True,
        )
        _submit_supply = st.form_submit_button(
            "📤 비품 보충 신청 (Owner 대시보드에만 기록)",
            type="primary",
            use_container_width=True,
        )

    if _submit_supply:
        if not _sel_items:
            st.error("❌ 신청할 소모품을 1개 이상 선택하세요.")
        else:
            from utils.rbac import ROLES, current_role
            _mgr_label = ROLES.get(current_role(), {}).get("label", "매니저")
            _items_payload = [
                {"name": item, "qty": _qty_note or "미기재"}
                for item in _sel_items
            ]
            add_supply_request(
                region=_my_region,
                manager_label=_mgr_label,
                items=_items_payload,
                urgency=_urgency,
            )
            st.success(
                f"✅ **비품 보충 신청 완료!**\n\n"
                f"신청 항목: {', '.join(_sel_items)}\n"
                f"긴급도: {_urgency}\n\n"
                f"Owner 대시보드 '비품 관리' 탭에 자동 등록되었습니다."
            )

# ──────────────── Tab 4: 담당 기사 위치 ────────────────
with tab_drivers:
    st.subheader(f"🗺️ {_my_region} 담당 기사 현황")
    st.caption("현재 가용 상태 및 진행 중 작업 기준으로 위치를 파악합니다.")

    if not drivers:
        st.info("담당 지역에 등록된 기사가 없습니다.")
    else:
        for d in sorted(drivers, key=lambda x: (not x["available"], x.get("rating", 0)), reverse=False):
            _avail_icon = "🟢" if d["available"] else "🔴"
            _spec = d.get("specialty", "공통")
            _spec_icon = {"수거": "📦", "철거": "🔨", "공통": "⚖️"}.get(_spec, "⚖️")

            # 현재 진행 중인 주문 찾기
            _active_order = next(
                (o for o in orders if o.get("driver_id") == d["id"] and o["status"] == "in_progress"),
                None
            )

            with st.container():
                st.markdown(
                    f"{_avail_icon} **{d['name']}** {_spec_icon} {_spec} | "
                    f"⭐ {d['rating']} | 이달 {d.get('monthly_jobs', 0)}건"
                )
                if _active_order:
                    st.info(
                        f"🔄 **진행중** — #{_active_order['id']} {_active_order['customer']}님 | "
                        f"📍 {_active_order.get('pickup','—')} | "
                        f"{'🔨 철거' if _active_order.get('work_type') == '철거' else '📦 수거'}"
                    )
                else:
                    _from = d.get("available_from", "—")
                    _to = d.get("available_to", "—")
                    if d["available"]:
                        st.caption(f"✅ 가용 ({_from}~{_to}) — 배차 대기 중")
                    else:
                        st.caption(f"❌ 비가용 ({_from}~{_to})")
                st.markdown("---")

from utils.footer import show_legal_warning
show_legal_warning()
