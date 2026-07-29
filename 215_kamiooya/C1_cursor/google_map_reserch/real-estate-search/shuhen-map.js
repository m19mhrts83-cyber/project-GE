// 周辺MAP 番号ピン（project-GE 別ページ。管理会社検索 app.js とは独立）
let map;
let markers = [];
let infoWindow;
let apiKey = '';
let lastCoords = [];
let mapOnly = false;
let lastPropertyCenter = null;
let lastMapBounds = null;

/** POI・丁目・道名・駅名など文字を抑えたスタイル（道路・線路の線は残す＝下地寄り） */
const CLEAN_MAP_STYLES = [
    // 店・施設アイコン
    { featureType: 'poi', stylers: [{ visibility: 'off' }] },
    { featureType: 'poi.business', stylers: [{ visibility: 'off' }] },
    { featureType: 'poi.attraction', stylers: [{ visibility: 'off' }] },
    { featureType: 'poi.park', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    // 丁目・町名・区画などの行政ラベル（1丁目・2丁目など）
    { featureType: 'administrative', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    { featureType: 'administrative.neighborhood', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    { featureType: 'administrative.land_parcel', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    { featureType: 'administrative.locality', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    // 地形・水系の文字
    { featureType: 'landscape', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    { featureType: 'water', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    // 道路名（環状線など）も下地ではオフ。線そのものは残す
    { featureType: 'road', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    { featureType: 'road', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
    // 駅名・路線名ラベルはオフ（線路・駅の形は残す）
    { featureType: 'transit', elementType: 'labels', stylers: [{ visibility: 'off' }] },
    { featureType: 'transit', elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
    { featureType: 'transit.station', elementType: 'labels', stylers: [{ visibility: 'off' }] },
];

const GRANDOLE_PRESET = {
    address: '愛知県名古屋市北区長田町4丁目69番地5',
    label: 'Grandole志賀本通',
    places: [
        { id: 'P1', query: '地下鉄 志賀本通駅 名古屋', name: '志賀本通駅' },
        { id: 'P2', query: '名鉄 尼ケ坂駅', name: '尼ケ坂駅／SAKUMACHI' },
        { id: 'P3', query: 'ナフコトミダ 杉栄店', name: 'ナフコトミダ杉栄店' },
        { id: 'P4', query: 'ドラッグスギヤマ 杉栄店', name: 'ドラッグスギヤマ杉栄店' },
        { id: 'P5', query: 'つばめパン＆Milk 尼ケ坂', name: 'つばめパン＆Milk' },
        { id: 'P6', query: 'Cafe de Lyon Palette 尼ケ坂', name: 'Cafe de Lyon Palette' },
        { id: 'P7', query: 'つけそば 神宮寺 志賀本通', name: 'つけそば 神宮寺' },
        { id: 'P8', query: 'コノズコーヒー 志賀本通', name: 'コノズコーヒー' },
    ],
};

document.addEventListener('DOMContentLoaded', () => {
    const savedApiKey = localStorage.getItem('googleMapsApiKey');
    if (savedApiKey) {
        document.getElementById('apiKeyInput').value = savedApiKey;
        apiKey = savedApiKey;
    }
    document.getElementById('apiKeyInput').addEventListener('change', (e) => {
        apiKey = e.target.value.trim();
        localStorage.setItem('googleMapsApiKey', apiKey);
    });
    const cleanToggle = document.getElementById('cleanStyleToggle');
    const hidePinsToggle = document.getElementById('hidePinsToggle');
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
    loadGrandolePreset();
});

function isCleanStyleOn() {
    const el = document.getElementById('cleanStyleToggle');
    return el ? el.checked : true;
}

function isHidePinsOn() {
    const el = document.getElementById('hidePinsToggle');
    return el ? el.checked : false;
}

function applyMapDisplayOptions() {
    if (!map) return;
    map.setOptions({ styles: isCleanStyleOn() ? CLEAN_MAP_STYLES : [] });
    const hide = isHidePinsOn();
    markers.forEach((m) => m.setMap(hide ? null : map));
}

function loadGrandolePreset() {
    document.getElementById('propertyAddress').value = GRANDOLE_PRESET.address;
    document.getElementById('propertyLabel').value = GRANDOLE_PRESET.label;
    document.getElementById('placesList').value = GRANDOLE_PRESET.places
        .map((p) => `${p.id} | ${p.query} | ${p.name}`)
        .join('\n');
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
        showError('Google Maps APIの読み込みに失敗しました。APIキーを確認してください。');
    };
    document.head.appendChild(script);
}

function clearMarkers() {
    markers.forEach((m) => m.setMap(null));
    markers = [];
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

async function runNumberedPins() {
    const currentApiKey = document.getElementById('apiKeyInput').value.trim();
    const address = document.getElementById('propertyAddress').value.trim();
    const propertyLabel = document.getElementById('propertyLabel').value.trim() || '物件';
    const places = parsePlacesList(document.getElementById('placesList').value);

    if (!currentApiKey) {
        showError('Google Maps API Keyを入力してください。');
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
    localStorage.setItem('googleMapsApiKey', apiKey);
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
            // 周辺MAP用: 広がりすぎ防止（試走のスクショが市域全体になるのを防ぐ）
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
