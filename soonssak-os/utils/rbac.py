"""
순삭 OS — 역할 기반 접근 제어 (RBAC)
확정 체제: Owner 1명 / Manager 세종 1명 / Manager 본사 1명 / CS / Executor
"""
import streamlit as st

ROLES = {
    "owner":           {"label": "👑 대표(Owner)",      "desc": "전체 지역 통합 조회 · 시스템 설정 전권"},
    "manager_sejong":  {"label": "👔 매니저 1 (세종)",   "desc": "세종 지역 리드·기사 관리 (타 지역 차단)"},
    "manager_bonsa":   {"label": "👔 매니저 2 (본사)",   "desc": "본사 지역 리드·기사 관리 (타 지역 차단)"},
    "executor":        {"label": "🚗 기사(Executor)",    "desc": "본인 배차·작업 보고·개인 정산만"},
    "cs":              {"label": "🎧 CS 상담원",         "desc": "상담 입력·예약 현황 (마진 비공개)"},
}

# 하위 호환: manager 키를 manager_bonsa로 매핑
_LEGACY_MAP = {"manager": "manager_bonsa"}

_SESSION_KEY = "_soonssak_role"

# 역할 → 담당 지역 매핑 (Manager만 사용; Owner는 전체)
ROLE_REGION = {
    "manager_sejong": "세종",
    "manager_bonsa":  "본사",
}


def render_role_selector(sidebar: bool = True) -> str:
    options = list(ROLES.keys())
    labels  = [ROLES[r]["label"] for r in options]

    current = st.session_state.get(_SESSION_KEY, "manager_bonsa")
    # 하위 호환 처리
    current = _LEGACY_MAP.get(current, current)
    if current not in options:
        current = "manager_bonsa"
    current_idx = options.index(current)

    target = st.sidebar if sidebar else st

    target.markdown("---")
    target.markdown("**🔐 현재 역할**")
    selected_label = target.selectbox(
        "역할 선택",
        labels,
        index=current_idx,
        key="__rbac_role_selector__",
        help="역할에 따라 표시 정보와 수정 권한이 달라집니다",
        label_visibility="collapsed",
    )
    selected_key = options[labels.index(selected_label)]
    st.session_state[_SESSION_KEY] = selected_key
    target.caption(ROLES[selected_key]["desc"])
    return selected_key


def current_role() -> str:
    raw = st.session_state.get(_SESSION_KEY, "manager_bonsa")
    return _LEGACY_MAP.get(raw, raw)


def is_owner()    -> bool:
    return current_role() == "owner"

def is_manager()  -> bool:
    """Owner 포함 Manager 계열 전체"""
    return current_role() in ("owner", "manager_sejong", "manager_bonsa")

def is_manager_only() -> bool:
    """순수 Manager (Owner 제외)"""
    return current_role() in ("manager_sejong", "manager_bonsa")

def is_executor() -> bool:
    return current_role() == "executor"

def is_cs()       -> bool:
    return current_role() == "cs"

def manager_region() -> str:
    """현재 Manager의 담당 지역. Owner/기타는 '전체'."""
    return ROLE_REGION.get(current_role(), "전체")


def require_role(*allowed_keys: str) -> bool:
    role = current_role()
    if role not in allowed_keys:
        st.error(
            f"🚫 **접근 권한 없음** — 현재 역할: **{ROLES.get(role, {}).get('label', role)}**\n\n"
            f"이 페이지는 **{', '.join(ROLES[k]['label'] for k in allowed_keys if k in ROLES)}** 만 접근할 수 있습니다."
        )
        return True
    return False


def role_badge() -> str:
    role = current_role()
    colors = {
        "owner": "#6a1b9a",
        "manager_sejong": "#1565c0", "manager_bonsa": "#0277bd",
        "executor": "#2e7d32", "cs": "#e65100",
    }
    label  = ROLES.get(role, {}).get("label", role)
    color  = colors.get(role, "#555")
    return (
        f"<span style='background:{color};color:white;padding:2px 10px;"
        f"border-radius:4px;font-size:13px;font-weight:bold'>{label}</span>"
    )
