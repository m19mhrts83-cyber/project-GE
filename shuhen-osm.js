// 周辺MAP 叩き台（OpenStreetMap版・試作）
// 構成案B: AI（ネタ出し・実在確認）は会員のチャット、ここは「表 → 地図・番号ピン・一覧・徒歩分 → A4」だけを担う。
// サーバ不要。外部に出るのは地図タイル・住所検索・経路計算の3つだけで、本展開時は CONFIG を商用プランへ差し替える。

const CONFIG = {
    // 試験公開（30〜50人）までは OSM 財団の無料配信。本展開時は商用プラン（Stadia Maps / MapTiler 等）の URL＋ドメイン制限キーへ。
    tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    geocodeUrl: 'https://nominatim.openstreetmap.org/search',
    walkRouteUrl: 'https://routing.openstreetmap.de/routed-foot/route/v1/driving/',
    carRouteUrl: 'https://routing.openstreetmap.de/routed-car/route/v1/driving/',
    geocodeIntervalMs: 1100, // Nominatim 利用規約: 1秒1件まで
    metersPerMinute: 80, // 不動産公取規約: 80m＝1分（端数切り上げ）
    credit: '地図データ © OpenStreetMap contributors（https://www.openstreetmap.org/copyright）',
};

const SAMPLE = {
    name: 'Grandole志賀本通',
    addr: '愛知県名古屋市北区長田町4丁目69番地5',
    area: '名城線と瀬戸線に挟まれた生活至便な立地。平日は栄へスマート通勤、休日はSAKUMACHI商店街でカフェ巡りを楽しめる街です。',
    table: [
        '| 掲載 | 区分 | 施設名 | 種類 | 住所・目印 | 吹き出し | 確認 |',
        '| --- | --- | --- | --- | --- | --- | --- |',
        '| ○ | 徒歩 | 志賀本通駅 | 駅 | 名古屋市北区 地下鉄名城線 | 栄まで地下鉄で直通。通勤に使いやすい駅です | 確認済み |',
        '| ○ | 徒歩 | 尼ヶ坂駅 | 駅 | 名古屋市北区 名鉄瀬戸線 | 高架下のSAKUMACHI商店街の最寄り駅です | 確認済み |',
        '| ○ | 徒歩 | ナフコトミダ 杉栄店 | スーパー | 名古屋市北区杉栄町 | 徒歩3分で大抵の買い物が済みます | 確認済み |',
        '| ○ | 徒歩 | ドラッグスギヤマ 杉栄店 | ドラッグストア | 名古屋市北区杉栄町 | 日用品やコスメがすぐ揃います | 確認済み |',
        '| ○ | 徒歩 | つばめパン&Milk | パン屋 | 名古屋市北区 尼ヶ坂駅高架下 | ふわもち食パンのモーニングが人気です | 確認済み |',
        '| ○ | 徒歩 | Cafe de Lyon Palette | カフェ | 名古屋市北区 SAKUMACHI商店街 | 旬のフルーツを使ったパフェが楽しめます | 確認済み |',
        '| ○ | 徒歩 | つけそば 神宮寺 | 飲食店 | 名古屋市北区若葉通 | 仕事帰りに寄れる、評判のつけそば店です | 確認済み |',
        '| ○ | 徒歩 | 名古屋市北区役所 | 役所 | 名古屋市北区清水4丁目 | 各種手続きはこちらで | 確認済み |',
        '| ○ | 吹き出し | | | | 朝は駅前でモーニング、帰りはナフコで買い物 |  |',
        '| ○ | 吹き出し | | | | 休日は高架下の商店街でカフェ巡り |  |',
    ].join('\n'),
};

let editMap = null;
let markerLayer = null;
let property = null; // {name, lat, lng}
let rows = []; // {no, kind:'walk'|'car', name, type, hint, note, lat, lng, approx, minutes, minutesApprox, route}
let bubbles = [];
let sheetDataUrl = null;

const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const setStatus = text => { $('status').textContent = text; };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------- 表の読み取り ----------

function splitRow(line) {
    if (line.includes('|')) {
        return line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(s => s.trim());
    }
    return line.split('\t').map(s => s.trim());
}

function parseTable(text) {
    const lines = text.split(/\r?\n/).filter(l => l.includes('|') || l.includes('\t'));
    const headerIdx = lines.findIndex(l => /施設名/.test(l));
    if (headerIdx < 0) throw new Error('表の見出し行（「施設名」を含む行）が見つかりません。');
    const head = splitRow(lines[headerIdx]);
    const col = re => head.findIndex(h => re.test(h));
    const c = {
        kind: col(/区分|徒歩|車/),
        name: col(/施設名|名称/),
        type: col(/種類|カテゴリ|ジャンル/),
        hint: col(/住所|目印|場所/),
        note: col(/吹き出し|コメント|一言/),
        keep: col(/掲載|載せる|○×/),
        check: col(/^確認/),
    };
    const out = [];
    const extra = [];
    for (const line of lines.slice(headerIdx + 1)) {
        const cells = splitRow(line);
        if (cells.every(s => /^:?-{2,}:?$/.test(s) || s === '')) continue;
        const get = i => (i >= 0 ? (cells[i] || '') : '');
        const kindText = get(c.kind);
        const note = get(c.note);
        if (/吹き出し/.test(kindText)) { if (note) extra.push(note); continue; }
        const name = get(c.name);
        if (!name) continue;
        if (/^[×✕xX]/.test(get(c.keep).trim())) continue; // ③で「載せない」にした行
        out.push({ kind: /車/.test(kindText) ? 'car' : 'walk', name, type: get(c.type), hint: get(c.hint), note, unchecked: /要確認/.test(get(c.check)) });
    }
    if (!out.length) throw new Error('施設の行が読み取れませんでした。');
    return { facilities: out, bubbles: extra };
}

// ---------- 住所・施設の位置 ----------

let lastGeocodeAt = 0;
async function nominatim(q, box) {
    const wait = lastGeocodeAt + CONFIG.geocodeIntervalMs - Date.now();
    if (wait > 0) await sleep(wait);
    lastGeocodeAt = Date.now();
    const p = new URLSearchParams({ q, format: 'jsonv2', limit: '1', countrycodes: 'jp', 'accept-language': 'ja' });
    if (box) { p.set('viewbox', box.join(',')); p.set('bounded', '1'); }
    const res = await fetch(`${CONFIG.geocodeUrl}?${p}`);
    if (!res.ok) throw new Error(`住所検索に失敗しました（${res.status}）`);
    const data = await res.json();
    return data[0] ? { lat: Number(data[0].lat), lng: Number(data[0].lon), label: data[0].display_name } : null;
}

// 日本の住所は番地まで入れると見つからないことが多いので、後ろから削って探す
function addressVariants(addr) {
    const a = addr.replace(/\s+/g, '');
    const v = [a];
    const cuts = [/(\d+|[０-９]+)番地?(\d+|[０-９]+)?(号)?$/, /(\d+|[０-９]+)(番地?|-|－).*$/, /(\d+|[０-９一二三四五六七八九十]+)丁目.*$/];
    let cur = a;
    for (const re of cuts) {
        const next = cur.replace(re, '');
        if (next && next !== cur) { v.push(next); cur = next; }
    }
    return [...new Set(v)];
}

function boxAround(lat, lng, km) {
    const dLat = km / 111;
    const dLng = km / (111 * Math.cos(lat * Math.PI / 180));
    return [lng - dLng, lat + dLat, lng + dLng, lat - dLat];
}

async function locateProperty(addr) {
    for (const q of addressVariants(addr)) {
        const hit = await nominatim(q);
        if (hit) return { ...hit, approx: q !== addressVariants(addr)[0] };
    }
    return null;
}

async function locateFacility(row) {
    const km = row.kind === 'car' ? 15 : 2.5;
    const box = boxAround(property.lat, property.lng, km);
    const tries = [[row.name, box], [`${row.name} ${row.hint}`, box], [row.name.replace(/\s+/g, ''), box]];
    for (const [q, b] of tries) {
        const hit = await nominatim(q, b);
        if (hit) return { ...hit, approx: false };
    }
    if (row.hint) {
        const hit = await nominatim(row.hint, box);
        if (hit) return { ...hit, approx: true };
    }
    return null;
}

// ---------- 徒歩分・車の分 ----------

function haversine(a, b) {
    const R = 6371000, toR = d => d * Math.PI / 180;
    const dLat = toR(b.lat - a.lat), dLng = toR(b.lng - a.lng);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(toR(a.lat)) * Math.cos(toR(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
}

async function measure(row) {
    const base = row.kind === 'car' ? CONFIG.carRouteUrl : CONFIG.walkRouteUrl;
    try {
        const res = await fetch(`${base}${property.lng},${property.lat};${row.lng},${row.lat}?overview=full&geometries=geojson`);
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        const r = data.routes && data.routes[0];
        if (!r) throw new Error('no route');
        row.route = r.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
        row.meters = r.distance;
        row.minutes = row.kind === 'car' ? Math.max(1, Math.ceil(r.duration / 60)) : Math.ceil(r.distance / CONFIG.metersPerMinute);
        row.minutesApprox = false;
    } catch (e) {
        // 経路が取れないときは直線距離×1.25で概算し、紙面で「概算」と分かるようにする
        const m = haversine(property, row) * 1.25;
        row.route = null;
        row.meters = m;
        row.minutes = row.kind === 'car' ? Math.max(1, Math.ceil(m / 400)) : Math.ceil(m / CONFIG.metersPerMinute);
        row.minutesApprox = true;
    }
}

function renumber() {
    const walk = rows.filter(r => r.kind === 'walk').sort((a, b) => a.minutes - b.minutes);
    const car = rows.filter(r => r.kind === 'car').sort((a, b) => a.minutes - b.minutes);
    rows = [...walk, ...car];
    rows.forEach((r, i) => { r.no = i + 1; });
}

// ---------- 編集用地図 ----------

function pinIcon(label, color) {
    return L.divIcon({
        className: '',
        html: `<div style="width:26px;height:26px;border-radius:50%;background:${color};color:#fff;font:700 12px sans-serif;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)">${label}</div>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13],
    });
}

function drawEditMap() {
    $('editPanel').hidden = false;
    if (!editMap) {
        editMap = L.map('editMap', { zoomSnap: 1 });
        L.tileLayer(CONFIG.tileUrl, { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(editMap);
        markerLayer = L.layerGroup().addTo(editMap);
    }
    markerLayer.clearLayers();
    L.marker([property.lat, property.lng], { icon: pinIcon('★', '#c8553d'), draggable: true })
        .on('dragend', async e => { Object.assign(property, e.target.getLatLng()); await remeasureAll(); })
        .bindTooltip(property.name).addTo(markerLayer);
    for (const r of rows) {
        if (r.lat == null) continue;
        L.marker([r.lat, r.lng], { icon: pinIcon(r.no, r.kind === 'car' ? '#7a6a3a' : '#2f6f8f'), draggable: true })
            .on('dragend', async e => { Object.assign(r, e.target.getLatLng()); r.approx = false; await measure(r); renumber(); drawEditMap(); drawRowTable(); })
            .bindTooltip(`${r.no}. ${r.name}`).addTo(markerLayer);
    }
    const walkPts = rows.filter(r => r.kind === 'walk' && r.lat != null).map(r => [r.lat, r.lng]);
    editMap.fitBounds(L.latLngBounds([[property.lat, property.lng], ...walkPts]).pad(0.12));
}

async function remeasureAll() {
    setStatus('徒歩分を計算し直しています…');
    for (const r of rows) if (r.lat != null) await measure(r);
    renumber();
    drawEditMap();
    drawRowTable();
    setStatus('計算し直しました。');
}

function drawRowTable() {
    const tr = rows.map(r => `<tr><td>${r.no}</td><td>${esc(r.name)}${r.unchecked ? '<br><span class="warn">AIが実在を確かめきれていません</span>' : ''}</td><td>${esc(r.type)}</td><td>${r.lat == null ? '<span class="warn">見つからず（紙面に載りません）</span>' : (r.kind === 'car' ? '車' : '徒歩') + `約${r.minutes}分` + (r.minutesApprox ? '<span class="warn">（概算）</span>' : '') + (r.approx ? '<span class="warn">（位置は目印から推定・要確認）</span>' : '')}</td><td>${esc(r.note)}</td></tr>`).join('');
    $('rowTable').innerHTML = `<tr><th>#</th><th>施設名</th><th>種類</th><th>所要</th><th>吹き出し</th></tr>${tr}`;
}

// ---------- 実行 ----------

async function run() {
    $('btnRun').disabled = true;
    try {
        const name = $('propName').value.trim();
        const addr = $('propAddr').value.trim();
        if (!name || !addr) throw new Error('物件名と住所を入れてください。');
        const parsed = parseTable($('tableIn').value);
        bubbles = parsed.bubbles;
        setStatus('物件の位置を探しています…');
        const p = await locateProperty(addr);
        if (!p) throw new Error('物件の住所が見つかりませんでした。町名までに短くして試してください。');
        property = { name, lat: p.lat, lng: p.lng };
        rows = parsed.facilities.map(f => ({ ...f, lat: null, lng: null }));
        let i = 0;
        for (const r of rows) {
            i += 1;
            setStatus(`施設の位置を探しています（${i}/${rows.length}）… ${r.name}`);
            const hit = await locateFacility(r);
            if (hit) { r.lat = hit.lat; r.lng = hit.lng; r.approx = hit.approx; await measure(r); }
        }
        renumber();
        drawEditMap();
        drawRowTable();
        const miss = rows.filter(r => r.lat == null).length;
        const approx = rows.filter(r => r.approx).length;
        setStatus(`ピンを立てました（${rows.length - miss}/${rows.length}件）。` + (p.approx ? '\n物件の位置は住所の一部から推定しています。★をドラッグして合わせてください。' : '') + (approx ? `\n${approx}件は目印から推定した位置です。` : '') + (miss ? `\n${miss}件は見つかりませんでした。住所・目印を足すか、紙面から外してください。` : ''));
    } catch (e) {
        setStatus(e.message);
    } finally {
        $('btnRun').disabled = false;
    }
}

// ---------- A4 叩き台（地図は実タイルを合成した画像） ----------

function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
    });
}

async function renderMapImage() {
    const size = editMap.getSize();
    const zoom = editMap.getZoom() + 1; // 2倍解像度
    const scale = 2;
    const W = size.x * scale, H = size.y * scale;
    const origin = editMap.project(editMap.getBounds().getNorthWest(), zoom).round();
    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#f2efe9'; ctx.fillRect(0, 0, W, H);
    const t0x = Math.floor(origin.x / 256), t0y = Math.floor(origin.y / 256);
    const t1x = Math.floor((origin.x + W) / 256), t1y = Math.floor((origin.y + H) / 256);
    const jobs = [];
    for (let tx = t0x; tx <= t1x; tx++) {
        for (let ty = t0y; ty <= t1y; ty++) {
            const url = CONFIG.tileUrl.replace('{z}', zoom).replace('{x}', tx).replace('{y}', ty);
            jobs.push(loadImage(url).then(img => ctx.drawImage(img, tx * 256 - origin.x, ty * 256 - origin.y)).catch(() => {}));
        }
    }
    await Promise.all(jobs);
    // 紙面向けに少し淡く
    ctx.fillStyle = 'rgba(251,248,242,0.28)'; ctx.fillRect(0, 0, W, H);
    const u = W / 760; // 紙面での見た目をそろえる基準
    const xy = (lat, lng) => { const p = editMap.project([lat, lng], zoom); return [p.x - origin.x, p.y - origin.y]; };

    // 最寄り駅（徒歩・種類に「駅」）→物件の動線
    const station = rows.filter(r => r.kind === 'walk' && /駅/.test(r.type + r.name) && r.route).sort((a, b) => a.minutes - b.minutes)[0];
    if (station) {
        ctx.save();
        ctx.strokeStyle = '#c8553d'; ctx.lineWidth = 3.5 * u; ctx.setLineDash([8 * u, 6 * u]); ctx.lineCap = 'round';
        ctx.beginPath();
        station.route.forEach(([lat, lng], i) => { const [x, y] = xy(lat, lng); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
        ctx.stroke();
        ctx.restore();
    }
    const dot = (x, y, r, fill, label, font) => {
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = fill; ctx.fill();
        ctx.lineWidth = 2.5 * u; ctx.strokeStyle = '#fff'; ctx.stroke();
        ctx.fillStyle = '#fff'; ctx.font = font; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(label, x, y + 1);
    };
    const [px, py] = xy(property.lat, property.lng);
    dot(px, py, 17 * u, '#c8553d', '★', `700 ${17 * u}px sans-serif`);
    ctx.font = `700 ${14 * u}px sans-serif`;
    const tw = ctx.measureText(property.name).width;
    ctx.fillStyle = 'rgba(255,255,255,0.92)'; ctx.fillRect(px - tw / 2 - 6 * u, py + 21 * u, tw + 12 * u, 22 * u);
    ctx.fillStyle = '#c8553d'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(property.name, px, py + 32 * u);
    // 施設ピンは物件ラベルより手前に描く
    for (const r of rows) {
        if (r.lat == null) continue;
        const [x, y] = xy(r.lat, r.lng);
        if (x < 0 || y < 0 || x > W || y > H) continue;
        dot(x, y, 13 * u, r.kind === 'car' ? '#7a6a3a' : '#2f6f8f', String(r.no), `700 ${14 * u}px sans-serif`);
    }
    return canvas.toDataURL('image/png');
}

function sheetHtml(imgSrc) {
    const li = r => `<li class="${r.kind}"><span class="no">${r.no}</span><span class="name">${esc(r.name)}</span><span class="min">${r.kind === 'car' ? '車' : '徒歩'}${r.minutesApprox ? '約' : ''}${r.minutes}分</span>${r.note ? `<span class="note">${esc(r.note)}</span>` : ''}</li>`;
    const walk = rows.filter(r => r.kind === 'walk' && r.lat != null);
    const car = rows.filter(r => r.kind === 'car' && r.lat != null);
    const approx = rows.some(r => r.minutesApprox && r.lat != null);
    return `<div class="sheet">
<h2>${esc(property.name)} 周辺MAP</h2>
${$('areaCopy').value.trim() ? `<p class="area">${esc($('areaCopy').value.trim())}</p>` : ''}
<img class="mapimg" src="${imgSrc}" alt="${esc(property.name)}の周辺地図">
<div class="lists${car.length ? '' : ' single'}">
<div><h3>歩いて行ける</h3><ol>${walk.map(li).join('')}</ol></div>
${car.length ? `<div><h3>車で行ける</h3><ol>${car.map(li).join('')}</ol></div>` : ''}
</div>
${bubbles.length ? `<div class="bubbles">${bubbles.slice(0, 2).map(b => `<div class="bubble">${esc(b)}</div>`).join('')}</div>` : ''}
<p class="credit">徒歩分は道のりの距離から80m＝1分で計算（端数切り上げ）。${approx ? '一部は直線距離からの概算です。' : ''}掲載情報は作成時点のものです。<br>${esc(CONFIG.credit)}</p>
</div>`;
}

async function buildSheet() {
    $('btnSheet').disabled = true;
    setStatus('叩き台を作っています…');
    try {
        sheetDataUrl = await renderMapImage();
        $('sheetHost').innerHTML = sheetHtml(sheetDataUrl);
        $('sheetHost').hidden = false;
        $('btnPrint').disabled = false;
        $('btnHtml').disabled = false;
        $('sheetHost').scrollIntoView({ behavior: 'smooth' });
        setStatus('叩き台ができました。下に表示しています。');
    } catch (e) {
        setStatus(`叩き台を作れませんでした: ${e.message}`);
    } finally {
        $('btnSheet').disabled = false;
    }
}

function saveHtml() {
    const own = [...document.styleSheets].find(s => s.ownerNode && s.ownerNode.tagName === 'STYLE');
    const css = [...own.cssRules].map(r => r.cssText).filter(t => /^(:root|\.sheet|\*|body|@media print|@page)/.test(t)).join('\n');
    const doc = `<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><title>${esc(property.name)} 周辺MAP 叩き台</title>
<!-- AI仕上げ用: 地図画像・施設名・徒歩分・出典は変えず、見た目（配色・フォント・余白・吹き出しの形）だけを整えてください。 -->
<style>${css}</style></head><body>${sheetHtml(sheetDataUrl)}</body></html>`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([doc], { type: 'text/html' }));
    a.download = `${property.name}_周辺MAP_叩き台.html`;
    a.click();
}

$('btnRun').addEventListener('click', run);
$('btnSample').addEventListener('click', () => {
    $('propName').value = SAMPLE.name;
    $('propAddr').value = SAMPLE.addr;
    $('areaCopy').value = SAMPLE.area;
    $('tableIn').value = SAMPLE.table;
});
$('btnSheet').addEventListener('click', buildSheet);
$('btnPrint').addEventListener('click', () => window.print());
$('btnHtml').addEventListener('click', saveHtml);
