def mask_phone(phone: str, role: str = "manager") -> str:
    if not phone:
        return "***-****-****"
    if role == "admin":
        return phone
    # CS 역할: 뒷자리 전체 마스킹 (010-****-****)
    if role == "cs":
        parts = str(phone).split("-")
        if len(parts) >= 1:
            return f"{parts[0]}-****-****"
        return "***-****-****"
    # 매니저: 뒷 2자리만 표시
    parts = str(phone).split("-")
    if len(parts) == 3:
        return f"{parts[0]}-****-{parts[2][-2:]}**"
    cleaned = str(phone).replace("-", "").replace(" ", "")
    if len(cleaned) >= 4:
        return cleaned[:3] + "-****-" + cleaned[-2:] + "**"
    return "***-****-****"


def mask_name(name: str, role: str = "manager") -> str:
    if not name:
        return "***"
    if role == "admin":
        return name
    if len(name) <= 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)
