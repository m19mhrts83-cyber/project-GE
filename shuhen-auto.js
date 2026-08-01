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
  document.getElementById('dlC0Base').addEventListener('click', () => {
    const w = lastResult?.images?.width || 3508;
    const h = lastResult?.images?.height || 2480;
    downloadB64(`c0_base_A4_${w}x${h}.png`, lastResult?.images?.c0_base_png_b64);
  });
  document.getElementById('dlC0Pins').addEventListener('click', () => {
    const w = lastResult?.images?.width || 3508;
    const h = lastResult?.images?.height || 2480;
    downloadB64(`c0_with_pins_A4_${w}x${h}.png`, lastResult?.images?.c0_with_pins_png_b64);
  });

  // Prefill: ?name=&address=&target=&count=  / demo=1 (Grandole)
  applyPrefillFromQuery();
});

function paramsHasDemo() {
  return new URLSearchParams(location.search).get('demo') === '1';
}

function applyPrefillFromQuery() {
  const params = new URLSearchParams(location.search);
  const nameEl = document.getElementById('propertyName');
  const addrEl = document.getElementById('propertyAddress');
  const targetEl = document.getElementById('targetInput');
  const countEl = document.getElementById('facilityCount');
  if (paramsHasDemo()) {
    if (nameEl) nameEl.value = 'Grandole志賀本通';
    if (addrEl) addrEl.value = '愛知県名古屋市北区杉栄町';
  }
  const name = params.get('name');
  const address = params.get('address');
  const target = params.get('target');
  const count = params.get('count');
  if (name && nameEl) nameEl.value = name;
  if (address && addrEl) addrEl.value = address;
  if (target && targetEl) targetEl.value = target;
  if (count && countEl) countEl.value = count;
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

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function walkBandLabel(band, walkMin) {
  const m = walkMin != null ? `約${walkMin}分` : '—';
  const cls = `band-${band || 'far'}`;
  const tip =
    band === 'prefer' ? '優先圏（〜7分）' :
    band === 'soft' ? '推奨圏（〜20分）' :
    band === 'hard' ? '上限圏（〜30分）' :
    band === 'far' ? '遠い' : '不明';
  return `<span class="${cls}">${escapeHtml(m)}（${tip}）</span>`;
}

function renderResearch(result) {
  const box = document.getElementById('researchBox');
  const research = result.research;
  if (!box) return;
  if (!research) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'block';
  const pol = research.policy || {};
  const policyEl = document.getElementById('researchPolicy');
  if (policyEl) {
    policyEl.textContent =
      `徒歩の目安: 優先〜${pol.walk_prefer_min ?? 7}分 / 推奨〜${pol.walk_soft_max_min ?? 20}分 / 上限〜${pol.walk_hard_max_min ?? 30}分` +
      `｜保存サイズ: ${(pol.output_size_px || []).join('×') || 'A4横'} px` +
      `｜${pol.distance_note || '直線換算'}`;
  }

  const adopted = document.getElementById('researchAdopted');
  const rows = result.facilities || [];
  adopted.innerHTML = rows.length
    ? `<table class="research-table"><thead><tr><th>ID</th><th>名称</th><th>徒歩概算</th><th>理由</th><th>確認</th></tr></thead><tbody>${
        rows.map((f) => `<tr>
          <td>${escapeHtml(f.id)}</td>
          <td>${escapeHtml(f.resolvedName || f.name)}${f.ok ? '' : '（未確定）'}</td>
          <td>${walkBandLabel(f.walk_band, f.walk_min_approx)}</td>
          <td>${escapeHtml(f.why || f.blurb || '')}</td>
          <td>${f.needs_check ? '要確認' : '—'}</td>
        </tr>`).join('')
      }</tbody></table>`
    : '<p class="subtitle">採用施設なし</p>';

  const wash = research.wash || {};
  const washEl = document.getElementById('researchWash');
  const cands = wash.candidates || [];
  washEl.innerHTML = cands.length
    ? `<table class="research-table"><thead><tr><th>優先</th><th>名称</th><th>種別</th><th>理由</th></tr></thead><tbody>${
        cands.map((c) => `<tr>
          <td>${escapeHtml(c.priority || '')}</td>
          <td>${escapeHtml(c.name)}</td>
          <td>${escapeHtml(c.category || '')}</td>
          <td>${escapeHtml(c.why || c.blurb || '')}</td>
        </tr>`).join('')
      }</tbody></table>`
    : '<p class="subtitle">候補なし</p>';

  const rejected = (research.verify || {}).rejected || [];
  const rejEl = document.getElementById('researchRejected');
  rejEl.innerHTML = rejected.length
    ? `<table class="research-table"><thead><tr><th>名称</th><th>落とした理由</th></tr></thead><tbody>${
        rejected.map((r) => `<tr>
          <td>${escapeHtml(r.name || r.query || '')}</td>
          <td>${escapeHtml(r.reason || '')}</td>
        </tr>`).join('')
      }</tbody></table>`
    : '<p class="subtitle">検証段階での除外なし（または未返却）</p>';

  const dropped = [
    ...(research.walk_dropped || []),
    ...(research.user_excluded || []).map((u) => ({ ...u, drop_reason: u.drop_reason || 'ユーザー除外' })),
  ];
  const dropEl = document.getElementById('researchDropped');
  dropEl.innerHTML = dropped.length
    ? `<table class="research-table"><thead><tr><th>名称</th><th>徒歩</th><th>理由</th></tr></thead><tbody>${
        dropped.map((d) => `<tr>
          <td>${escapeHtml(d.name || '')}</td>
          <td>${d.walk_min_approx != null ? escapeHtml(`約${d.walk_min_approx}分`) : '—'}</td>
          <td>${escapeHtml(d.drop_reason || '')}</td>
        </tr>`).join('')
      }</tbody></table>`
    : '<p class="subtitle">距離・Places除外なし</p>';

  renderDeepPanel(research.deep);
  const deepBtn = document.getElementById('deepButton');
  const copyBtn = document.getElementById('deepCopyHandoff');
  if (deepBtn) deepBtn.disabled = !result.job_id;
  if (copyBtn) copyBtn.disabled = !result.job_id;
}

function renderDeepPanel(deep) {
  // API近似UIは停止中。案内は HTML 側。コピーボタンのみ利用。
  const el = document.getElementById('researchDeep');
  if (el) el.innerHTML = '';
  void deep;
}

async function runDeepResearch(_apply) {
  showError(
    'アプリ内 Deep Research（API近似）は停止中です。公式 Gemini の Deep Research（Step1.2）と「Step1.2渡す用をコピー」を使ってください。'
  );
}

function copyDeepHandoff() {
  const block = lastResult?.research?.deep?.handoff_block
    || (lastResult ? buildClientHandoff(lastResult) : '');
  if (!block) {
    showError('コピーする渡す用ブロックがありません。先に周辺MAPを作成してください。');
    return;
  }
  navigator.clipboard.writeText(block).then(
    () => {
      const hint = document.getElementById('deepHint');
      if (hint) {
        hint.textContent =
          'Step1.2渡す用をコピーしました → Raimo Step1.2 → 新しいチャットで Deep Research オン';
      }
    },
    () => showError('クリップボードへのコピーに失敗しました')
  );
}

function buildClientHandoff(result) {
  const lines = [
    `物件名: ${result.property_name || ''}`,
    `住所: ${result.address || ''}`,
    `ターゲット: ${result.target || ''}`,
    '施設候補:',
  ];
  const cands = result.research?.wash?.candidates || result.facilities || [];
  cands.forEach((c) => {
    lines.push(`- ${c.category || ''} | ${c.query || ''} | ${c.name || ''}`);
  });
  return lines.join('\n');
}

function renderFacilityList(result) {
  const intro = document.getElementById('facilityIntro');
  const list = document.getElementById('facilityList');
  const ok = (result.facilities || []).filter((f) => f.ok);
  intro.textContent =
    `周辺施設（確定 ${ok.length} 件）。チェックした施設を除外して下のボタンで地図・下地を更新できます。徒歩分は直線概算です。`;
  list.innerHTML = (result.facilities || [])
    .map((f) => {
      const check = f.needs_check || !f.ok
        ? `<div class="needs-check">${f.ok ? '要確認（徒歩・評判）' : '地図上で未確定'}</div>`
        : '';
      const walk = f.walk_min_approx != null
        ? `<div style="font-size:0.85rem;">徒歩概算: ${walkBandLabel(f.walk_band, f.walk_min_approx)}</div>`
        : '';
      return `<div class="facility-card">
        <div class="exclude-row">
          <input type="checkbox" class="exclude-facility" data-id="${escapeHtml(f.id)}" title="除外する">
          <div style="flex:1">
            <span class="id">${escapeHtml(f.id)}</span><strong>${escapeHtml(f.name)}</strong>
            <div>${escapeHtml(f.blurb || '')}</div>
            <div style="font-size:0.85rem;color:#666">${escapeHtml(f.category || '')} / ${escapeHtml(f.query || '')}</div>
            ${walk}
            ${f.why ? `<div style="font-size:0.85rem;color:#334155">理由: ${escapeHtml(f.why)}</div>` : ''}
            ${check}
          </div>
        </div>
      </div>`;
    })
    .join('');
  const rebuildBtn = document.getElementById('rebuildButton');
  if (rebuildBtn) rebuildBtn.disabled = !(result.facilities || []).length;
}

function renderC0(result) {
  const box = document.getElementById('c0Preview');
  const base = result.images?.c0_base_png_b64;
  const pins = result.images?.c0_with_pins_png_b64;
  const w = result.images?.width || 3508;
  const h = result.images?.height || 2480;
  box.innerHTML = '';
  if (base) {
    box.innerHTML += `<figure><img alt="C0下地" src="data:image/png;base64,${base}"><figcaption>ピンなし下地（C0・A4横 ${w}×${h}）</figcaption></figure>`;
  }
  if (pins) {
    box.innerHTML += `<figure><img alt="C0骨格" src="data:image/png;base64,${pins}"><figcaption>ピン付き骨格（C0・A4横）</figcaption></figure>`;
  }
  document.getElementById('dlC0Base').disabled = !base;
  document.getElementById('dlC0Pins').disabled = !pins;
}

function applyPipelineResult(result) {
  lastResult = result;
  const steps = (lastResult.steps || []).map((s) => `${s.ok ? '✓' : '×'} ${s.id}: ${s.detail || ''}`);
  setProgress(steps);
  document.getElementById('resultsTitle').textContent = `${lastResult.property_name} 周辺MAP`;
  document.getElementById('areaBlurb').textContent = lastResult.area_blurb || '';
  renderResearch(lastResult);
  renderFacilityList(lastResult);
  renderC0(lastResult);
  document.getElementById('resultsSection').style.display = 'block';
  document.getElementById('c1Button').disabled = false;
  const hint = document.getElementById('rebuildHint');
  if (hint) hint.textContent = '';

  apiKey = resolveApiKey();
  if (!apiKey) {
    showError('地図表示用の Maps API Key がありません（下地画像は取得済みです）。');
  } else {
    if (!hasEmbeddedMapsKey()) localStorage.setItem('googleMapsApiKey', apiKey);
    loadGoogleMapsScript(() => renderMapFromResult(lastResult));
  }
}

function getExcludedIds() {
  return Array.from(document.querySelectorAll('.exclude-facility:checked'))
    .map((el) => el.getAttribute('data-id'))
    .filter(Boolean);
}

async function rebuildWithExclusions() {
  if (!lastResult?.job_id) return;
  const base = apiBase();
  if (!base) return;
  const exclude_ids = getExcludedIds();
  if (!exclude_ids.length) {
    showError('除外する施設にチェックを入れてください。');
    return;
  }
  hideError();
  const btn = document.getElementById('rebuildButton');
  const hint = document.getElementById('rebuildHint');
  btn.disabled = true;
  if (hint) hint.textContent = '更新中…';
  try {
    const res = await fetch(`${base}/api/rebuild`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ job_id: lastResult.job_id, exclude_ids }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    applyPipelineResult(data.result);
    if (hint) hint.textContent = `除外 ${exclude_ids.length} 件を反映しました`;
  } catch (err) {
    showError(`更新に失敗しました: ${err.message || err}`);
    if (hint) hint.textContent = '';
    btn.disabled = false;
  }
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
    let res;
    try {
      res = await fetch(`${base}/api/run`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ property_name, address, target, facility_count }),
      });
    } catch (netErr) {
      throw new Error(
        `APIに接続できません（${base}）。./scripts/shuhen_auto_open.sh でサーバを起動し直してください。詳細: ${netErr.message || netErr}`
      );
    }
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    lastResult = data.result;
    applyPipelineResult(lastResult);
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
