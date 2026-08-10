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
    const splitBtn = document.getElementById('bulkSplitButton');
    if (splitBtn) {
        splitBtn.addEventListener('click', () => {
            applyBulkPasteToFields();
        });
    }
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

/** 全角縦棒などを半角 | に揃える（Step1.2／デモコピペの揺れ対策） */
function normalizePipes(text) {
    return String(text || '')
        .replace(/\uFF5C/g, '|') // ｜ FULLWIDTH VERTICAL LINE
        .replace(/\u2502/g, '|') // │ BOX DRAWINGS
        .replace(/\u2503/g, '|');
}

function looksLikeAddressLine(line) {
    const t = String(line || '').trim();
    if (!t || t.includes('|')) return false;
    return /[都道府県]/.test(t) || /市|区|町|村/.test(t) || /^〒/.test(t);
}

function looksLikePlaceLine(line) {
    const t = normalizePipes(line).trim();
    if (!t) return false;
    if (/^#{1,6}\s/.test(t)) return false;
    if (/^=====/.test(t) || /^-----/.test(t)) return false;
    if (/^(使い方|アプリ:|補足|Access参考|※)/i.test(t)) return false;
    if (/物件住所|物件ラベル|施設リスト|店・施設リスト|Step1\.2|コピペ/.test(t)) return false;
    if (/^（/.test(t) && t.includes('）')) return false;
    const parts = t.split('|').map((s) => s.trim()).filter(Boolean);
    if (parts.length >= 2) return true;
    // P1 だけの行は施設行とみなさない
    return false;
}

function extractFencedBlocks(text) {
    const blocks = [];
    const re = /```[^\n]*\n?([\s\S]*?)```/g;
    let m;
    while ((m = re.exec(text))) {
        const body = (m[1] || '').trim();
        if (body) blocks.push(body);
    }
    return blocks;
}

/**
 * Step1.2 の ## E 全文／デモ txt／3欄バラバラ、いずれでも住所・ラベル・施設行に分解する。
 * @returns {{ address: string, label: string, placesText: string, placeCount: number, warnings: string[] }}
 */
function parseBulkStep2Input(raw) {
    const text = normalizePipes(raw).trim();
    const warnings = [];
    let address = '';
    let label = '';
    let placeLines = [];

    if (!text) {
        return { address, label, placesText: '', placeCount: 0, warnings };
    }

    // デモ／手順用: ===== 物件住所 ===== 形式
    const addrSec = text.match(/=====\s*物件住所\s*=====\s*\r?\n([^\r\n=]+)/);
    const labelSec = text.match(/=====\s*物件ラベル[^\n=]*=====\s*\r?\n([^\r\n=]+)/);
    const listSec = text.match(
        /=====\s*(?:店・)?施設リスト[^\n=]*=====\s*\r?\n([\s\S]*?)(?=\r?\n=====|\r?\n-----|\r?\nAccess|$)/i
    );
    if (addrSec) address = addrSec[1].trim();
    if (labelSec) label = labelSec[1].trim();
    if (listSec) {
        placeLines = listSec[1]
            .split(/\r?\n/)
            .map((l) => l.trim())
            .filter(looksLikePlaceLine);
    }

    // Markdown の ``` コードブロック（## E の E-1/E-2/E-3）
    const blocks = extractFencedBlocks(text);
    if (blocks.length) {
        const singleLines = [];
        const multiPlace = [];
        for (const b of blocks) {
            const lines = b
                .split(/\r?\n/)
                .map((l) => l.trim())
                .filter(Boolean);
            if (lines.length === 1 && !lines[0].includes('|')) {
                singleLines.push(lines[0]);
            } else if (lines.some((l) => looksLikePlaceLine(l))) {
                multiPlace.push(...lines.filter(looksLikePlaceLine));
            }
        }
        if (!address) {
            const a = singleLines.find(looksLikeAddressLine);
            if (a) address = a;
        }
        if (!label) {
            const rest = singleLines.filter((l) => l !== address);
            if (rest.length) label = rest[0];
        }
        if (!placeLines.length && multiPlace.length) placeLines = multiPlace;
    }

    // 見出し付きプレーン（### E-1. 物件住所 の次行、など）
    if (!address) {
        const m = text.match(/(?:E-1[^\n]*物件住所|物件住所)[^\n]*\r?\n+([^\r\n`#=]+)/i);
        if (m && looksLikeAddressLine(m[1])) address = m[1].trim();
    }
    if (!label) {
        const m = text.match(/(?:E-2[^\n]*物件ラベル|物件ラベル\s*\(?P0\)?)[^\n]*\r?\n+([^\r\n`#=|]+)/i);
        if (m) label = m[1].trim();
    }

    // フォールバック: 全文から施設行／住所行を拾う
    if (!placeLines.length) {
        placeLines = text
            .split(/\r?\n/)
            .map((l) => l.trim())
            .filter(looksLikePlaceLine);
    }
    if (!address) {
        const a = text
            .split(/\r?\n/)
            .map((l) => l.trim().replace(/^住所[:：]\s*/, ''))
            .find(looksLikeAddressLine);
        if (a) address = a;
    }
    if (!label) {
        const m = text.match(/(?:物件名|ラベル)[:：]\s*([^\r\n|]+)/);
        if (m) label = m[1].trim();
    }

    // ゴミ行が施設に紛れたときの警告
    const junkish = placeLines.filter((l) => l.split('|').length < 2);
    if (junkish.length) {
        warnings.push('施設行に縦棒（|）が無い行があります。未ヒットになりやすいです。');
    }
    if (placeLines.length === 0) {
        warnings.push('施設リスト行（例: P1 | 検索クエリ | 表示名）が見つかりません。');
    }
    if (!address) {
        warnings.push('物件住所が見つかりません。');
    }

    return {
        address,
        label,
        placesText: placeLines.join('\n'),
        placeCount: placeLines.length,
        warnings,
    };
}

/** 一括欄の内容を3欄へ振り分け。成功時 true */
function applyBulkPasteToFields() {
    const bulkEl = document.getElementById('bulkStep2Paste');
    const raw = (bulkEl && bulkEl.value.trim()) || '';
    // 一括が空なら、施設リスト欄に ## E 全文が入っているケースを救済
    const placesEl = document.getElementById('placesList');
    const source =
        raw ||
        (placesEl &&
        (placesEl.value.includes('=====') ||
            placesEl.value.includes('```') ||
            placesEl.value.includes('## E') ||
            placesEl.value.includes('物件住所'))
            ? placesEl.value
            : '');
    if (!source.trim()) {
        showError('「## E 一括貼付」欄に Step1.2 の ## E 全文（またはデモ用 txt）を貼ってから「振り分け」を押してください。');
        return false;
    }
    const parsed = parseBulkStep2Input(source);
    const addrEl = document.getElementById('propertyAddress');
    const labelEl = document.getElementById('propertyLabel');
    if (parsed.address && addrEl) addrEl.value = parsed.address;
    if (parsed.label && labelEl) labelEl.value = parsed.label;
    if (parsed.placesText && placesEl) placesEl.value = parsed.placesText;
    if (bulkEl && raw) {
        // 振り分け後も一括欄は残す（再実行用）
    }
    if (!parsed.address || parsed.placeCount === 0) {
        showError(
            '振り分けに失敗しました。' +
                (parsed.warnings.length ? parsed.warnings.join(' ') : '') +
                ' E-1住所・E-2物件名・E-3の「P1 | クエリ | 表示名」形式を確認してください。'
        );
        return false;
    }
    hideError();
    const tip = document.getElementById('bulkPasteStatus');
    if (tip) {
        tip.textContent = `振り分け完了: 住所あり / ラベル「${parsed.label || '（空）'}」 / 施設 ${parsed.placeCount} 行` +
            (parsed.warnings.length ? ` ※${parsed.warnings[0]}` : '');
    }
    return true;
}

function parsePlacesList(text) {
    return normalizePipes(text)
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => looksLikePlaceLine(line))
        .map((line) => {
            const parts = line.split('|').map((s) => s.trim()).filter(Boolean);
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
    const run = () => {
        Promise.resolve()
            .then(() => callback())
            .catch((err) => {
                console.error(err);
                showError(`エラー: ${err.message || err}`);
            });
    };
    if (typeof google !== 'undefined' && google.maps) {
        run();
        return;
    }
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&language=ja`;
    script.async = true;
    script.defer = true;
    script.onload = run;
    script.onerror = () => {
        showError(
            'Google Maps APIの読み込みに失敗しました。APIキー／HTTPリファラ制限／Maps JavaScript API の有効化を確認してください。'
        );
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

/** Maps コールバックが返らない（リファラ拒否・ネットワーク等）ときの無限待ち防止 */
function withTimeout(promise, ms, label) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            reject(
                new Error(
                    `${label}がタイムアウトしました（${Math.round(ms / 1000)}秒）。` +
                        'Google Cloud の APIキー制限を確認してください' +
                        '（HTTPリファラに Pages URL／Raimo URL があるか、' +
                        'Maps JavaScript / Places / Geocoding が有効か）。'
                )
            );
        }, ms);
        promise.then(
            (value) => {
                clearTimeout(timer);
                resolve(value);
            },
            (err) => {
                clearTimeout(timer);
                reject(err);
            }
        );
    });
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
                    status: String(status),
                });
            } else {
                resolve({ ok: false, status: String(status) });
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
                        status: String(status),
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
    let address = document.getElementById('propertyAddress').value.trim();
    let places = parsePlacesList(document.getElementById('placesList').value);
    const bulkRaw = (document.getElementById('bulkStep2Paste') || {}).value || '';

    // 住所が空／施設0件／一括欄あり → 自動振り分け（## E 全文の手分け忘れ対策）
    const placesRaw = document.getElementById('placesList').value;
    const needBulk =
        Boolean(bulkRaw.trim()) ||
        (!address && placesRaw.trim()) ||
        (places.length === 0 && placesRaw.trim());
    if (needBulk) {
        const ok = applyBulkPasteToFields();
        if (!ok && !document.getElementById('propertyAddress').value.trim()) return;
        address = document.getElementById('propertyAddress').value.trim();
        places = parsePlacesList(document.getElementById('placesList').value);
    }

    const propertyLabel = document.getElementById('propertyLabel').value.trim() || '物件';

    if (!currentApiKey) {
        showError(
            hasEmbeddedMapsKey()
                ? '運営キーの注入に失敗しています。Pages の Secret を確認してください。'
                : 'Google Maps API Keyを入力してください（ローカル開発用）。'
        );
        return;
    }
    if (!address) {
        showError(
            '物件住所が空です。「## E 一括貼付」に Step1.2 の ## E 全文を貼るか、物件住所欄へ E-1 を入れてください。'
        );
        return;
    }
    if (places.length === 0) {
        showError(
            '施設リストが空、または形式が不正です。1行を「P1 | 検索クエリ | 表示名」（半角|）にしてください。全角｜や見出しだけの貼付は失敗します。'
        );
        return;
    }
    const weak = places.filter((p) => p.id === '?' || !p.query);
    if (weak.length >= Math.max(2, Math.ceil(places.length / 2))) {
        showError(
            `施設行の形式が崩れている可能性が高いです（${weak.length}/${places.length} 行）。## E の E-3 だけ、または「振り分け」後のリストを確認してください。`
        );
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
            const geo = await withTimeout(geocodeAddress(address), 15000, 'ジオコード（住所→座標）');
            if (!geo || geo.lat == null) {
                const st = geo && geo.status ? `（${geo.status}）` : '';
                showError(
                    `物件住所のジオコードに失敗しました${st}。` +
                        '住所表記を見直すか、Geocoding API／リファラ制限を確認してください。'
                );
                return;
            }
            const property = geo;

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

            const placeStatuses = [];
            for (const p of places) {
                const found = await withTimeout(
                    findPlace(p.query, bias),
                    12000,
                    `施設検索「${p.id}」`
                );
                if (!found.ok) placeStatuses.push(`${p.id}:${found.status || 'FAIL'}`);
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
            await withTimeout(updateWalkRoute(rows), 15000, '徒歩動線');
            document.getElementById('mapOnlyButton').disabled = false;
            document.getElementById('copyJsonButton').disabled = false;
            const applyBtn = document.getElementById('applyStyleButton');
            if (applyBtn) applyBtn.disabled = false;

            const denied = placeStatuses.filter((s) =>
                /REQUEST_DENIED|OVER_QUERY_LIMIT|UNKNOWN_ERROR/.test(s)
            );
            const okPlaces = rows.filter((r) => !r.isProperty && r.ok).length;
            if (denied.length && okPlaces === 0) {
                showError(
                    `施設検索がAPI制限で全滅しました: ${denied.slice(0, 4).join(', ')}` +
                        '。Places API の有効化・日次クォータ・HTTPリファラ制限を確認してください。'
                );
            } else if (denied.length) {
                const tip = document.getElementById('resultsCount');
                if (tip) {
                    tip.textContent +=
                        `　※API制限の失敗あり（${denied.slice(0, 2).join(', ')}）。リファラ／クォータを確認。`;
                }
            }
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
    let countMsg = `成功 ${okRows.length} 件` + (failCount ? ` / 失敗 ${failCount} 件` : '');
    if (clean) {
        countMsg += '　※クリーン表示ON：地図上の地名ラベルはオフです（ピンは表示）。地名も見る場合はトグルを外して「表示を更新」';
    }
    if (isHidePinsOn()) {
        countMsg += '　※「ピンを隠す」ON中';
    }
    document.getElementById('resultsCount').textContent = countMsg;

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
