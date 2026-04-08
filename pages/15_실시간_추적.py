"""
실시간 기사 위치 추적 페이지 — 고객 전용 (인증 불필요)
URL: /실시간_추적?oid={order_id}&tok={tracking_token}
30초마다 자동 갱신 / Leaflet.js 지도 / 지오펜싱 상태 표시
"""
import streamlit as st
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data.db import get_trip_data, get_orders

st.set_page_config(
    page_title="기사 위치 추적 — 순삭",
    page_icon="📡",
    layout="centered",
)

# ── 스타일
st.markdown(
    """
<style>
  #MainMenu, header, footer {visibility: hidden;}
  .block-container {padding-top: 1rem !important; max-width: 720px}
  .track-card {
    background: white;
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.10);
    margin: 8px 0;
  }
  .status-chip {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
  }
</style>
""",
    unsafe_allow_html=True,
)

# ── 쿼리 파라미터 파싱
_params = st.query_params
_oid_raw = _params.get("oid", "")
_tok_raw = _params.get("tok", "")

try:
    _order_id = int(_oid_raw)
except (ValueError, TypeError):
    _order_id = None

# ── 유효성 검증
if not _order_id or not _tok_raw:
    st.error("❌ 잘못된 추적 링크입니다. 기사가 발송한 링크를 다시 확인해 주세요.")
    st.stop()

trip = get_trip_data(_order_id)

if not trip:
    st.warning("⏳ 기사가 아직 출발하지 않았거나 추적 정보가 없습니다.")
    st.stop()

if trip.get("tracking_token") != _tok_raw:
    st.error("❌ 추적 링크가 만료되었거나 유효하지 않습니다.")
    st.stop()

# ── 주문 정보 조회
orders = get_orders()
order = next((o for o in orders if o["id"] == _order_id), None)

# ── 상태 배지
_status = trip.get("status", "in_progress")
_geofence = trip.get("geofence_triggered", False)
_arrived = trip.get("arrived_at") or (order and order.get("arrived_at"))

if _arrived:
    _chip_color = "#4caf50"
    _chip_text = "✅ 현장 도착 완료"
elif _geofence:
    _chip_color = "#ff9800"
    _chip_text = "🔔 잠시 후 도착 (100m 이내)"
else:
    _chip_color = "#1976d2"
    _chip_text = "🚗 이동 중"

# ── 헤더
st.markdown(
    f"""
<div class='track-card' style='text-align:center;background:linear-gradient(135deg,#1976d2,#42a5f5)'>
  <h2 style='color:white;margin:0 0 6px 0'>📡 기사 실시간 위치</h2>
  <span class='status-chip' style='background:{_chip_color};color:white'>{_chip_text}</span>
</div>
""",
    unsafe_allow_html=True,
)

# ── 핵심 정보 카드
_eta = trip.get("eta_str", "—")
_exp_min = trip.get("expected_min", 0)
_driver_name = trip.get("driver_name", "기사")
_dep_at = trip.get("departed_at", "")
_dep_display = _dep_at[11:16] if len(_dep_at) >= 16 else "—"
_dest_addr = trip.get("dest_address", "—")

_eta_remain = ""
if not _arrived and _eta != "—" and _dep_at:
    try:
        _now = datetime.now()
        _eta_dt = datetime.strptime(_dep_at[:10] + " " + _eta, "%Y-%m-%d %H:%M")
        _remain = int((_eta_dt - _now).total_seconds() / 60)
        _eta_remain = f" (약 {_remain}분 남음)" if _remain > 0 else " (도착 임박)"
    except Exception:
        pass

col_a, col_b = st.columns(2)
with col_a:
    st.markdown(
        f"<div class='track-card'>"
        f"<div style='font-size:12px;color:#888'>담당 기사</div>"
        f"<div style='font-size:20px;font-weight:700'>{_driver_name} 기사</div>"
        f"<div style='font-size:12px;color:#555;margin-top:4px'>출발: {_dep_display}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        f"<div class='track-card'>"
        f"<div style='font-size:12px;color:#888'>도착 예정</div>"
        f"<div style='font-size:20px;font-weight:700'>{_eta}</div>"
        f"<div style='font-size:12px;color:#1976d2;margin-top:4px'>{_eta_remain}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ── 지도 (Leaflet.js — API Key 불필요)
_cur_lat = trip.get("current_lat") or 37.5665
_cur_lng = trip.get("current_lng") or 126.9780
_dest_lat = trip.get("dest_lat")
_dest_lng = trip.get("dest_lng")
_gps_ts = trip.get("current_ts", "")
_gps_time_display = _gps_ts[11:16] if len(_gps_ts) >= 16 else "—"

_dest_marker_js = ""
if _dest_lat and _dest_lng:
    _dest_marker_js = f"""
    var destMarker = L.marker([{_dest_lat}, {_dest_lng}], {{
        icon: L.divIcon({{
            html: '<div style="font-size:28px">📍</div>',
            iconSize: [32, 32], iconAnchor: [16, 32]
        }})
    }}).addTo(map);
    destMarker.bindPopup('<b>목적지</b><br>{_dest_addr}').openPopup();

    var routeLine = L.polyline(
        [[{_cur_lat}, {_cur_lng}], [{_dest_lat}, {_dest_lng}]],
        {{color:'#1976d2', weight:3, dashArray:'6,6', opacity:0.7}}
    ).addTo(map);

    var geofenceCircle = L.circle([{_dest_lat}, {_dest_lng}], {{
        radius: 100,
        color: '#ff9800', fillColor:'#fff9c4', fillOpacity: 0.35, weight: 2
    }}).addTo(map);
    geofenceCircle.bindTooltip('도착 감지 범위 (100m)');
    """

_geofence_badge = ""
if _geofence:
    _geofence_badge = "var gfBadge = L.popup().setLatLng([" + str(_cur_lat) + "," + str(_cur_lng) + "]).setContent('<b>🔔 100m 이내 진입!</b>').addTo(map);"

_map_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body {{ margin:0; padding:0; }}
  #map {{ height: 340px; width: 100%; border-radius: 12px; }}
  .gps-badge {{
    position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
    background: rgba(255,255,255,0.93); padding: 4px 12px; border-radius: 20px;
    font-size: 12px; color: #555; z-index: 1000; white-space: nowrap;
    box-shadow: 0 1px 6px rgba(0,0,0,0.15);
  }}
</style>
</head>
<body>
<div style="position:relative">
<div id="map"></div>
<div class="gps-badge">📡 마지막 갱신: {_gps_time_display} (30초마다 자동 갱신)</div>
</div>
<script>
  var map = L.map('map').setView([{_cur_lat}, {_cur_lng}], 15);

  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap', maxZoom: 19
  }}).addTo(map);

  var driverIcon = L.divIcon({{
    html: '<div style="font-size:32px;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.3))">🚗</div>',
    iconSize: [36, 36], iconAnchor: [18, 18]
  }});

  var driverMarker = L.marker([{_cur_lat}, {_cur_lng}], {{icon: driverIcon}}).addTo(map);
  driverMarker.bindPopup('<b>기사 현재 위치</b><br>위도 {_cur_lat:.5f}<br>경도 {_cur_lng:.5f}');

  {_dest_marker_js}
  {_geofence_badge}
</script>
</body>
</html>
"""

st.components.v1.html(_map_html, height=360, scrolling=False)

# ── GPS 이력 요약
_history = trip.get("gps_history", [])
_gps_count = len(_history)
st.caption(f"📊 GPS 기록 수: {_gps_count}개 | 목적지: {_dest_addr[:30]}{'…' if len(_dest_addr) > 30 else ''}")

# ── 알림 상태
if _arrived:
    st.success(
        f"✅ **{_driver_name} 기사가 현장에 도착했습니다.**\n\n"
        f"도착 시각: {str(_arrived)[11:16]} | "
        f"총 이동: {trip.get('actual_min', '—')}분"
    )
elif _geofence:
    st.warning(
        "🔔 **기사가 목적지 100m 이내에 진입했습니다.**\n\n"
        "'잠시 후 도착합니다. 문을 열어주시거나 작업 준비를 부탁드립니다.' 알림이 발송되었습니다."
    )
else:
    st.info(
        f"🚗 **{_driver_name} 기사가 이동 중입니다.**\n\n"
        f"예상 도착: **{_eta}** | 예상 이동 시간: {_exp_min}분\n\n"
        "이 페이지는 30초마다 자동으로 새로고침됩니다."
    )

# ── 고객 안내
st.markdown(
    """
<div style='background:#f5f5f5;border-radius:10px;padding:12px 16px;
font-size:13px;color:#555;margin-top:12px'>
<b>📌 안내사항</b><br>
• 지도의 🚗 아이콘이 기사님의 현재 위치입니다<br>
• 📍 아이콘이 방문 예정 주소입니다<br>
• 주황색 원(100m) 안에 기사님이 진입하면 도착 알림이 발송됩니다<br>
• 문의: 순삭 본사 고객센터
</div>
""",
    unsafe_allow_html=True,
)

# ── 자동 갱신 (30초 JavaScript 리로드)
if not _arrived:
    st.components.v1.html(
        """
<script>
  setTimeout(function() { window.parent.location.reload(); }, 30000);
</script>
""",
        height=0,
    )
