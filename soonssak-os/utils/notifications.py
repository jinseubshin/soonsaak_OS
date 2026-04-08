"""
순삭 OS 알림 시스템 — v3 지역별 수신자 분리
─────────────────────────────────────────────────────────────────
[수신자 라우팅 원칙]
  • 일상 운영 알림 (지연/정산가 초과/리드/견적)
      → 해당 주문 지역의 담당 매니저 텔레그램만 전송
      → 세종 주문 → 매니저1(세종) 채널
      → 본사 주문 → 매니저2(본사) 채널
      → Owner 수신 없음 (무소음 모드)

  • 예외/긴급 알림 (AI 사기 감지 / 미등록 번호 / 정산보류 / 근태불량 / 사고 / 클레임)
      → Owner 텔레그램 즉시 전송

[법인폰 3대]
  설정키: owner_device_phone, mgr1_device_phone (세종), mgr2_device_phone (본사)
  텔레그램 수신: mgr1_telegram_chat_id (세종) / mgr2_telegram_chat_id (본사) 지역별 라우팅
─────────────────────────────────────────────────────────────────
"""
import os
import requests
from datetime import datetime
from typing import Optional


# ═══════════════════════════════════════════════════════════════
#  설정 로더
# ═══════════════════════════════════════════════════════════════

def _get_notif_settings() -> dict:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from data.db import get_settings
        s = get_settings()
        return {
            "webhook_url":   s.get("kakao_webhook_url", ""),
            "owner_phone":   s.get("owner_phone", ""),
            "app_url":       s.get("app_base_url", ""),
            "enabled":       bool(s.get("kakao_webhook_url", "")),
            # Owner 텔레그램 (긴급/예외 전용)
            "telegram_bot_token": s.get("telegram_bot_token", ""),
            "telegram_chat_id":   s.get("telegram_chat_id", ""),
            "telegram_enabled":   bool(
                s.get("telegram_bot_token", "") and s.get("telegram_chat_id", "")
            ),
            # 매니저1 (세종) 텔레그램 (일상 운영 알림)
            "mgr1_bot_token":  s.get("mgr1_telegram_bot_token", ""),
            "mgr1_chat_id":    s.get("mgr1_telegram_chat_id", ""),
            "mgr1_enabled":    bool(
                s.get("mgr1_telegram_bot_token", "") and s.get("mgr1_telegram_chat_id", "")
            ),
            # 매니저2 (본사) 텔레그램 (일상 운영 알림)
            "mgr2_bot_token":  s.get("mgr2_telegram_bot_token", ""),
            "mgr2_chat_id":    s.get("mgr2_telegram_chat_id", ""),
            "mgr2_enabled":    bool(
                s.get("mgr2_telegram_bot_token", "") and s.get("mgr2_telegram_chat_id", "")
            ),
            # 법인폰 번호
            "owner_device_phone": s.get("owner_device_phone", ""),
            "mgr1_device_phone":  s.get("mgr1_device_phone", ""),
            "mgr2_device_phone":  s.get("mgr2_device_phone", ""),
        }
    except Exception:
        return {
            "webhook_url": "", "owner_phone": "", "app_url": "", "enabled": False,
            "telegram_bot_token": "", "telegram_chat_id": "", "telegram_enabled": False,
            "mgr1_bot_token": "", "mgr1_chat_id": "", "mgr1_enabled": False,
            "mgr2_bot_token": "", "mgr2_chat_id": "", "mgr2_enabled": False,
            "owner_device_phone": "", "mgr1_device_phone": "", "mgr2_device_phone": "",
        }


def _build_order_deeplink(app_url: str, order_id: int) -> str:
    if not app_url:
        return ""
    return f"{app_url.rstrip('/')}/배차_스케줄링?order_id={order_id}"


# ═══════════════════════════════════════════════════════════════
#  내부 전송 함수
# ═══════════════════════════════════════════════════════════════

def _raw_telegram(bot_token: str, chat_id: str, text: str) -> dict:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": False},
            timeout=8,
        )
        data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
        ok = resp.status_code == 200 and data.get("ok", False)
        return {"success": ok, "status_code": resp.status_code,
                "error": data.get("description") if not ok else None}
    except requests.exceptions.Timeout:
        return {"success": False, "status_code": None, "error": "텔레그램 타임아웃 (8초)"}
    except Exception as e:
        return {"success": False, "status_code": None, "error": str(e)}


def _send_telegram(message: str, order_id: Optional[int] = None) -> dict:
    """[Owner 전용] 긴급/예외 상황 텔레그램 전송."""
    cfg = _get_notif_settings()
    if not cfg["telegram_enabled"]:
        return {"success": False, "status_code": None, "error": "Owner 텔레그램 미설정"}
    full = message
    if order_id is not None and cfg.get("app_url"):
        full += f"\n\n🔗 [OS 상세페이지 바로가기]({_build_order_deeplink(cfg['app_url'], order_id)})"
    return _raw_telegram(cfg["telegram_bot_token"], cfg["telegram_chat_id"], full)


def _send_telegram_manager(message: str, order_id: Optional[int] = None,
                            region: str = "전체") -> dict:
    """
    [매니저 전용] 지역별 라우팅.
      세종 주문 → 매니저1(세종) 채널
      본사 주문 → 매니저2(본사) 채널
      전체/기타  → 두 채널 모두 전송
    Owner에게는 전송하지 않음.
    """
    cfg = _get_notif_settings()
    full = message
    if order_id is not None and cfg.get("app_url"):
        full += f"\n\n🔗 [주문 바로가기]({_build_order_deeplink(cfg['app_url'], order_id)})"

    results = []
    if region == "세종":
        if cfg["mgr1_enabled"]:
            results.append(_raw_telegram(cfg["mgr1_bot_token"], cfg["mgr1_chat_id"], full))
        else:
            results.append({"success": False, "error": "매니저1(세종) 텔레그램 미설정"})
    elif region in ("본사", ""):
        if cfg["mgr2_enabled"]:
            results.append(_raw_telegram(cfg["mgr2_bot_token"], cfg["mgr2_chat_id"], full))
        else:
            results.append({"success": False, "error": "매니저2(본사) 텔레그램 미설정"})
    else:
        # 전체: 두 채널 모두
        if cfg["mgr1_enabled"]:
            results.append(_raw_telegram(cfg["mgr1_bot_token"], cfg["mgr1_chat_id"], full))
        if cfg["mgr2_enabled"]:
            results.append(_raw_telegram(cfg["mgr2_bot_token"], cfg["mgr2_chat_id"], full))
        if not results:
            return {"success": False, "error": "매니저 텔레그램 미설정"}

    return results[0] if results else {"success": False, "error": "전송 채널 없음"}


def _send_webhook(payload: dict, webhook_url: str) -> dict:
    try:
        resp = requests.post(webhook_url, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=8)
        return {"success": resp.status_code < 300, "status_code": resp.status_code, "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "status_code": None, "error": "타임아웃 (8초)"}
    except Exception as e:
        return {"success": False, "status_code": None, "error": str(e)}


def _log_notification(event_type: str, order_id: Optional[int], message: str, result: dict,
                      recipient: str = "manager", region: str = "전체"):
    try:
        from data.db import _load, _save
        data = _load()
        data.setdefault("notification_log", [])
        data["notification_log"].append({
            "id": len(data["notification_log"]) + 1,
            "event_type": event_type,
            "order_id": order_id,
            "message": message,
            "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success": result.get("success", False),
            "status_code": result.get("status_code"),
            "error": result.get("error"),
            "recipient": recipient,
            "region": region,
        })
        data["notification_log"] = data["notification_log"][-500:]
        _save(data)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  ▣ 일상 운영 알림 — 담당 매니저만 (지역 라우팅)
# ═══════════════════════════════════════════════════════════════

def notify_delay(order: dict, overdue_min: int, penalty_amt: int) -> dict:
    """⏰ 지연 → 담당 매니저 텔레그램만"""
    region = order.get("region", "본사")
    message = (
        f"[순삭OS] ⏰ *지연 발생 — {region} 지역*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 주소: {order.get('pickup','—')}\n"
        f"■ 예약: {order.get('scheduled_time','—')}\n"
        f"■ 초과: *{overdue_min}분 지연*\n"
        f"■ 자동 페널티: ₩{penalty_amt:,} 차감 예정\n\n"
        f"📌 시스템이 자동으로 페널티를 적용했습니다."
    )
    result = _send_telegram_manager(message, order.get("id"), region=region)
    _log_notification("delay_detected", order.get("id"), message, result,
                      recipient="manager", region=region)
    return result


def notify_settlement_overrun(order: dict, estimate: int, actual: int,
                               manager_name: str = "—") -> dict:
    """💰 정산가 초과 → 담당 매니저 텔레그램만"""
    region = order.get("region", "본사")
    overrun_pct = ((actual - estimate) / estimate * 100) if estimate > 0 else 0
    message = (
        f"[순삭OS] 💰 *정산가 초과 — {region} 지역*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 담당 매니저: {manager_name}\n"
        f"■ 견적가: ₩{estimate:,}\n"
        f"■ 실 정산가: ₩{actual:,} (*+{overrun_pct:.1f}%*)\n\n"
        f"📌 초과분을 검토하고 고객에게 안내해 주세요."
    )
    result = _send_telegram_manager(message, order.get("id"), region=region)
    _log_notification("settlement_overrun", order.get("id"), message, result,
                      recipient="manager", region=region)
    return result


def notify_new_lead(order: dict, channel: str = "—") -> dict:
    """📋 신규 리드 → 담당 매니저 텔레그램만"""
    region = order.get("region", "본사")
    message = (
        f"[순삭OS] 📋 *신규 리드 — {region} 지역*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 작업: {'🔨 철거' if order.get('work_type') == '철거' else '📦 수거'}\n"
        f"■ 주소: {order.get('pickup','—')}\n"
        f"■ 예약: {order.get('scheduled_time','—')}\n"
        f"■ 기초 견적: ₩{order.get('base_fee',0):,}\n"
        f"■ 유입 경로: {channel}\n\n"
        f"📌 배차 스케줄링 탭에서 기사를 배정해 주세요."
    )
    result = _send_telegram_manager(message, order.get("id"), region=region)
    _log_notification("new_lead", order.get("id"), message, result,
                      recipient="manager", region=region)
    return result


def notify_quote_confirmed(order: dict, quote_amt: int, manager_name: str = "—") -> dict:
    """✅ 견적 확정 → 담당 매니저 텔레그램만 (Owner 승인 없음)"""
    region = order.get("region", "본사")
    message = (
        f"[순삭OS] ✅ *현장 견적 확정 — {region} 지역*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 확정 금액: *₩{quote_amt:,}*\n"
        f"■ 처리: {manager_name}\n\n"
        f"📌 기사 배차를 진행해 주세요."
    )
    result = _send_telegram_manager(message, order.get("id"), region=region)
    _log_notification("quote_confirmed", order.get("id"), message, result,
                      recipient="manager", region=region)
    return result


# ═══════════════════════════════════════════════════════════════
#  ▣ 예외/긴급 알림 — Owner 전용 (즉시 전송)
# ═══════════════════════════════════════════════════════════════

def notify_photo_mismatch(order: dict, score: int, reasoning: str, flags: list) -> dict:
    """🚨 AI 사진 불일치 → Owner 텔레그램 긴급"""
    cfg = _get_notif_settings()
    message = (
        f"🚨 *[긴급] AI 사진 불일치*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 지역: {order.get('region','본사')}\n"
        f"■ 담당 기사: {order.get('_driver_name','—')}\n"
        f"■ AI Score: *{score}점* (기준 75점 이상)\n"
        f"■ 판단: {reasoning}\n"
    )
    if flags:
        message += "■ 의심 사유:\n" + "\n".join(f"  - {f}" for f in flags) + "\n"
    message += "\n⚡ 즉시 현장 재확인 필요."
    payload = {"event": "photo_mismatch", "order_id": order.get("id"), "score": score,
               "message": message, "timestamp": datetime.now().isoformat(),
               "to": cfg.get("owner_phone", ""), "recipient": "owner", "priority": "emergency"}
    result = _send_webhook(payload, cfg["webhook_url"]) if cfg["enabled"] else \
             {"success": False, "status_code": None, "error": "웹훅 미설정"}
    _send_telegram(message, order.get("id"))
    _log_notification("photo_mismatch", order.get("id"), message, result,
                      recipient="owner", region=order.get("region", "본사"))
    return result


def notify_unregistered_phone(phone: str, contact_name: str,
                               driver_name: str = "—", order_id: int = None) -> dict:
    """🔐 미등록 번호 접촉 → Owner 긴급"""
    message = (
        f"🔐 *[긴급] 미등록 번호 접촉*\n\n"
        f"■ 미등록 번호: `{phone}`\n"
        f"■ 상대방: {contact_name}\n"
        f"■ 담당 기사: {driver_name}\n"
        f"■ 관련 주문: {'#' + str(order_id) if order_id else '—'}\n\n"
        f"⚡ 보안 점검 필요."
    )
    result = _send_telegram(message, order_id)
    _log_notification("unregistered_phone", order_id, message, result, recipient="owner")
    return result


def notify_settlement_hold(order: dict, score: int, reasoning: str) -> dict:
    """🔒 정산 보류 → Owner 긴급"""
    message = (
        f"🔒 *[긴급] 정산 자동 보류(Hold)*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 지역: {order.get('region','본사')}\n"
        f"■ AI Score: *{score}점* (기준 75점 미만)\n"
        f"■ 판단: {reasoning}\n\n"
        f"⚡ 대시보드에서 수동 해제 가능."
    )
    result = _send_telegram(message, order.get("id"))
    _log_notification("settlement_hold", order.get("id"), message, result,
                      recipient="owner", region=order.get("region", "본사"))
    return result


def notify_poor_attendance(driver: dict, monthly_jobs: int, threshold: int,
                            block_count: int) -> dict:
    """⚠️ 근태 불량 → Owner 긴급"""
    attain_pct = round(monthly_jobs / max(threshold, 1) * 100, 1)
    message = (
        f"⚠️ *[긴급] 근태 불량 — 의무 면담 필요*\n\n"
        f"■ 기사: {driver.get('name','—')}\n"
        f"■ 달성: {monthly_jobs}건 / {threshold}건 (*{attain_pct}%*)\n"
        f"■ 스케줄 차단: {block_count}회\n\n"
        f"⚡ 즉시 의무 면담 진행."
    )
    result = _send_telegram(message, None)
    _log_notification("poor_attendance", None, message, result, recipient="owner")
    return result


def notify_accident_report(driver: dict, order: dict, description: str) -> dict:
    """🚑 기사 사고 → Owner 최우선 긴급"""
    message = (
        f"🚑 *[최우선 긴급] 기사 사고 보고*\n\n"
        f"■ 기사: {driver.get('name','—')} / {driver.get('phone','—')}\n"
        f"■ 주문 #{order.get('id','—')} — {order.get('customer','—')}\n"
        f"■ 주소: {order.get('pickup','—')}\n"
        f"■ 사고 내용:\n{description}\n\n"
        f"🆘 즉시 확인 및 후속 조치 필요!"
    )
    result = _send_telegram(message, order.get("id"))
    _log_notification("accident_report", order.get("id"), message, result, recipient="owner")
    return result


def notify_customer_claim(order: dict, claim_description: str, reporter: str = "CS") -> dict:
    """📢 고객 클레임 → Owner 긴급"""
    message = (
        f"📢 *[긴급] 고객 클레임 접수*\n\n"
        f"■ 주문 #{order.get('id','—')} / {order.get('customer','—')}\n"
        f"■ 지역: {order.get('region','본사')}\n"
        f"■ 접수자: {reporter}\n"
        f"■ 내용:\n{claim_description}\n\n"
        f"⚡ 즉시 고객 대응 지시 필요."
    )
    result = _send_telegram(message, order.get("id"))
    _log_notification("customer_claim", order.get("id"), message, result,
                      recipient="owner", region=order.get("region", "본사"))
    return result


# ═══════════════════════════════════════════════════════════════
#  ▣ 비품 보충 신청 알림 — Owner 전용
# ═══════════════════════════════════════════════════════════════

def notify_supply_request(region: str, manager_label: str,
                           items: list, urgency: str = "일반") -> dict:
    """
    📦 비품 보충 신청 → Owner 텔레그램 즉시 전송
    items: [{"name": "보양재", "qty": "2팩"}, ...]
    urgency: "일반" | "긴급"
    """
    urgency_icon = "🚨" if urgency == "긴급" else "📦"
    items_text = "\n".join(
        f"  - {i.get('name','—')}: {i.get('qty','미기재')}"
        for i in items
    ) or "  (항목 없음)"

    message = (
        f"{urgency_icon} *[비품 보충 신청] {urgency}*\n\n"
        f"■ 지역: {region}\n"
        f"■ 신청자: {manager_label}\n"
        f"■ 신청 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"■ 신청 소모품:\n{items_text}\n\n"
        f"⚡ 순삭 OS 설정 → 물류창고 발송 처리 필요."
    )
    result = _send_telegram(message, order_id=None)
    _log_notification("supply_request", None, message, result,
                      recipient="owner", region=region)
    return result


# ═══════════════════════════════════════════════════════════════
#  알림 이력 조회
# ═══════════════════════════════════════════════════════════════

def get_notification_log(limit: int = 100) -> list:
    try:
        from data.db import _load
        data = _load()
        return list(reversed(data.get("notification_log", [])[-limit:]))
    except Exception:
        return []
