import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent
DB_FILE = DATA_DIR / "soonssak_db.json"


def _load():
    if not DB_FILE.exists():
        return _default_db()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _migrate(data)
    except Exception:
        return _default_db()


def _migrate(data):
    for o in data.get("orders", []):
        o.setdefault("work_type", "수거")
        o.setdefault("job_allowance", 0)
        o.setdefault("delay_flag", False)
        o.setdefault("arbitrary_fee_flag", False)
        o.setdefault("photo_before", None)
        o.setdefault("photo_after", None)
        o.setdefault("photo_cleanup", None)
        o.setdefault("penalty_amount", 0)
        o.setdefault("satisfaction_score", None)
        o.setdefault("satisfaction_comment", "")
        # 출발/도착 추적 필드
        o.setdefault("departed_at", None)
        o.setdefault("arrived_at", None)
        o.setdefault("gps_lat", None)
        o.setdefault("gps_lng", None)
        o.setdefault("departure_delay_minutes", None)
        o.setdefault("eta", None)
        o.setdefault("expected_travel_min", None)
        o.setdefault("actual_travel_min", None)
        o.setdefault("travel_dist_km", None)
        o.setdefault("travel_source", None)
        o.setdefault("photo_before_at", None)
        # CS / 권한 분리 필드
        o.setdefault("cs_confirmed", False)
        o.setdefault("cs_memo", "")
        o.setdefault("cs_items", [])
        o.setdefault("cs_photo", None)
        o.setdefault("manager_closed", False)
        o.setdefault("field_report", None)
        o.setdefault("settlement_ready", False)
        # 철거 전용 필드
        o.setdefault("demolition_area", None)
        o.setdefault("has_ladder_car", False)
        o.setdefault("waste_types", [])
        o.setdefault("has_asbestos", False)
        o.setdefault("floor_number", None)
        o.setdefault("has_elevator", True)
        o.setdefault("demolition_scope", "")
        o.setdefault("team_size", 1)
        o.setdefault("second_driver_id", None)
        o.setdefault("manager_quote", None)
        o.setdefault("manager_quote_confirmed", False)
        o.setdefault("manager_quote_sent", False)
        o.setdefault("driver_allowance_amount", None)
        o.setdefault("manager_incentive", None)
        # AI 사진 검증 필드
        o.setdefault("estimate_photo_path", None)      # 매니저 견적 현장 사진 (단일, 구버전 호환)
        o.setdefault("estimate_photos", [])            # 매니저 현장 사진 목록 (3장 이상 필수)
        o.setdefault("completion_photo_path", None)    # 기사 완료 사진
        o.setdefault("photo_match_score", None)        # AI 일치 점수 0~100
        o.setdefault("photo_match_flagged", False)     # True이면 대표 알림
        o.setdefault("photo_match_reasoning", "")      # AI 판단 근거
        o.setdefault("photo_match_flags", [])          # AI 적발 사유 목록
        o.setdefault("photo_match_checked_at", None)   # 검증 시각
    for d in data.get("drivers", []):
        d.setdefault("driver_type", "직영")
        d.setdefault("monthly_jobs", 0)
        d.setdefault("collection_jobs", 0)
        d.setdefault("demolition_jobs", 0)
        d.setdefault("avg_satisfaction", None)
        d.setdefault("region", "본사")
        d.setdefault("specialty", "공통")            # '수거' | '철거' | '공통'
        d.setdefault("joined_at", None)              # 등록일시 (온보딩 판단용)
        # 세무 유형 필드
        d.setdefault("tax_type", "individual")       # 'individual' | 'business'
        d.setdefault("business_reg_no", "")          # 사업자등록번호
        d.setdefault("business_type", "")            # 업태
        d.setdefault("business_category", "")        # 종목
        d.setdefault("tax_invoice_requested", False) # 세금계산서 발행 요청 여부
    for o in data.get("orders", []):
        o.setdefault("region", "본사")
        o.setdefault("region_lead_source", None)
    for pl in data.get("phone_logs", []):
        pl.setdefault("region", None)
        pl.setdefault("manager_id", None)
        pl.setdefault("corporate_phone", None)
    data.setdefault("subcontractors", [])
    data.setdefault("subcontractor_jobs", [])
    data.setdefault("waiting_executors", [])
    data.setdefault("phone_logs", [])
    data.setdefault("satisfaction_surveys", [])
    data.setdefault("manager_settlements", [])
    data.setdefault("ace_bonuses", [])
    data.setdefault("monthly_allowances", {})
    data.setdefault("journey_notifications", [])
    data.setdefault("reviews", [])
    data.setdefault("crm_followups", [])
    data.setdefault("blacklist", [])
    # 기사 자기주도형 스케줄 관리
    data.setdefault("driver_schedules", [])  # 날짜별 차단 슬롯
    data.setdefault("schedule_logs", [])     # 이력 (무단 이탈 방지)
    if "settings" in data:
        data["settings"].setdefault("vat_rate", 0.10)
        data["settings"].setdefault("withholding_tax_rate", 0.033)
        data["settings"].setdefault("rest_hours_between_jobs", 1)
    for o in data.get("orders", []):
        o.setdefault("settlement_overrun_notified", False)
        # 무인 자동 페널티 필드
        o.setdefault("delay_auto_applied", False)
        o.setdefault("delay_overdue_min", 0)
        # 정산 보류 필드
        o.setdefault("settlement_hold", False)
        o.setdefault("settlement_hold_reason", "")
        o.setdefault("settlement_hold_at", None)
        o.setdefault("settlement_hold_released", False)
        o.setdefault("settlement_hold_released_by", "")
        # 배차 우선순위 페널티
        o.setdefault("dispatch_priority_penalty", False)
        o.setdefault("notif_reserved", False)
        o.setdefault("notif_dispatched", False)
        o.setdefault("notif_geofence", False)
        o.setdefault("tracking_token", None)
        o.setdefault("notif_eta", False)
        o.setdefault("notif_completed", False)
        o.setdefault("notif_review_sent", False)
        o.setdefault("notif_review_reminded", False)
        o.setdefault("notif_crm_scheduled", False)
        o.setdefault("review_written", False)
        o.setdefault("coupon_issued", False)
    if "settings" in data:
        s = data["settings"]
        s.setdefault("demolition_incentive_min", 50000)
        s.setdefault("demolition_incentive_max", 100000)
        s.setdefault("manager_base_cost", 1500000)
        s.setdefault("direct_team_full_cost", 1500000)
        s.setdefault("direct_team_half_cost", 750000)
        s.setdefault("direct_team_threshold", 40)
        s.setdefault("active_driver_threshold", 60)
        s.setdefault("retention_days", 7)
        s.setdefault("retention_rate", 0.10)
        s.setdefault("ad_cost_rate", 0.10)
        # 멀티 지역 설정
        # 자동 페널티 설정
        s.setdefault("auto_penalty_amount", 20000)
        s.setdefault("delay_threshold_min", 30)
        # 카카오 알림 설정
        s.setdefault("kakao_webhook_url", "")
        s.setdefault("owner_phone", "")
        s.setdefault("app_base_url", "")
        # 텔레그램 알림 설정
        s.setdefault("telegram_bot_token", "")
        s.setdefault("telegram_chat_id", "")
        # 알림 로그
        data.setdefault("notification_log", [])
        s.setdefault("regions", ["본사", "세종"])
        s.setdefault("managers", [
            {"id": 1, "name": "김대표", "region": "본사",
             "corporate_phone": "010-0000-0001", "role": "대표"},
            {"id": 2, "name": "이세종", "region": "세종",
             "corporate_phone": "010-0000-0002", "role": "지역매니저"},
        ])
        s.setdefault("region_labels", {
            "본사": {
                "manager_base_cost": "운영비",
                "region_activity": "지역 활동비",
            },
            "세종": {
                "manager_base_cost": "지역 활동비",
                "region_activity": "세종 지역 활동비",
            },
        })
    return data


def _save(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _default_db():
    return {
        "drivers": [
            {"id": 1, "name": "김철수", "phone": "010-1234-5678", "rating": 4.8,
             "available": True, "available_from": "08:00", "available_to": "20:00",
             "completed_jobs": 142, "license": "1종보통", "driver_type": "직영",
             "monthly_jobs": 65, "collection_jobs": 50, "demolition_jobs": 15,
             "avg_satisfaction": 4.7},
            {"id": 2, "name": "이영희", "phone": "010-2345-6789", "rating": 4.6,
             "available": True, "available_from": "09:00", "available_to": "18:00",
             "completed_jobs": 98, "license": "1종보통", "driver_type": "직영",
             "monthly_jobs": 38, "collection_jobs": 35, "demolition_jobs": 3,
             "avg_satisfaction": 4.5},
            {"id": 3, "name": "박민준", "phone": "010-3456-7890", "rating": 4.9,
             "available": False, "available_from": "10:00", "available_to": "22:00",
             "completed_jobs": 215, "license": "2종보통", "driver_type": "직영",
             "monthly_jobs": 72, "collection_jobs": 40, "demolition_jobs": 32,
             "avg_satisfaction": 4.9},
            {"id": 4, "name": "최지은", "phone": "010-4567-8901", "rating": 4.7,
             "available": True, "available_from": "07:00", "available_to": "19:00",
             "completed_jobs": 167, "license": "1종보통", "driver_type": "직영",
             "monthly_jobs": 45, "collection_jobs": 38, "demolition_jobs": 7,
             "avg_satisfaction": 4.6},
            {"id": 5, "name": "정우성", "phone": "010-5678-9012", "rating": 4.5,
             "available": True, "available_from": "08:00", "available_to": "17:00",
             "completed_jobs": 88, "license": "2종보통", "driver_type": "외부",
             "monthly_jobs": 22, "collection_jobs": 20, "demolition_jobs": 2,
             "avg_satisfaction": 4.3},
        ],
        "orders": [
            {"id": 1, "customer": "홍길동", "customer_phone": "010-9999-0001",
             "pickup": "서울 강남구 역삼동 123", "destination": "서울 서초구 반포동 456",
             "scheduled_time": "2026-04-01 10:00", "driver_id": 1,
             "status": "completed", "base_fee": 50000, "extra_fee": 0,
             "extra_fee_status": None, "payment_confirmed": True, "created_at": "2026-04-01 08:00",
             "work_type": "수거", "job_allowance": 30000, "delay_flag": False,
             "arbitrary_fee_flag": False, "photo_before": "ok", "photo_after": "ok",
             "photo_cleanup": "ok", "penalty_amount": 0,
             "satisfaction_score": 5, "satisfaction_comment": "빠르고 친절했어요"},
            {"id": 2, "customer": "김영수", "customer_phone": "010-9999-0002",
             "pickup": "서울 마포구 합정동 789", "destination": "경기 성남시 분당구 정자동 101",
             "scheduled_time": "2026-04-01 14:00", "driver_id": 2,
             "status": "in_progress", "base_fee": 80000, "extra_fee": 20000,
             "extra_fee_status": "pending", "payment_confirmed": False, "created_at": "2026-04-01 09:00",
             "work_type": "철거", "job_allowance": 80000, "delay_flag": True,
             "arbitrary_fee_flag": False, "photo_before": "ok", "photo_after": None,
             "photo_cleanup": None, "penalty_amount": 10000,
             "satisfaction_score": None, "satisfaction_comment": ""},
            {"id": 3, "customer": "이수진", "customer_phone": "010-9999-0003",
             "pickup": "서울 송파구 잠실동 202", "destination": "서울 강동구 천호동 303",
             "scheduled_time": "2026-04-01 16:00", "driver_id": None,
             "status": "pending", "base_fee": 45000, "extra_fee": 0,
             "extra_fee_status": None, "payment_confirmed": False, "created_at": "2026-04-01 10:00",
             "work_type": "수거", "job_allowance": 0, "delay_flag": False,
             "arbitrary_fee_flag": False, "photo_before": None, "photo_after": None,
             "photo_cleanup": None, "penalty_amount": 0,
             "satisfaction_score": None, "satisfaction_comment": ""},
            {"id": 4, "customer": "박동현", "customer_phone": "010-9999-0004",
             "pickup": "인천 연수구 송도동 404", "destination": "서울 중구 명동 505",
             "scheduled_time": "2026-04-01 09:00", "driver_id": 4,
             "status": "completed", "base_fee": 120000, "extra_fee": 30000,
             "extra_fee_status": "approved", "payment_confirmed": True, "created_at": "2026-03-31 17:00",
             "work_type": "철거", "job_allowance": 120000, "delay_flag": False,
             "arbitrary_fee_flag": False, "photo_before": "ok", "photo_after": "ok",
             "photo_cleanup": "ok", "penalty_amount": 0,
             "satisfaction_score": 4, "satisfaction_comment": "만족합니다"},
        ],
        "subcontractors": [
            {"id": 1, "name": "한국이삿짐센터", "phone": "010-7777-1111",
             "specialty": "철거", "unit_price_min": 80000, "unit_price_max": 150000,
             "region": "서울/경기", "rating": 4.5, "avg_satisfaction": 4.4,
             "active": True, "registered_at": "2026-01-15"},
            {"id": 2, "name": "퀵서비스파트너스", "phone": "010-8888-2222",
             "specialty": "수거", "unit_price_min": 25000, "unit_price_max": 35000,
             "region": "인천/경기", "rating": 4.2, "avg_satisfaction": 4.1,
             "active": True, "registered_at": "2026-02-01"},
        ],
        "subcontractor_jobs": [
            {"id": 1, "subcontractor_id": 1, "order_id": 4,
             "total_amount": 120000, "retention_amount": 12000,
             "net_amount": 108000, "status": "retention_pending",
             "created_at": "2026-04-01 10:00",
             "retention_due_date": "2026-04-08 10:00",
             "photo_before": "ok", "photo_after": "ok", "photo_cleanup": None,
             "claim_reported": False},
        ],
        "waiting_executors": [
            {"id": 1, "name": "홍준표", "phone": "010-6666-3333",
             "specialty": "철거", "region": "서울", "status": "대기중",
             "registered_at": "2026-04-01 09:00", "note": "경력 5년, 강남구 전문"},
        ],
        "phone_logs": [],
        "satisfaction_surveys": [],
        "driver_logs": [],
        "notifications": [],
        "tax_records": [],
        "manager_settlements": [],
        "ace_bonuses": [],
        "monthly_allowances": {},
        "settings": {
            "driver_ratio": 0.70,
            "cs_ratio": 0.40,
            "success_fee_ratio": 0.05,
            "withholding_tax_rate": 0.033,
            "dispatch_fee": 30000,
            "kakao_api_key": "",
            "grenter_api_key": "",
            "demolition_incentive_min": 50000,
            "demolition_incentive_max": 100000,
            "manager_base_cost": 1500000,
            "direct_team_full_cost": 1500000,
            "direct_team_half_cost": 750000,
            "direct_team_threshold": 40,
            "active_driver_threshold": 60,
            "retention_days": 7,
            "retention_rate": 0.10,
            "ad_cost_rate": 0.10,
        }
    }


def get_all():
    return _load()


def get_drivers():
    return _load()["drivers"]


def get_orders():
    return _load()["orders"]


def get_settings():
    return _load()["settings"]


def get_driver_logs():
    return _load()["driver_logs"]


def get_notifications():
    return _load()["notifications"]


def get_tax_records():
    return _load()["tax_records"]


def get_manager_settlements():
    return _load()["manager_settlements"]


def get_ace_bonuses():
    return _load()["ace_bonuses"]


def get_monthly_allowances():
    return _load()["monthly_allowances"]


def get_subcontractors():
    return _load()["subcontractors"]


def get_subcontractor_jobs():
    return _load()["subcontractor_jobs"]


def get_waiting_executors():
    return _load()["waiting_executors"]


def get_phone_logs():
    return _load()["phone_logs"]


def get_satisfaction_surveys():
    return _load()["satisfaction_surveys"]


def get_blacklist():
    return _load().get("blacklist", [])


def add_blacklist(entry: dict):
    """entry: {phone, customer_name, reason, added_by, created_at}"""
    db = _load()
    db.setdefault("blacklist", [])
    # 중복 방지 (같은 번호)
    phone = entry.get("phone", "").replace("-", "").replace(" ", "")
    existing = [b for b in db["blacklist"]
                if b.get("phone", "").replace("-", "").replace(" ", "") == phone]
    if not existing:
        entry["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db["blacklist"].append(entry)
        _save(db)
        return True
    return False


def remove_blacklist_entry(phone: str):
    db = _load()
    phone_clean = phone.replace("-", "").replace(" ", "")
    db["blacklist"] = [b for b in db.get("blacklist", [])
                       if b.get("phone", "").replace("-", "").replace(" ", "") != phone_clean]
    _save(db)


def is_blacklisted(phone: str) -> dict | None:
    """전화번호가 블랙리스트에 있으면 해당 entry 반환, 없으면 None"""
    if not phone:
        return None
    phone_clean = phone.replace("-", "").replace(" ", "")
    for b in _load().get("blacklist", []):
        if b.get("phone", "").replace("-", "").replace(" ", "") == phone_clean:
            return b
    return None


def save_driver(driver):
    db = _load()
    for i, d in enumerate(db["drivers"]):
        if d["id"] == driver["id"]:
            db["drivers"][i] = driver
            _save(db)
            return
    db["drivers"].append(driver)
    _save(db)


def add_order(order):
    db = _load()
    max_id = max((o["id"] for o in db["orders"]), default=0)
    order["id"] = max_id + 1
    order["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    order.setdefault("work_type", "수거")
    order.setdefault("job_allowance", 0)
    order.setdefault("delay_flag", False)
    order.setdefault("arbitrary_fee_flag", False)
    order.setdefault("photo_before", None)
    order.setdefault("photo_after", None)
    order.setdefault("photo_cleanup", None)
    order.setdefault("penalty_amount", 0)
    order.setdefault("satisfaction_score", None)
    order.setdefault("satisfaction_comment", "")
    db["orders"].append(order)
    _save(db)
    return order["id"]


def update_order(order_id, updates):
    db = _load()
    for i, o in enumerate(db["orders"]):
        if o["id"] == order_id:
            db["orders"][i].update(updates)
            _save(db)
            return True
    return False


def add_driver_log(log):
    db = _load()
    log["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db["driver_logs"].append(log)
    _save(db)


def add_notification(notif):
    db = _load()
    notif["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ACCOUNT_NOTICE = "\n\n⚠️ 본사 공식 계좌 외 기사 직접 송금 시 서비스 보장 불가."
    notif["message"] = notif.get("message", "") + ACCOUNT_NOTICE
    db["notifications"].append(notif)
    _save(db)


def add_tax_record(record):
    db = _load()
    max_id = max((r.get("id", 0) for r in db["tax_records"]), default=0)
    record["id"] = max_id + 1
    record["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db["tax_records"].append(record)
    _save(db)


def save_settings(settings):
    db = _load()
    db["settings"] = settings
    _save(db)


def add_ace_bonus(bonus):
    db = _load()
    bonus["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db["ace_bonuses"].append(bonus)
    _save(db)


def save_monthly_allowances(allowances):
    db = _load()
    db["monthly_allowances"] = allowances
    _save(db)


def add_manager_settlement(record):
    db = _load()
    record["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db["manager_settlements"].append(record)
    _save(db)


def save_subcontractor(sc):
    db = _load()
    for i, s in enumerate(db["subcontractors"]):
        if s["id"] == sc["id"]:
            db["subcontractors"][i] = sc
            _save(db)
            return
    db["subcontractors"].append(sc)
    _save(db)


def add_subcontractor_job(job):
    db = _load()
    max_id = max((j["id"] for j in db["subcontractor_jobs"]), default=0)
    job["id"] = max_id + 1
    job["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    settings = db["settings"]
    retention_days = settings.get("retention_days", 7)
    due = datetime.now() + timedelta(days=retention_days)
    job["retention_due_date"] = due.strftime("%Y-%m-%d %H:%M")
    db["subcontractor_jobs"].append(job)
    _save(db)
    return job["id"]


def update_subcontractor_job(job_id, updates):
    db = _load()
    for i, j in enumerate(db["subcontractor_jobs"]):
        if j["id"] == job_id:
            db["subcontractor_jobs"][i].update(updates)
            _save(db)
            return True
    return False


def add_waiting_executor(executor):
    db = _load()
    max_id = max((e["id"] for e in db["waiting_executors"]), default=0)
    executor["id"] = max_id + 1
    executor["registered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    executor.setdefault("status", "대기중")
    db["waiting_executors"].append(executor)
    _save(db)
    return executor["id"]


def update_waiting_executor(exec_id, updates):
    db = _load()
    for i, e in enumerate(db["waiting_executors"]):
        if e["id"] == exec_id:
            db["waiting_executors"][i].update(updates)
            _save(db)
            return True
    return False


def save_phone_logs(logs):
    db = _load()
    db["phone_logs"] = logs
    _save(db)


def add_satisfaction_survey(survey):
    db = _load()
    survey["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db["satisfaction_surveys"].append(survey)
    _save(db)
    _update_driver_satisfaction(db)
    _save(db)


def _update_driver_satisfaction(db):
    scores = {}
    for s in db["satisfaction_surveys"]:
        did = s.get("driver_id")
        if did and s.get("score"):
            if did not in scores:
                scores[did] = []
            scores[did].append(s["score"])
    for d in db["drivers"]:
        if d["id"] in scores:
            d["avg_satisfaction"] = round(sum(scores[d["id"]]) / len(scores[d["id"]]), 1)


def next_driver_id():
    drivers = get_drivers()
    return max((d["id"] for d in drivers), default=0) + 1


def next_subcontractor_id():
    scs = get_subcontractors()
    return max((s["id"] for s in scs), default=0) + 1


def get_order_by_id(order_id):
    for o in get_orders():
        if o["id"] == order_id:
            return o
    return None


def get_driver_by_id(driver_id):
    for d in get_drivers():
        if d["id"] == driver_id:
            return d
    return None


def get_subcontractor_by_id(sc_id):
    for s in get_subcontractors():
        if s["id"] == sc_id:
            return s
    return None


def get_journey_notifications():
    return _load().get("journey_notifications", [])


def get_reviews():
    return _load().get("reviews", [])


def get_crm_followups():
    return _load().get("crm_followups", [])


def add_journey_notification(notif):
    db = _load()
    notif["sent_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.setdefault("journey_notifications", []).append(notif)
    _save(db)


def add_review(review):
    db = _load()
    review["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.setdefault("reviews", []).append(review)
    for o in db["orders"]:
        if o["id"] == review.get("order_id"):
            o["review_written"] = True
            o["satisfaction_score"] = review.get("score")
            o["satisfaction_comment"] = review.get("comment", "")
            if review.get("coupon_issued"):
                o["coupon_issued"] = True
            break
    _save(db)


def add_crm_followup(followup):
    db = _load()
    followup["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    followup.setdefault("sent", False)
    db.setdefault("crm_followups", []).append(followup)
    _save(db)


def update_crm_followup(idx, updates):
    db = _load()
    followups = db.get("crm_followups", [])
    if 0 <= idx < len(followups):
        followups[idx].update(updates)
        _save(db)


def mark_notification_sent(order_id, notif_field):
    db = _load()
    for o in db["orders"]:
        if o["id"] == order_id:
            o[notif_field] = True
            break
    _save(db)


# ──────────────── 기사 스케줄 관리 ────────────────

def get_driver_schedules() -> list:
    """모든 기사 스케줄 차단 목록 반환"""
    return _load().get("driver_schedules", [])


def get_schedule_logs() -> list:
    """스케줄 변경 이력 전체 반환"""
    return _load().get("schedule_logs", [])


def _next_schedule_id(db: dict) -> int:
    items = db.get("driver_schedules", [])
    return max((s["id"] for s in items), default=0) + 1


def add_schedule_block(block: dict, role: str = "executor") -> int:
    """
    스케줄 차단 추가.
    block 필드: driver_id, date, is_all_day, start_hour(opt), end_hour(opt), reason
    Returns: 생성된 block id
    """
    db = _load()
    block_id = _next_schedule_id(db)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = {
        **block,
        "id": block_id,
        "created_at": now_str,
        "created_by_role": role,
    }
    db.setdefault("driver_schedules", []).append(block)
    # 이력 기록
    db.setdefault("schedule_logs", []).append({
        "action": "block_added",
        "block_id": block_id,
        "driver_id": block.get("driver_id"),
        "date": block.get("date"),
        "is_all_day": block.get("is_all_day"),
        "start_hour": block.get("start_hour"),
        "end_hour": block.get("end_hour"),
        "reason": block.get("reason", ""),
        "role": role,
        "logged_at": now_str,
    })
    _save(db)
    return block_id


def remove_schedule_block(block_id: int, role: str = "executor"):
    """스케줄 차단 삭제 + 이력 기록"""
    db = _load()
    schedules = db.get("driver_schedules", [])
    original = next((s for s in schedules if s["id"] == block_id), None)
    db["driver_schedules"] = [s for s in schedules if s["id"] != block_id]
    if original:
        db.setdefault("schedule_logs", []).append({
            "action": "block_removed",
            "block_id": block_id,
            "driver_id": original.get("driver_id"),
            "date": original.get("date"),
            "is_all_day": original.get("is_all_day"),
            "start_hour": original.get("start_hour"),
            "end_hour": original.get("end_hour"),
            "reason": original.get("reason", ""),
            "role": role,
            "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    _save(db)


# ═══════════════════════════════════════════════════════════════
#  비품 보충 신청 (푸시 알림 없음 — Owner 대시보드 배지만)
# ═══════════════════════════════════════════════════════════════

def get_supply_requests(unresolved_only: bool = False) -> list:
    """비품 보충 신청 목록 조회."""
    db = _load()
    reqs = db.get("supply_requests", [])
    if unresolved_only:
        reqs = [r for r in reqs if not r.get("resolved", False)]
    return list(reversed(reqs))


def add_supply_request(region: str, manager_label: str,
                        items: list, urgency: str = "일반") -> dict:
    """
    비품 보충 신청 DB 저장 (텔레그램 전송 없음).
    Owner 대시보드 '비품 관리' 탭의 숫자 배지로만 표시.
    """
    db = _load()
    db.setdefault("supply_requests", [])
    new_id = max((r["id"] for r in db["supply_requests"]), default=0) + 1
    req = {
        "id": new_id,
        "region": region,
        "manager_label": manager_label,
        "items": items,
        "urgency": urgency,
        "requested_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "resolved": False,
        "resolved_at": None,
        "resolved_note": "",
    }
    db["supply_requests"].append(req)
    _save(db)
    return req


def resolve_supply_request(req_id: int, note: str = "") -> bool:
    """비품 신청 처리 완료 표시."""
    db = _load()
    found = False
    for r in db.get("supply_requests", []):
        if r["id"] == req_id:
            r["resolved"] = True
            r["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            r["resolved_note"] = note
            found = True
    if found:
        _save(db)
    return found


# ═══════════════════════════════════════════════════════════════
#  기사 출발 트립 추적 — GPS 이력 / 지오펜싱 / 효율 분석
# ═══════════════════════════════════════════════════════════════

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 GPS 좌표 간 직선거리(m) — 내부 전용 (utils.maps 순환 import 방지)"""
    import math
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def start_trip_tracking(
    order_id: int, driver_id: int, driver_name: str,
    origin_lat: float, origin_lng: float,
    dest_lat, dest_lng,
    dest_address: str, eta_str: str,
    expected_min: int, tracking_token: str,
) -> dict:
    """출발 버튼 클릭 시 트립 기록 시작. 기존 레코드 있으면 덮어씀."""
    db = _load()
    db.setdefault("trips", [])
    db["trips"] = [t for t in db["trips"] if t["order_id"] != order_id]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trip = {
        "order_id": order_id,
        "driver_id": driver_id,
        "driver_name": driver_name,
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
        "dest_lat": dest_lat,
        "dest_lng": dest_lng,
        "dest_address": dest_address,
        "eta_str": eta_str,
        "expected_min": expected_min,
        "tracking_token": tracking_token,
        "current_lat": origin_lat,
        "current_lng": origin_lng,
        "current_ts": now_str,
        "departed_at": now_str,
        "arrived_at": None,
        "actual_min": None,
        "geofence_triggered": False,
        "geofence_triggered_at": None,
        "status": "in_progress",
        "gps_history": [
            {"lat": origin_lat, "lng": origin_lng, "ts": now_str}
        ],
    }
    db["trips"].append(trip)
    _save(db)
    return trip


def update_trip_gps(order_id: int, lat: float, lng: float) -> dict:
    """
    기사 GPS 위치 업데이트 + 지오펜싱 체크.
    목적지 100m 이내 진입 시 geofence_triggered = True (최초 1회).
    반환: {"geofence_triggered": bool, "dist_m": float | None}
    """
    db = _load()
    trip = next((t for t in db.get("trips", []) if t["order_id"] == order_id), None)
    if not trip or trip.get("status") == "arrived":
        return {"geofence_triggered": False, "dist_m": None}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trip["current_lat"] = lat
    trip["current_lng"] = lng
    trip["current_ts"] = now_str
    history = trip.setdefault("gps_history", [])
    history.append({"lat": lat, "lng": lng, "ts": now_str})
    if len(history) > 200:
        trip["gps_history"] = history[-200:]

    geofence_triggered = False
    dist_m = None
    if (trip.get("dest_lat") is not None
            and trip.get("dest_lng") is not None
            and not trip.get("geofence_triggered")):
        dist_m = _haversine_m(lat, lng, trip["dest_lat"], trip["dest_lng"])
        if dist_m <= 100:
            trip["geofence_triggered"] = True
            trip["geofence_triggered_at"] = now_str
            geofence_triggered = True

    _save(db)
    return {"geofence_triggered": geofence_triggered, "dist_m": dist_m}


def complete_trip_tracking(
    order_id: int, final_lat: float, final_lng: float, actual_min: int
) -> None:
    """도착 버튼 클릭 시 트립 완료 처리."""
    db = _load()
    for t in db.get("trips", []):
        if t["order_id"] == order_id:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            t["arrived_at"] = now_str
            t["actual_min"] = actual_min
            t["current_lat"] = final_lat
            t["current_lng"] = final_lng
            t["status"] = "arrived"
            t.setdefault("gps_history", []).append(
                {"lat": final_lat, "lng": final_lng, "ts": now_str}
            )
            break
    _save(db)


def get_trip_data(order_id: int) -> dict | None:
    """추적 페이지용 — 특정 주문의 트립 데이터 조회."""
    db = _load()
    return next((t for t in db.get("trips", []) if t["order_id"] == order_id), None)


def get_trip_history(driver_id: int | None = None) -> list:
    """기사 효율 분석 대시보드용 — 완료된 트립 전체 목록."""
    db = _load()
    trips = [t for t in db.get("trips", []) if t.get("arrived_at")]
    if driver_id is not None:
        trips = [t for t in trips if t.get("driver_id") == driver_id]
    return list(reversed(trips))
