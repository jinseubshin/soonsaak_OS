"""
순삭 OS — 기사 자기주도형 스케줄 관리 유틸리티

데이터 구조 (driver_schedules 컬렉션):
  {
    "id": <int>,
    "driver_id": <int>,
    "date": "YYYY-MM-DD",
    "is_all_day": <bool>,       # True: 전일 휴무
    "start_hour": <int|None>,   # 부분 차단 시작 (0-23)
    "end_hour": <int|None>,     # 부분 차단 종료 (0-23, 포함)
    "reason": <str>,
    "created_at": <str>,
    "created_by_role": <str>,
  }

Lead Time 규칙:
  - 전일 휴무(All Day): 대상일 24시간 전까지 설정 가능
  - 부분 시간 차단: 대상일 12시간 전까지 설정 가능
"""
from datetime import datetime, timedelta
from typing import Optional

ALLDAY_LEADTIME_H  = 24   # 전일 휴무 최소 사전 설정 시간
PARTIAL_LEADTIME_H = 12   # 부분 차단 최소 사전 설정 시간


def _now() -> datetime:
    return datetime.now()


def can_set_block(target_date: str, is_all_day: bool, start_hour: Optional[int] = None) -> tuple[bool, str]:
    """
    Lead Time 규칙 검증.
    Returns (ok: bool, message: str)
    """
    if is_all_day:
        cutoff = datetime.strptime(target_date, "%Y-%m-%d")
        required_before = cutoff - timedelta(hours=ALLDAY_LEADTIME_H)
        if _now() >= required_before:
            return False, (
                f"⚠️ 전일 휴무는 {ALLDAY_LEADTIME_H}시간 전까지만 설정 가능합니다.\n\n"
                "긴급 휴무는 담당 매니저에게 직접 문의하세요."
            )
    else:
        block_start_h = start_hour if start_hour is not None else 0
        cutoff = datetime.strptime(target_date, "%Y-%m-%d").replace(hour=block_start_h)
        required_before = cutoff - timedelta(hours=PARTIAL_LEADTIME_H)
        if _now() >= required_before:
            return False, (
                f"⚠️ 부분 시간 차단은 해당 시간 {PARTIAL_LEADTIME_H}시간 전까지만 설정 가능합니다.\n\n"
                "긴급 휴무는 담당 매니저에게 직접 문의하세요."
            )
    return True, ""


def is_driver_blocked_at(schedules: list, driver_id: int, dt: datetime) -> bool:
    """
    특정 시점(dt)에 기사가 차단(Off)되어 있으면 True.
    """
    date_str = dt.strftime("%Y-%m-%d")
    hour = dt.hour
    for s in schedules:
        if s.get("driver_id") != driver_id:
            continue
        if s.get("date") != date_str:
            continue
        if s.get("is_all_day"):
            return True
        sh = s.get("start_hour")
        eh = s.get("end_hour")
        if sh is not None and eh is not None:
            if sh <= hour <= eh:
                return True
    return False


def get_driver_blocks_for_date(schedules: list, driver_id: int, date_str: str) -> list:
    """특정 기사의 특정 날짜 차단 목록 반환"""
    return [
        s for s in schedules
        if s.get("driver_id") == driver_id and s.get("date") == date_str
    ]


def get_driver_active_blocks(schedules: list, driver_id: int) -> list:
    """오늘 이후 미래 차단 목록 반환"""
    today = _now().strftime("%Y-%m-%d")
    return [
        s for s in schedules
        if s.get("driver_id") == driver_id and s.get("date", "") >= today
    ]


def get_current_driver_status(schedules: list, driver: dict) -> dict:
    """
    현재 시각 기준 기사 상태 반환.
    Returns {"status": "영업중"|"휴무중", "reason": str, "until": str|None}
    """
    now = _now()
    date_str = now.strftime("%Y-%m-%d")
    hour = now.hour

    # 기본 available 플래그 체크
    if not driver.get("available", True):
        return {"status": "휴무중", "reason": "가용 상태 Off", "until": None}

    for s in schedules:
        if s.get("driver_id") != driver["id"]:
            continue
        if s.get("date") != date_str:
            continue
        if s.get("is_all_day"):
            return {"status": "휴무중", "reason": s.get("reason", "전일 휴무"), "until": "당일 종료"}
        sh = s.get("start_hour")
        eh = s.get("end_hour")
        if sh is not None and eh is not None and sh <= hour <= eh:
            return {
                "status": "휴무중",
                "reason": s.get("reason", "부분 차단"),
                "until": f"{eh+1:02d}:00 이후 영업 재개 예정"
            }

    return {"status": "영업중", "reason": "", "until": None}


def build_day_grid(schedules: list, driver_id: int, date_str: str, orders: list) -> list:
    """
    24시간 슬롯 그리드 생성.
    각 슬롯: {"hour": int, "blocked": bool, "has_order": bool, "order_id": int|None}
    """
    blocks = get_driver_blocks_for_date(schedules, driver_id, date_str)
    # 해당 날짜에 배정된 주문 시간대 추출
    assigned_hours = set()
    for o in orders:
        if o.get("driver_id") == driver_id and o.get("status") not in ("cancelled",):
            sched = o.get("scheduled_time", "")
            if sched.startswith(date_str):
                try:
                    h = int(sched[11:13])
                    assigned_hours.add(h)
                except Exception:
                    pass

    grid = []
    for h in range(6, 23):   # 06:00 ~ 22:00 표시
        is_blocked = False
        for b in blocks:
            if b.get("is_all_day"):
                is_blocked = True
                break
            sh = b.get("start_hour")
            eh = b.get("end_hour")
            if sh is not None and eh is not None and sh <= h <= eh:
                is_blocked = True
                break
        grid.append({
            "hour": h,
            "blocked": is_blocked,
            "has_order": h in assigned_hours,
        })
    return grid


def is_past_date(date_str: str) -> bool:
    today = _now().date()
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return d < today
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# 최소 가동 의무 검증
# 주당 최소 5일 풀타임(8시간 이상 가용) 가동 의무
# ──────────────────────────────────────────────────────────────────────────────

MIN_FULLDAY_DAYS_PER_WEEK = 5    # 주당 최소 영업일
FULLDAY_HOURS = 8                # 풀타임 기준 시간


def _driver_daily_available_hours(driver: dict, date_str: str, schedules: list) -> float:
    """
    특정 날짜 기사의 실제 가용 시간(시) 계산.
    가용 범위 = avail_from ~ avail_to, 여기서 차단된 시간 제거.
    """
    try:
        from_h = int(driver.get("available_from", "08:00").split(":")[0])
        to_h = int(driver.get("available_to", "20:00").split(":")[0])
    except Exception:
        from_h, to_h = 8, 20
    total_hours = max(0, to_h - from_h)

    day_blocks = get_driver_blocks_for_date(schedules, driver["id"], date_str)
    blocked_hours = 0
    for b in day_blocks:
        if b.get("is_all_day"):
            return 0.0   # 전일 휴무 → 가용 0시간
        sh = b.get("start_hour")
        eh = b.get("end_hour")
        if sh is not None and eh is not None:
            # driver 가용 범위와 교집합 계산
            overlap_start = max(sh, from_h)
            overlap_end = min(eh, to_h)
            if overlap_end > overlap_start:
                blocked_hours += overlap_end - overlap_start
    return max(0.0, total_hours - blocked_hours)


def _week_dates(ref_date) -> list:
    """ref_date가 속한 주(월~일) 날짜 리스트 반환"""
    from datetime import date as _d, timedelta as _td
    if isinstance(ref_date, str):
        ref_date = datetime.strptime(ref_date, "%Y-%m-%d").date()
    monday = ref_date - _td(days=ref_date.weekday())
    return [(monday + _td(days=i)).strftime("%Y-%m-%d") for i in range(7)]


def count_weekly_fullday_count(driver: dict, schedules: list, week_start_date=None) -> int:
    """
    해당 주 영업일(풀타임 ≥ 8h) 일수 반환.
    week_start_date=None 이면 오늘이 속한 주 사용.
    """
    if week_start_date is None:
        week_start_date = _now().date()
    dates = _week_dates(week_start_date)
    count = 0
    for d in dates:
        if _driver_daily_available_hours(driver, d, schedules) >= FULLDAY_HOURS:
            count += 1
    return count


def check_minimum_operation(
    driver: dict,
    schedules: list,
    new_block_date: str,
    new_is_all_day: bool,
    new_start_h: Optional[int],
    new_end_h: Optional[int],
) -> tuple[bool, str]:
    """
    새 차단을 추가했을 때 최소 가동 의무(주당 5일 풀타임) 위반 여부 확인.
    Returns (ok: bool, message: str)
    """
    # 새 블록이 속한 주의 현재 영업일 수 계산 (가상 블록 추가 후)
    dates = _week_dates(new_block_date)

    # 가상으로 블록 추가 후 해당 날짜 가용 시간 재계산
    try:
        from_h = int(driver.get("available_from", "08:00").split(":")[0])
        to_h = int(driver.get("available_to", "20:00").split(":")[0])
    except Exception:
        from_h, to_h = 8, 20
    total_hours = max(0, to_h - from_h)

    # 해당 날짜 기존 차단된 시간
    existing_blocks = get_driver_blocks_for_date(schedules, driver["id"], new_block_date)
    existing_blocked = 0
    for b in existing_blocks:
        if b.get("is_all_day"):
            existing_blocked = total_hours  # 이미 전일 차단
            break
        sh = b.get("start_hour")
        eh = b.get("end_hour")
        if sh is not None and eh is not None:
            existing_blocked += max(0, min(eh, to_h) - max(sh, from_h))

    # 새 블록 추가 후 차단 시간
    if new_is_all_day:
        new_blocked_total = total_hours
    else:
        sh = new_start_h or 0
        eh = new_end_h or 0
        new_blocked_total = existing_blocked + max(0, min(eh, to_h) - max(sh, from_h))

    new_available = max(0, total_hours - new_blocked_total)
    new_block_is_fullday = new_available >= FULLDAY_HOURS

    # 현재 주 영업일 수 (새 블록 없이)
    fullday_count = 0
    for d in dates:
        if d == new_block_date:
            # 원래 해당일 가용 시간으로 계산 (새 블록 미적용)
            orig_available = max(0, total_hours - existing_blocked)
            if orig_available >= FULLDAY_HOURS:
                fullday_count += 1
        else:
            if _driver_daily_available_hours(driver, d, schedules) >= FULLDAY_HOURS:
                fullday_count += 1

    # 새 블록 추가 후 해당 날짜가 풀타임에서 제외되면 전체 일수 감소
    orig_day_is_fullday = max(0, total_hours - existing_blocked) >= FULLDAY_HOURS
    if orig_day_is_fullday and not new_block_is_fullday:
        fullday_count -= 1   # 이 날이 풀타임 목록에서 빠짐

    if fullday_count < MIN_FULLDAY_DAYS_PER_WEEK:
        return False, (
            f"🚫 **의무 가동 시간 부족으로 스케줄 차단이 불가능합니다.**\n\n"
            f"이번 주 풀타임(8시간+) 영업일이 {fullday_count}일로, "
            f"최소 의무 기준 **{MIN_FULLDAY_DAYS_PER_WEEK}일**에 미달합니다.\n\n"
            "스케줄을 더 닫으려면 담당 매니저에게 사전 승인을 받으세요."
        )
    return True, ""


def get_monthly_block_count(schedules: list, driver_id: int, year_month: str) -> int:
    """
    특정 기사의 해당 월 총 차단 건수.
    year_month: 'YYYY-MM'
    """
    return sum(
        1 for s in schedules
        if s.get("driver_id") == driver_id
        and s.get("date", "").startswith(year_month)
    )
