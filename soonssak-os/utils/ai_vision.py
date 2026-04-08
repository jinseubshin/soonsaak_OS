import os
import base64
import json
from pathlib import Path
from typing import Optional

PHOTOS_DIR = Path(__file__).parent.parent / "data" / "photos"
PHOTOS_DIR.mkdir(exist_ok=True)

MATCH_ALERT_THRESHOLD = 75  # 이 점수 미만이면 대표 대시보드 알림 + 카톡 전송


def save_photo(order_id: int, photo_type: str, file_bytes: bytes, ext: str = "jpg") -> str:
    """사진을 파일로 저장하고 경로 반환. photo_type: 'estimate' | 'completion'"""
    filename = f"order_{order_id}_{photo_type}.{ext}"
    path = PHOTOS_DIR / filename
    path.write_bytes(file_bytes)
    return str(path)


def load_photo_b64(path: str) -> Optional[str]:
    """파일 경로에서 base64 인코딩 문자열 반환"""
    try:
        return base64.b64encode(Path(path).read_bytes()).decode()
    except Exception:
        return None


def compare_photos(estimate_path: str, completion_path: str, order_info: dict) -> dict:
    """
    GPT-4o Vision으로 견적 사진 vs 완료 사진 비교 후 Match Score 산출.
    Returns: {"score": int, "reasoning": str, "flagged": bool, "error": str|None}
    """
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "dummy"),
        )

        b64_estimate = load_photo_b64(estimate_path)
        b64_completion = load_photo_b64(completion_path)

        if not b64_estimate or not b64_completion:
            return {"score": None, "reasoning": "사진 파일 로드 실패", "flagged": False, "error": "file_load_error"}

        scope = order_info.get("demolition_scope", "철거 작업")
        area = order_info.get("demolition_area", "—")
        customer = order_info.get("customer", "—")

        system_prompt = (
            "당신은 철거·정리 전문 현장 검수 AI입니다. "
            "견적 사진(현장 방문 시 촬영)과 완료 사진(작업 후 촬영)을 비교하여 "
            "작업이 견적 범위대로 완수되었는지 검증합니다."
        )

        user_prompt = (
            f"주문 정보:\n"
            f"- 고객: {customer}\n"
            f"- 작업 범위: {scope}\n"
            f"- 면적: {area}평\n\n"
            "아래 두 사진을 비교 분석하세요:\n"
            "• 첫 번째 이미지: 매니저 현장 방문 시 촬영한 '견적용 사진'\n"
            "• 두 번째 이미지: 기사 작업 완료 후 촬영한 '완료 사진'\n\n"
            "다음 기준으로 '일치 점수(Match Score)'를 0~100 사이의 정수로 산출하세요:\n"
            "- 같은 현장/장소로 보이는가? (위치 일치성)\n"
            "- 작업이 실제로 완료된 것처럼 보이는가? (작업 완성도)\n"
            "- 견적에서 약속한 범위가 이행되었는가? (범위 이행율)\n"
            "- 의심스러운 점이 있는가? (이상 징후)\n\n"
            "반드시 아래 JSON 형식으로만 응답하세요:\n"
            '{"score": <0~100 정수>, "reasoning": "<한국어로 2~3문장 근거 설명>", '
            '"flags": ["<의심 사유1>", "<의심 사유2>"]}'
        )

        response = client.chat.completions.create(
            model="gpt-5.2",
            max_completion_tokens=512,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_estimate}", "detail": "high"},
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_completion}", "detail": "high"},
                        },
                    ],
                },
            ],
        )

        raw = response.choices[0].message.content.strip()
        # JSON 파싱 시도
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                return {"score": None, "reasoning": raw, "flagged": False, "error": "parse_error"}

        score = int(result.get("score", 0))
        reasoning = result.get("reasoning", "")
        flags = result.get("flags", [])
        flagged = score < MATCH_ALERT_THRESHOLD

        return {
            "score": score,
            "reasoning": reasoning,
            "flags": flags,
            "flagged": flagged,
            "error": None,
        }

    except Exception as e:
        return {"score": None, "reasoning": f"AI 분석 오류: {e}", "flagged": False, "error": str(e)}


def score_badge(score: Optional[int]) -> str:
    """점수에 따른 색상 뱃지 HTML"""
    if score is None:
        return "<span style='color:#888'>분석 대기</span>"
    if score >= 80:
        color, label = "#16a34a", "우수"
    elif score >= MATCH_ALERT_THRESHOLD:
        color, label = "#d97706", "주의"
    else:
        color, label = "#dc2626", "불일치 의심"
    return (
        f"<span style='background:{color};color:white;padding:3px 10px;"
        f"border-radius:12px;font-weight:bold;font-size:14px'>"
        f"{score}점 — {label}</span>"
    )
