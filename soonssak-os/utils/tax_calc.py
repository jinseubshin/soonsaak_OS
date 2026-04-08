"""
순삭 OS 세무 자동 계산 엔진
- 개인(3.3%): 원천세 공제 후 실지급
- 사업자(부가세 포함): Base ÷ 1.1 → 공급가액 + 부가세 분리, 총 지급 = Base 고정
"""
from typing import Optional


TAX_TYPE_INDIVIDUAL = "individual"   # 개인 사업소득 3.3%
TAX_TYPE_BUSINESS = "business"       # 사업자 부가세 포함

INDIVIDUAL_WITHHOLDING_RATE = 0.033  # 3.3% (소득세 3% + 지방소득세 0.3%)
VAT_RATE = 0.10                      # 부가세 10%
REVERSE_VAT_DIVISOR = 1 + VAT_RATE  # 1.1 — 역산용


def get_driver_tax_type(driver: dict) -> str:
    """기사 세무 유형 반환. 기본값: 개인"""
    return driver.get("tax_type", TAX_TYPE_INDIVIDUAL)


def calc_driver_settlement(base: float, driver: dict) -> dict:
    """
    기사 정산 계산.
    Args:
        base: 기준 금액 (기사 지급 기준액, 예: driver_pay)
        driver: 기사 dict
    Returns:
        {
          tax_type, base,
          supply_amount, vat, net_pay, withholding,
          label, breakdown_text, notice
        }
    """
    base = float(base)
    tax_type = get_driver_tax_type(driver)

    if tax_type == TAX_TYPE_BUSINESS:
        # 사업자: Base ÷ 1.1 = 공급가액, 부가세 = Base - 공급가액
        # 총 지급 = Base (추가 부가세 절대 없음)
        supply_amount = round(base / REVERSE_VAT_DIVISOR)
        vat = round(base - supply_amount)
        net_pay = base           # 총 지급 = Base 고정
        withholding = 0.0
        label = "사업자(부가세 포함)"
        breakdown_text = (
            f"총액 ₩{int(base):,} "
            f"(공급가 ₩{supply_amount:,} + 부가세 ₩{vat:,})"
        )
        notice = "세금계산서 발행 후 지급 처리됩니다."
        return {
            "tax_type": TAX_TYPE_BUSINESS,
            "label": label,
            "base": base,
            "supply_amount": supply_amount,
            "vat": vat,
            "withholding": withholding,
            "net_pay": net_pay,
            "breakdown_text": breakdown_text,
            "notice": notice,
        }
    else:
        # 개인: Base에서 3.3% 차감
        withholding = round(base * INDIVIDUAL_WITHHOLDING_RATE)
        net_pay = round(base - withholding)
        supply_amount = base
        vat = 0.0
        label = "개인(3.3%)"
        breakdown_text = (
            f"총액 ₩{int(base):,} "
            f"(세전 ₩{int(base):,} - 원천세 ₩{withholding:,})"
        )
        notice = "3.3% 공제 후 지급 예정입니다."
        return {
            "tax_type": TAX_TYPE_INDIVIDUAL,
            "label": label,
            "base": base,
            "supply_amount": base,
            "vat": vat,
            "withholding": withholding,
            "net_pay": net_pay,
            "breakdown_text": breakdown_text,
            "notice": notice,
        }


def format_tax_badge(tax_type: str) -> str:
    """세무 유형 뱃지 HTML"""
    if tax_type == TAX_TYPE_BUSINESS:
        return (
            "<span style='background:#1565c0;color:white;padding:2px 8px;"
            "border-radius:10px;font-size:12px'>🏢 사업자</span>"
        )
    return (
        "<span style='background:#2e7d32;color:white;padding:2px 8px;"
        "border-radius:10px;font-size:12px'>👤 개인 3.3%</span>"
    )


def monthly_settlement_summary(driver: dict, total_base: float) -> dict:
    """월간 정산 요약 계산 (월간 정산 명세서용)"""
    result = calc_driver_settlement(total_base, driver)
    return {
        **result,
        "driver_name": driver.get("name", "—"),
        "driver_id": driver.get("id"),
        "tax_type_label": result["label"],
        "total_base": total_base,
    }
