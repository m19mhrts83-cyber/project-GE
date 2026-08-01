// 周辺MAP 単独Web（メンバー向け自動作成）
// Pages ビルド時は EMBEDDED_MAPS_KEY の値だけを運営キーへ置換する。
const EMBEDDED_MAPS_KEY = '__GOOGLE_MAPS_BROWSER_KEY__';
const MAPS_KEY_PLACEHOLDER = '__GOOGLE_MAPS_BROWSER_KEY__';

let map;
let markers = [];
let infoWindow;
let apiKey = '';
let lastCoords = [];
let lastRoute = null;
let routePolyline = null;
let routeInfoMarker = null;
let lastResult = null;
let adoptedC1 = null;

const CLEAN_MAP_STYLES = [
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.business', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.attraction', stylers: [{ visibility: 'off' }] },
  { featureType: 'poi.park', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative.neighborhood', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative.land_parcel', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative.locality', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'landscape', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'water', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit.station', elementType: 'labels', stylers: [{ visibility: 'off' }] },
];

function hasEmbeddedMapsKey() {
  return Boolean(EMBEDDED_MAPS_KEY) && EMBEDDED_MAPS_KEY !== MAPS_KEY_PLACEHOLDER;
}

function resolveApiKey() {
  if (hasEmbeddedMapsKey()) return EMBEDDED_MAPS_KEY.trim();
  const input = document.getElementById('apiKeyInput');
  if (input && input.value.trim()) return input.value.trim();
  return (localStorage.getItem('googleMapsApiKey') || '').trim();
}

function syncApiKeyUi() {
  const section = document.getElementById('apiKeySection');
  const input = document.getElementById('apiKeyInput');
  if (hasEmbeddedMapsKey()) {
    if (section) section.style.display = 'none';
    apiKey = EMBEDDED_MAPS_KEY.trim();
    return;
  }
  if (section) section.style.display = '';
  const saved = localStorage.getItem('googleMapsApiKey');
  if (saved && input) {
    input.value = saved;
    apiKey = saved;
  }
}

function apiBase() {
  const params = new URLSearchParams(location.search);
  const q = (params.get('api') || '').replace(/\/$/, '');
  if (q) {
    localStorage.setItem('shuhenAutoApiBase', q);
    return q;
  }
  const saved = (localStorage.getItem('shuhenAutoApiBase') || '').replace(/\/$/, '');
  if (saved) return saved;
  // same origin when served by shuhen_auto_server.py
  if (location.port === '8765' || location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
    return location.origin;
  }
  return '';
}

function authHeaders() {
  const params = new URLSearchParams(location.search);
  const token = params.get('token') || localStorage.getItem('shuhenAutoToken') || '';
  const h = { 'Content-Type': 'application/json' };
  if (token) h['X-Shuhen-Token'] = token;
  return h;
}

document.addEventListener('DOMContentLoaded', () => {
  syncApiKeyUi();
  const input = document.getElementById('apiKeyInput');
  if (input && !hasEmbeddedMapsKey()) {
    input.addEventListener('change', (e) => {
      apiKey = e.target.value.trim();
      localStorage.setItem('googleMapsApiKey', apiKey);
    });
  }
  const hint = document.getElementById('apiHint');
  const base = apiBase();
  if (hint) {
    hint.textContent = base
      ? `API: ${base}`
      : 'API未設定。ローカルは scripts/shuhen_auto_server.py、または ?api=https://... を指定';
  }
  const cleanToggle = document.getElementById('cleanStyleToggle');
  const routeToggle = document.getElementById('walkRouteToggle');
  if (cleanToggle) {
    cleanToggle.addEventListener('change', () => {
      if (map) map.setOptions({ styles: cleanToggle.checked ? CLEAN_MAP_STYLES : [] });
    });
  }
  if (routeToggle) {
    routeToggle.addEventListener('change', () => {
      if (lastCoords.length && map) updateWalkRoute(lastCoords).catch(console.error);
    });
  }
  document.getElementById('dlC0Base').addEventListener('click', () => downloadB64('c0_base.png', lastResult?.images?.c0_base_png_b64));
  document.getElementById('dlC0Pins').addEventListener('click', () => downloadB64('c0_with_pins.png', lastResult?.images?.c0_with_pins_png_b64));

  // Grandole quick fill for local verify
  if (paramsHasDemo()) {
    document.getElementById('propertyName').value = 'Grandole志賀本通';
    document.getElementById('propertyAddress').value = '愛知県名古屋市北区杉栄町';
  }
});

function paramsHasDemo() {
  return new URLSearchParams(location.search).get('demo') === '1';
}

function showError(message) {
  const errorDiv = document.getElementById('errorMessage');
  errorDiv.textContent = message;
  errorDiv.style.display = 'block';
}

function hideError() {
  document.getElementById('errorMessage').style.display = 'none';
}

function setRunLoading(loading) {
  const button = document.getElementById('runButton');
  const buttonText = button.querySelector('.button-text');
  const spinner = button.querySelector('.loading-spinner');
  button.disabled = loading;
  buttonText.style.display = loading ? 'none' : 'inline';
  spinner.style.display = loading ? 'inline' : 'none';
}

function setProgress(lines) {
  const el = document.getElementById('progressList');
  if (!lines || !lines.length) {
    el.style.display = 'none';
    el.innerHTML = '';
    return;
  }
  el.style.display = 'block';
  el.innerHTML = lines.map((t) => `<li>${t}</li>`).join('');
}

function downloadB64(filename, b64) {
  if (!b64) return;
  const a = document.createElement('a');
  a.href = `data:image/png;base64,${b64}`;
  a.download = filename;
  a.click();
}

function numberedIcon(label, isProperty) {
  const bg = isProperty ? '#c0392b' : '#2980b9';
  const svg = encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="36" height="44" viewBox="0 0 36 44">
      <path fill="${bg}" stroke="#fff" stroke-width="2" d="M18 1C9.2 1 2 8.2 2 17c0 11.5 16 26 16 26s16-14.5 16-26C34 8.2 26.8 1 18 1z"/>
      <circle cx="18" cy="16" r="10" fill="#fff"/>
      <text x="18" y="20" text-anchor="middle" font-size="10" font-family="Arial,sans-serif" font-weight="bold" fill="${bg}">${label}</text>
    </svg>`
  );
  return {
    url: `data:image/svg+xml,${svg}`,
    scaledSize: new google.maps.Size(36, 44),
    anchor: new google.maps.Point(18, 44),
  };
}

function loadGoogleMapsScript(callback) {
  if (typeof google !== 'undefined' && google.maps) {
    callback();
    return;
  }
  const script = document.createElement('script');
  script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&language=ja`;
  script.async = true;
  script.defer = true;
  script.onload = callback;
  script.onerror = () => showError('Google Maps APIの読み込みに失敗しました。');
  document.head.appendChild(script);
}

function clearMarkers() {
  markers.forEach((m) => m.setMap(null));
  markers = [];
}

function clearRouteOverlay() {
  if (routePolyline) {
    routePolyline.setMap(null);
    routePolyline = null;
  }
  if (routeInfoMarker) {
    routeInfoMarker.setMap(null);
    routeInfoMarker = null;
  }
  lastRoute = null;
  const el = document.getElementById('routeSummary');
  if (el) el.textContent = '';
}

function looksLikeStation(row) {
  if (!row || row.isProperty) return false;
  const blob = `${row.id || ''} ${row.name || ''} ${row.query || ''}`;
  return /駅/.test(blob);
}

function requestWalkingRoute(origin, destination) {
  return new Promise((resolve) => {
    const service = new google.maps.DirectionsService();
    service.route(
      {
        origin,
        destination,
        travelMode: google.maps.TravelMode.WALKING,
        language: 'ja',
        region: 'jp',
      },
      (result, status) => {
        if (status === 'OK' && result?.routes?.[0]) resolve(result);
        else resolve(null);
      }
    );
  });
}

async function updateWalkRoute(rows) {
  clearRouteOverlay();
  const summary = document.getElementById('routeSummary');
  const on = document.getElementById('walkRouteToggle')?.checked;
  if (!on) {
    if (summary) summary.textContent = '';
    return;
  }
  if (!map || !google?.maps) return;
  const property = rows.find((r) => r.isProperty && r.ok && r.lat != null);
  const stations = rows.filter((r) => r.ok && r.lat != null && looksLikeStation(r));
  if (!property || !stations.length) {
    if (summary) summary.textContent = '徒歩動線: 駅または物件が不足';
    return;
  }
  const origin = { lat: property.lat, lng: property.lng };
  let best = null;
  for (const st of stations) {
    const result = await requestWalkingRoute({ lat: st.lat, lng: st.lng }, origin);
    if (!result) continue;
    const leg = result.routes[0].legs[0];
    const meters = leg.distance ? leg.distance.value : Number.POSITIVE_INFINITY;
    if (!best || meters < best.meters) {
      best = {
        station: st,
        result,
        meters,
        distanceText: leg.distance?.text || '',
        durationText: leg.duration?.text || '',
      };
    }
  }
  if (!best) return;
  const path = best.result.routes[0].overview_path.map((p) => ({ lat: p.lat(), lng: p.lng() }));
  routePolyline = new google.maps.Polyline({
    path,
    geodesic: true,
    strokeColor: '#c0392b',
    strokeOpacity: 0.95,
    strokeWeight: 5,
    map,
    zIndex: 50,
  });
  if (summary) {
    summary.textContent = `徒歩動線: ${best.station.id} ${best.station.name} → 物件（約${best.durationText} / ${best.distanceText}）`;
  }
}

function renderFacilityList(result) {
  const intro = document.getElementById('facilityIntro');
  const list = document.getElementById('facilityList');
  const ok = (result.facilities || []).filter((f) => f.ok);
  intro.textContent = `周辺施設には、次のようなものがあります（確定 ${ok.length} 件。要確認は徒歩分などをマップで最終確認してください）。`;
  list.innerHTML = (result.facilities || [])
    .map((f) => {
      const check = f.needs_check || !f.ok
        ? `<div class="needs-check">${f.ok ? '要確認（徒歩・評判）' : '地図上で未確定'}</div>`
        : '';
      return `<div class="facility-card"><span class="id">${f.id}</span><strong>${f.name}</strong>
        <div>${f.blurb || ''}</div>
        <div style="font-size:0.85rem;color:#666">${f.category || ''} / ${f.query || ''}</div>
        ${check}</div>`;
    })
    .join('');
}

function renderC0(result) {
  const box = document.getElementById('c0Preview');
  const base = result.images?.c0_base_png_b64;
  const pins = result.images?.c0_with_pins_png_b64;
  box.innerHTML = '';
  if (base) {
    box.innerHTML += `<figure><img alt="C0下地" src="data:image/png;base64,${base}"><figcaption>ピンなし下地（C0）</figcaption></figure>`;
  }
  if (pins) {
    box.innerHTML += `<figure><img alt="C0骨格" src="data:image/png;base64,${pins}"><figcaption>ピン付き骨格（C0）</figcaption></figure>`;
  }
  document.getElementById('dlC0Base').disabled = !base;
  document.getElementById('dlC0Pins').disabled = !pins;
}

function renderMapFromResult(result) {
  const prop = result.property_pin;
  if (!prop?.ok) {
    showError('物件ピンがありません');
    return;
  }
  const rows = [
    { ...prop, isProperty: true },
    ...(result.facilities || []).map((f) => ({ ...f, isProperty: false })),
  ];
  lastCoords = rows;
  clearMarkers();
  clearRouteOverlay();
  infoWindow = new google.maps.InfoWindow();
  const clean = document.getElementById('cleanStyleToggle')?.checked !== false;
  map = new google.maps.Map(document.getElementById('map'), {
    center: { lat: prop.lat, lng: prop.lng },
    zoom: 15,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true,
    styles: clean ? CLEAN_MAP_STYLES : [],
  });
  const bounds = new google.maps.LatLngBounds();
  rows
    .filter((r) => r.ok && r.lat != null)
    .forEach((r) => {
      const pos = { lat: r.lat, lng: r.lng };
      bounds.extend(pos);
      const marker = new google.maps.Marker({
        map,
        position: pos,
        title: `${r.id} ${r.name}`,
        icon: numberedIcon(String(r.id || '?').replace(/^P/, '') || '?', r.isProperty),
        zIndex: r.isProperty ? 1000 : 100,
      });
      marker.addListener('click', () => {
        infoWindow.setContent(
          `<div style="padding:4px 8px"><strong>${r.id}</strong> ${r.name}<br><small>${r.blurb || r.formatted || ''}</small></div>`
        );
        infoWindow.open(map, marker);
      });
      markers.push(marker);
    });
  if (!bounds.isEmpty()) map.fitBounds(bounds, 48);
  updateWalkRoute(rows).catch(console.error);
}

async function runAutoPipeline() {
  hideError();
  const base = apiBase();
  if (!base) {
    showError('APIサーバーが未設定です。scripts/shuhen_auto_server.py を起動するか、?api= でURLを指定してください。');
    return;
  }
  const property_name = document.getElementById('propertyName').value.trim();
  const address = document.getElementById('propertyAddress').value.trim();
  const target = document.getElementById('targetInput').value.trim();
  const facility_count = Number(document.getElementById('facilityCount').value || 15);
  if (!property_name || !address) {
    showError('物件名と住所を入力してください。');
    return;
  }

  setRunLoading(true);
  setProgress(['洗い出し中…', '続けて実在検証・地図・色付き下地まで実行します（数分かかることがあります）']);
  document.getElementById('resultsSection').style.display = 'none';
  document.getElementById('c1Button').disabled = true;
  adoptedC1 = null;

  try {
    const res = await fetch(`${base}/api/run`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ property_name, address, target, facility_count }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    lastResult = data.result;
    const steps = (lastResult.steps || []).map((s) => `${s.ok ? '✓' : '×'} ${s.id}: ${s.detail || ''}`);
    setProgress(steps);
    document.getElementById('resultsTitle').textContent = `${lastResult.property_name} 周辺MAP`;
    document.getElementById('areaBlurb').textContent = lastResult.area_blurb || '';
    renderFacilityList(lastResult);
    renderC0(lastResult);
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('c1Button').disabled = false;

    apiKey = resolveApiKey();
    if (!apiKey) {
      showError('地図表示用の Maps API Key がありません（下地画像は取得済みです）。');
    } else {
      if (!hasEmbeddedMapsKey()) localStorage.setItem('googleMapsApiKey', apiKey);
      loadGoogleMapsScript(() => renderMapFromResult(lastResult));
    }
    if (lastResult.errors?.length) {
      console.warn('pipeline warnings', lastResult.errors);
    }
  } catch (err) {
    console.error(err);
    showError(`作成に失敗しました: ${err.message || err}`);
    setProgress([]);
  } finally {
    setRunLoading(false);
  }
}

async function runC1() {
  if (!lastResult?.job_id) return;
  const base = apiBase();
  if (!base) return;
  const btn = document.getElementById('c1Button');
  btn.disabled = true;
  document.getElementById('c1Message').textContent = 'C1 生成中…（最大2分）';
  document.getElementById('c1Preview').innerHTML = '';
  try {
    const res = await fetch(`${base}/api/c1`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ job_id: lastResult.job_id, timeout_sec: 120 }),
    });
    const data = await res.json();
    const c1 = data.c1 || {};
    document.getElementById('c1Message').textContent = c1.message || (data.error || '');
    if (c1.status !== 'ready' || !c1.png_b64) {
      btn.disabled = false;
      return;
    }
    const box = document.getElementById('c1Preview');
    box.innerHTML = `<figure><img alt="C1" src="data:image/png;base64,${c1.png_b64}"><figcaption>C1プレビュー（未採用）</figcaption></figure>`;
    if (c1.with_pins_png_b64) {
      box.innerHTML += `<figure><img alt="C1 pins" src="data:image/png;base64,${c1.with_pins_png_b64}"><figcaption>C1＋ピン再合成</figcaption></figure>`;
    }
    adoptedC1 = c1;
    document.getElementById('c1Accept').style.display = 'inline-block';
    document.getElementById('c1Reject').style.display = 'inline-block';
    document.getElementById('c1Accept').disabled = false;
    document.getElementById('c1Reject').disabled = false;
  } catch (err) {
    document.getElementById('c1Message').textContent = `C1失敗: ${err.message || err}`;
    btn.disabled = false;
  }
}

function acceptC1() {
  if (!adoptedC1?.png_b64 || !lastResult) return;
  lastResult.images.c0_base_png_b64 = adoptedC1.png_b64;
  if (adoptedC1.with_pins_png_b64) {
    lastResult.images.c0_with_pins_png_b64 = adoptedC1.with_pins_png_b64;
  }
  renderC0(lastResult);
  document.getElementById('c1Message').textContent = 'C1を採用し、ダウンロード画像を差し替えました。';
  document.getElementById('c1Accept').disabled = true;
  document.getElementById('c1Reject').disabled = true;
  document.getElementById('c1Button').disabled = false;
}

function rejectC1() {
  adoptedC1 = null;
  document.getElementById('c1Preview').innerHTML = '';
  document.getElementById('c1Message').textContent = 'C1を破棄しました。C0のまま利用できます。';
  document.getElementById('c1Accept').style.display = 'none';
  document.getElementById('c1Reject').style.display = 'none';
  document.getElementById('c1Button').disabled = false;
}
