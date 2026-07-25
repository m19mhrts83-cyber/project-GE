// 周辺MAP 番号ピン（project-GE 別ページ。管理会社検索 app.js とは独立）
// Pages ビルド時は「代入行の値だけ」を運営キーへ置換する（判定用プレースホルダ文字列は触らない）。
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
let mapOnly = false;
let lastPropertyCenter = null;
let lastMapBounds = null;

/** POI・丁目・道名・駅名など文字を抑えたスタイル（道路・線路の線は残す＝下地寄り） */
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

document.addEventListener('DOMContentLoaded', () => {
    syncApiKeyUi();
    const input = document.getElementById('apiKeyInput');
    if (input && !hasEmbeddedMapsKey()) {
        input.addEventListener('change', (e) => {
            apiKey = e.target.value.trim();
            localStorage.setItem('googleMapsApiKey', apiKey);
        });
    }
    const cleanToggle = document.getElementById('cleanStyleToggle');
    const hidePinsToggle = document.getElementById('hidePinsToggle');
    const routeToggle = document.getElementById('walkRouteToggle');
    if (cleanToggle) {
        const savedClean = localStorage.getItem('shuhenCleanStyle');
        if (savedClean !== null) cleanToggle.checked = savedClean === '1';
        cleanToggle.addEventListener('change', () => {
            localStorage.setItem('shuhenCleanStyle', cleanToggle.checked ? '1' : '0');
            applyMapDisplayOptions();
        });
    }
    if (hidePinsToggle) {
        hidePinsToggle.addEventListener('change', () => applyMapDisplayOptions());
    }
    if (routeToggle) {
        const savedRoute = localStorage.getItem('shuhenWalkRoute');
        if (savedRoute !== null) routeToggle.checked = savedRoute === '1';
        routeToggle.addEventListener('change', () => {
            localStorage.setItem('shuhenWalkRoute', routeToggle.checked ? '1' : '0');
            if (lastCoords.length && map) {
                updateWalkRoute(lastCoords).catch((err) => console.error(err));
            }
        });
    }
});

function isCleanStyleOn() {
    const el = document.getElementById('cleanStyleToggle');
    return el ? el.checked : true;
}

function isHidePinsOn() {
    const el = document.getElementById('hidePinsToggle');
    return el ? el.checked : false;
}

function isWalkRouteOn() {
    const el = document.getElementById('walkRouteToggle');
    return el ? el.checked : false;
}

function applyMapDisplayOptions() {
    if (!map) return;
    map.setOptions({ styles: isCleanStyleOn() ? CLEAN_MAP_STYLES : [] });
    const hide = isHidePinsOn();
    markers.forEach((m) => m.setMap(hide ? null : map));
    if (routePolyline) routePolyline.setMap(map);
    if (routeInfoMarker) routeInfoMarker.setMap(hide ? null : map);
}

function parsePlacesList(text) {
    return text
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
            const parts = line.split('|').map((s) => s.trim());
            if (parts.length >= 3) {
                return { id: parts[0], query: parts[1], name: parts[2] };
            }
            if (parts.length === 2) {
                return { id: parts[0], query: parts[1], name: parts[1] };
            }
            return { id: '?', query: parts[0], name: parts[0] };
        });
}

function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    document.getElementById('resultsSection').style.display = 'none';
    resetPinButton();
}

function hideError() {
    document.getElementById('errorMessage').style.display = 'none';
}

function setPinButtonLoading(loading) {
    const button = document.getElementById('pinButton');
    const buttonText = button.querySelector('.button-text');
    const spinner = button.querySelector('.loading-spinner');
    button.disabled = loading;
    buttonText.style.display = loading ? 'none' : 'inline';
    spinner.style.display = loading ? 'inline' : 'none';
}

function resetPinButton() {
    setPinButtonLoading(false);
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
    script.onerror = () => {
        showError('Google Maps APIの読み込みに失敗しました。APIキー／制限設定を確認してください。');
    };
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

function geocodeAddress(address) {
    return new Promise((resolve) => {
        const geocoder = new google.maps.Geocoder();
        geocoder.geocode({ address, region: 'jp' }, (results, status) => {
            if (status === 'OK' && results[0]) {
                resolve({
                    lat: results[0].geometry.location.lat(),
                    lng: results[0].geometry.location.lng(),
                    formatted: results[0].formatted_address,
                });
            } else {
                resolve(null);
            }
        });
    });
}

function findPlace(query, biasLatLng) {
    return new Promise((resolve) => {
        const service = new google.maps.places.PlacesService(document.createElement('div'));
        service.findPlaceFromQuery(
            {
                query,
                fields: ['name', 'geometry', 'formatted_address', 'place_id'],
                locationBias: biasLatLng,
            },
            (results, status) => {
                if (status === google.maps.places.PlacesServiceStatus.OK && results && results[0]) {
                    const r = results[0];
                    resolve({
                        name: r.name,
                        lat: r.geometry.location.lat(),
                        lng: r.geometry.location.lng(),
                        formatted: r.formatted_address || '',
                        placeId: r.place_id || '',
                        ok: true,
                    });
                } else {
                    resolve({ ok: false, status: String(status) });
                }
            }
        );
    });
}

function looksLikeStation(row) {
    if (!row || row.isProperty) return false;
    const blob = `${row.id || ''} ${row.name || ''} ${row.query || ''} ${row.resolvedName || ''}`;
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
                if (status === 'OK' && result && result.routes && result.routes[0]) {
                    resolve(result);
                } else {
                    resolve(null);
                }
            }
        );
    });
}

function pathToLatLngLiteral(overviewPath) {
    return overviewPath.map((p) => ({ lat: p.lat(), lng: p.lng() }));
}

async function updateWalkRoute(rows) {
    clearRouteOverlay();
    const summary = document.getElementById('routeSummary');
    if (!isWalkRouteOn()) {
        if (summary) summary.textContent = '徒歩動線: OFF';
        return;
    }
    if (!map || !google || !google.maps) return;

    const property = rows.find((r) => r.isProperty && r.ok && r.lat != null);
    const stations = rows.filter((r) => r.ok && r.lat != null && looksLikeStation(r));
    if (!property) {
        if (summary) summary.textContent = '徒歩動線: 物件ピンがありません';
        return;
    }
    if (!stations.length) {
        if (summary) summary.textContent = '徒歩動線: 駅候補がリストにありません（名称に「駅」を含めてください）';
        return;
    }

    const origin = { lat: property.lat, lng: property.lng };
    let best = null;
    for (const st of stations) {
        const dest = { lat: st.lat, lng: st.lng };
        const result = await requestWalkingRoute(dest, origin);
        if (!result) continue;
        const leg = result.routes[0].legs[0];
        const meters = leg.distance ? leg.distance.value : Number.POSITIVE_INFINITY;
        const seconds = leg.duration ? leg.duration.value : Number.POSITIVE_INFINITY;
        if (!best || meters < best.meters) {
            best = {
                station: st,
                result,
                meters,
                seconds,
                distanceText: leg.distance ? leg.distance.text : '',
                durationText: leg.duration ? leg.duration.text : '',
            };
        }
    }

    if (!best) {
        if (summary) summary.textContent = '徒歩動線: Directions 取得に失敗（API有効化を確認）';
        return;
    }

    const path = pathToLatLngLiteral(best.result.routes[0].overview_path);
    routePolyline = new google.maps.Polyline({
        path,
        geodesic: true,
        strokeColor: '#c0392b',
        strokeOpacity: 0.95,
        strokeWeight: 5,
        map,
        zIndex: 50,
    });

    const mid = path[Math.floor(path.length / 2)] || origin;
    routeInfoMarker = new google.maps.Marker({
        map: isHidePinsOn() ? null : map,
        position: mid,
        label: {
            text: best.durationText || '徒歩',
            color: '#fff',
            fontSize: '11px',
            fontWeight: '700',
        },
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 18,
            fillColor: '#c0392b',
            fillOpacity: 0.95,
            strokeColor: '#fff',
            strokeWeight: 2,
        },
        zIndex: 60,
    });

    lastRoute = {
        mode: 'WALKING',
        fromStationId: best.station.id,
        fromStationName: best.station.name,
        toPropertyId: 'P0',
        distanceText: best.distanceText,
        durationText: best.durationText,
        meters: best.meters,
        seconds: best.seconds,
        path,
    };

    if (summary) {
        summary.textContent = `徒歩動線: ${best.station.id} ${best.station.name} → 物件（約${best.durationText} / ${best.distanceText}）`;
    }
}

async function runNumberedPins() {
    const currentApiKey = resolveApiKey();
    const address = document.getElementById('propertyAddress').value.trim();
    const propertyLabel = document.getElementById('propertyLabel').value.trim() || '物件';
    const places = parsePlacesList(document.getElementById('placesList').value);

    if (!currentApiKey) {
        showError(
            hasEmbeddedMapsKey()
                ? '運営キーの注入に失敗しています。Pages の Secret を確認してください。'
                : 'Google Maps API Keyを入力してください（ローカル開発用）。'
        );
        return;
    }
    if (!address) {
        showError('物件住所を入力してください。');
        return;
    }
    if (places.length === 0) {
        showError('店・施設リストを1行以上入力してください。');
        return;
    }

    apiKey = currentApiKey;
    if (!hasEmbeddedMapsKey()) {
        localStorage.setItem('googleMapsApiKey', apiKey);
    }
    hideError();
    setPinButtonLoading(true);

    loadGoogleMapsScript(async () => {
        try {
            const property = await geocodeAddress(address);
            if (!property) {
                showError('物件住所のジオコードに失敗しました。');
                return;
            }

            const bias = new google.maps.LatLng(property.lat, property.lng);
            const rows = [
                {
                    id: 'P0',
                    query: address,
                    name: propertyLabel,
                    lat: property.lat,
                    lng: property.lng,
                    formatted: property.formatted,
                    ok: true,
                    isProperty: true,
                },
            ];

            for (const p of places) {
                const found = await findPlace(p.query, bias);
                rows.push({
                    id: p.id,
                    query: p.query,
                    name: p.name,
                    lat: found.ok ? found.lat : null,
                    lng: found.ok ? found.lng : null,
                    formatted: found.ok ? found.formatted : '',
                    resolvedName: found.ok ? found.name : '',
                    ok: found.ok,
                    status: found.status || '',
                    isProperty: false,
                });
            }

            lastCoords = rows;
            lastPropertyCenter = property;
            renderMapAndList(property, rows);
            await updateWalkRoute(rows);
            document.getElementById('mapOnlyButton').disabled = false;
            document.getElementById('copyJsonButton').disabled = false;
            const applyBtn = document.getElementById('applyStyleButton');
            if (applyBtn) applyBtn.disabled = false;
            resetPinButton();
        } catch (err) {
            console.error(err);
            showError(`エラー: ${err.message || err}`);
        }
    });
}

function renderMapAndList(property, rows) {
    clearMarkers();
    clearRouteOverlay();
    infoWindow = new google.maps.InfoWindow();

    const clean = isCleanStyleOn();
    map = new google.maps.Map(document.getElementById('map'), {
        center: { lat: property.lat, lng: property.lng },
        zoom: 15,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: true,
        styles: clean ? CLEAN_MAP_STYLES : [],
    });

    const bounds = new google.maps.LatLngBounds();
    const okRows = rows.filter((r) => r.ok && r.lat != null);
    const showPins = !isHidePinsOn();

    okRows.forEach((r) => {
        const pos = { lat: r.lat, lng: r.lng };
        bounds.extend(pos);
        const marker = new google.maps.Marker({
            map: showPins ? map : null,
            position: pos,
            title: `${r.id} ${r.name}`,
            icon: numberedIcon(r.id, r.isProperty),
            zIndex: r.isProperty ? 1000 : 100,
        });
        marker.addListener('click', () => {
            infoWindow.setContent(
                `<div style="padding:4px 8px"><strong>${r.id}</strong> ${r.name}<br><small>${r.formatted || ''}</small></div>`
            );
            infoWindow.open(map, marker);
        });
        markers.push(marker);
    });

    if (okRows.length > 1) {
        map.fitBounds(bounds, 64);
        lastMapBounds = bounds;
        google.maps.event.addListenerOnce(map, 'idle', () => {
            const z = map.getZoom();
            if (typeof z === 'number' && z < 14) map.setZoom(14);
            if (typeof z === 'number' && z > 16) map.setZoom(16);
            lastMapBounds = map.getBounds();
        });
    }

    const failCount = rows.filter((r) => !r.ok).length;
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('resultsTitle').textContent = `${property.formatted || '物件'} 周辺`;
    document.getElementById('resultsCount').textContent =
        `成功 ${okRows.length} 件` + (failCount ? ` / 失敗 ${failCount} 件` : '');

    const list = document.getElementById('pinList');
    list.innerHTML = rows
        .map((r) => {
            if (r.ok) {
                return `<div class="result-card">
                    <h3>${r.id} — ${r.name}</h3>
                    <p>${r.resolvedName && r.resolvedName !== r.name ? `Maps名: ${r.resolvedName}<br>` : ''}
                    ${r.formatted}<br>
                    <small>${r.lat.toFixed(6)}, ${r.lng.toFixed(6)}</small></p>
                </div>`;
            }
            return `<div class="result-card result-card-fail">
                <h3>${r.id} — ${r.name}（未ヒット）</h3>
                <p>検索語: ${r.query}<br><small>status: ${r.status || 'UNKNOWN'}</small></p>
            </div>`;
        })
        .join('');
}

function toggleMapOnly() {
    mapOnly = !mapOnly;
    document.body.classList.toggle('map-only-mode', mapOnly);
    document.getElementById('mapOnlyBar').style.display = mapOnly ? 'flex' : 'none';
    const btn = document.getElementById('mapOnlyButton');
    if (btn) btn.textContent = mapOnly ? '通常表示に戻す' : 'マップのみ表示';
    if (map) {
        setTimeout(() => google.maps.event.trigger(map, 'resize'), 100);
    }
}

function copyCoordsJson() {
    if (!lastCoords.length) return;
    const payload = {
        generatedAt: new Date().toISOString(),
        property: lastCoords.find((r) => r.id === 'P0') || null,
        pins: lastCoords,
        walkRoute: lastRoute,
    };
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2)).then(
        () => {
            const btn = document.getElementById('copyJsonButton');
            const prev = btn.textContent;
            btn.textContent = 'コピーしました';
            setTimeout(() => {
                btn.textContent = prev;
            }, 1500);
        },
        () => showError('クリップボードへのコピーに失敗しました。')
    );
}
