"""
순삭 OS 무인 자동 페널티 엔진

실행 시점: 기사 앱 / 메인 대시보드 / 정산 엔진 로딩 시 자동 호출
- 지연 30분 자동 감지 + 페널티 차감
- AI 사진 불일치 정산 보류 처리
- 사진 미업로드 기사 배차 제외 플래그
"""
from datetime import datetime, timedelta
from typing import Optional


# ────────────────────────────────────────────
# 1. 지연 자동 감지 + 페널티
# ────────────────────────────────────────────
DELAY_THRESHOLD_MIN = 30    # 예약 시간 초과 기준(분)
AUTO_PENALTY_AMOUNT = 20000  # 기본 자동 페널티 금액(원)


def check_and_apply_delay_penalty(orders: list, settings: dict) -> list:
    """
    진행 중인 주문 중 예약 시간 30분 초과 건 자동 페널티 적용.
    변경된 order ID 목록 반환 (DB 저장은 호출자가 처리).
    """
    from data.db import update_order
    from utils.notifications import notify_delay

    penalty_amt = settings.get("auto_penalty_amount", AUTO_PENALTY_AMOUNT)
    changed = []

    now = datetime.now()
    for o in orders:
        if o.get("status") not in ("in_progress", "dispatched"):
            continue
        if o.get("delay_auto_applied"):
            continue

        sched_str = o.get("scheduled_time", "")
        if not sched_str:
            continue

        try:
            sched_dt = datetime.strptime(sched_str[:16], "%Y-%m-%d %H:%M")
        except Exception:
            continue

        # 예약 시간 + 30분 초과 감지
        if now > sched_dt + timedelta(minutes=DELAY_THRESHOLD_MIN):
            overdue_min = int((now - sched_dt).total_seconds() / 60)
            update_order(o["id"], {
                "delay_flag": True,
                "delay_auto_applied": True,
                "delay_overdue_min": overdue_min,
                "penalty_amount": o.get("penalty_amount", 0) + penalty_amt,
            })
            changed.append(o["id"])

            # 카카오 알림 — 대표 + 기사
            try:
                notify_delay(order=o, overdue_min=overdue_min, penalty_amt=penalty_amt)
            except Exception:
                pass

    return changed


# ────────────────────────────────────────────
# 2. AI 사진 불일치 → 정산 보류(Hold)
# ────────────────────────────────────────────
def apply_settlement_hold(order_id: int, score: int, reasoning: str):
    """
    AI 사진 Match Score < 75 → 해당 건 정산 즉시 Hold.
    배차 우선순위 페널티 플래그도 함께 설정.
    """
    from data.db import update_order
    from utils.notifications import notify_settlement_hold
    from data.db import _load

    data = _load()
    order = next((o for o in data.get("orders", []) if o["id"] == order_id), None)
    if not order:
        return

    if not order.get("settlement_hold"):
        update_order(order_id, {
            "settlement_hold": True,
            "settlement_hold_reason": f"AI 사진 불일치 — Match Score {score}점 (기준 75점)",
            "settlement_hold_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dispatch_priority_penalty": True,  # 배차 우선순위 강제 하향
        })
        # 카카오 알림 — 대표 + 매니저
        try:
            notify_settlement_hold(order=order, score=score, reasoning=reasoning)
        except Exception:
            pass


# ────────────────────────────────────────────
# 3. 사진 미업로드 → 배차 제외 플래그
# ────────────────────────────────────────────
def get_photo_blocked_driver_ids(orders: list) -> set:
    """
    진행 중인 주문에 사진이 없는 기사 ID 집합 반환.
    → 배차 알고리즘에서 자동 제외용.
    """
    blocked = set()
    for o in orders:
        if o.get("status") != "in_progress":
            continue
        driver_id = o.get("driver_id")
        if not driver_id:
            continue
        # 작업 전 사진 미업로드 → 배차 제외
        if not o.get("photo_before"):
            blocked.add(driver_id)
    return blocked


def get_hold_penalty_driver_ids(orders: list) -> set:
    """
    정산 보류 또는 배차 우선순위 페널티인 기사 ID 집합 반환.
    → 우선순위 점수 -30 페널티용.
    """
    penalty_ids = set()
    for o in orders:
        if o.get("dispatch_priority_penalty") or o.get("settlement_hold"):
            driver_id = o.get("driver_id")
            if driver_id:
                penalty_ids.add(driver_id)
    return penalty_ids


# ────────────────────────────────────────────
# 4. 자동 점검 요약 (메인 대시보드 전용)
# ────────────────────────────────────────────
def run_auto_checks(orders: list, settings: dict) -> dict:
    """
    모든 자동 점검 실행 후 결과 요약 반환.
    Returns: {
        "delay_applied": [order_id, ...],
        "photo_blocked": {driver_id, ...},
        "hold_penalty": {driver_id, ...},
        "hold_orders": [order with settlement_hold, ...],
    }
    """
    delay_applied = check_and_apply_delay_penalty(orders, settings)
    photo_blocked = get_photo_blocked_driver_ids(orders)
    hold_penalty = get_hold_penalty_driver_ids(orders)
    hold_orders = [o for o in orders if o.get("settlement_hold")]
    return {
        "delay_applied": delay_applied,
        "photo_blocked": photo_blocked,
        "hold_penalty": hold_penalty,
        "hold_orders": hold_orders,
    }
