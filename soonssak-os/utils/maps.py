import math
import requests
from datetime import datetime, timedelta


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 GPS 좌표 간 직선거리(km) — Haversine 공식"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def geocode_address(address: str) -> tuple[float, float] | None:
    """
    OpenStreetMap Nominatim으로 한국 주소 → (lat, lng) 좌표 변환.
    API 키 불필요, 무료.
    실패 시 None 반환.
    """
    try:
        params = {
            "q": address + ", 대한민국",
            "format": "json",
            "limit": 1,
            "countrycodes": "kr",
        }
        headers = {"User-Agent": "SoonsakOS/1.0 contact@soonssak.co.kr"}
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=6,
        )
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def get_osrm_route(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
) -> dict | None:
    """
    OSRM (Open Source Routing Machine) — 실제 도로 기반 소요시간/거리 계산.
    API 키 불필요, 무료.
    반환: {"duration_min": int, "dist_km": float, "source": "OSRM"} 또는 None.
    """
    try:
        url = (
            f"http://router.project-osrm.org/route/v1/driving/"
            f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
        )
        resp = requests.get(url, params={"overview": "false"}, timeout=7)
        data = resp.json()
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return {
                "duration_min": max(1, int(route["duration"] / 60)),
                "dist_km": round(route["distance"] / 1000, 1),
                "source": "OSRM",
            }
    except Exception:
        pass
    return None


def estimate_travel(
    origin_lat: float, origin_lng: float,
    dest_lat: float, dest_lng: float,
) -> dict:
    """
    OSRM 결과를 우선 사용, 실패 시 Haversine + 도심속도 25km/h 폴백.
    항상 dict 반환: {"duration_min", "dist_km", "source"}
    """
    osrm = get_osrm_route(origin_lat, origin_lng, dest_lat, dest_lng)
    if osrm:
        return osrm
    dist = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    duration_min = max(5, int(dist / 25 * 60))
    return {
        "duration_min": duration_min,
        "dist_km": round(dist, 1),
        "source": "추정(직선거리)",
    }


def compute_eta(departed_at: datetime, duration_min: int) -> datetime:
    return departed_at + timedelta(minutes=duration_min)


def efficiency_label(expected_min: int, actual_min: int) -> tuple[str, str]:
    """
    예상 vs 실제 이동 시간 비교.
    반환: (emoji_label, css_color)
    """
    if actual_min <= expected_min:
        return "🟢 정상", "#4caf50"
    diff = actual_min - expected_min
    if diff < 30:
        return f"🟡 +{diff}분 지연", "#ff9800"
    return f"🔴 +{diff}분 지연 (패널티)", "#f44336"
