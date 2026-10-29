// 周辺MAP 叩き台（OpenStreetMap版・試作）
// 構成案B: AI（ネタ出し・実在確認）は会員のチャット、ここは「表 → 地図・番号ピン・一覧・徒歩分 → A4」だけを担う。
// サーバ不要。外部に出るのは地図タイル・住所検索・経路計算（白地図を選んだときは Overpass も）だけで、本展開時は CONFIG を商用プランへ差し替える。

const CONFIG = {
    // 試験公開（30〜50人）までは OSM 財団の無料配信。本展開時は商用プラン（Stadia Maps / MapTiler 等）の URL＋ドメイン制限キーへ。
    tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    // 白地図（道路・線路・川・公園の形だけで文字なし）は、OSM の生データを Overpass で取ってこのページで描く。文字のないタイルはキーが要るため
    overpassUrl: 'https://overpass-api.de/api/interpreter',
    geocodeUrl: 'https://nominatim.openstreetmap.org/search',
    walkRouteUrl: 'https://routing.openstreetmap.de/routed-foot/route/v1/driving/',
    carRouteUrl: 'https://routing.openstreetmap.de/routed-car/route/v1/driving/',
    geocodeIntervalMs: 1100, // Nominatim 利用規約: 1秒1件まで
    walkMaxMinutes: 25, // これより遠い徒歩の施設は別の場所に当たったとみなす
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
let propertyAddr = '';
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

// OSMは「杉栄町二丁目」のように漢数字で持っていることが多い
const KANJI_NUM = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
function chomeToKanji(s) {
    return s.replace(/([0-9０-９]+)丁目/g, (m, d) => {
        const n = Number(d.replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0)));
        if (!n || n > 29) return m;
        return (n >= 20 ? KANJI_NUM[Math.floor(n / 10)] + '十' : n >= 10 ? '十' : '') + KANJI_NUM[n % 10] + '丁目';
    });
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
    return [...new Set(v.flatMap(x => [x, chomeToKanji(x)]))];
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

// AIは「地下鉄名城線 志賀本通駅」のように路線名を前に付けがちだが、OSMの駅名は「志賀本通」だけ
function stripLine(name) {
    return name.replace(/^.*?線\s*[「『]?(?=\S+駅)/, '').replace(/[」』]/g, '').trim();
}

// 目印の「杉栄町2-48」「長田町4-66-2」は番地まで入っていてOSMで引けないので「杉栄町二丁目」にする。
// 「若葉通沿い」「志賀本通駅の近く（瑠璃光町）」のような文は、括弧の中の町名や「〜沿い」の前を使う
function hintVariants(hint) {
    if (!hint) return [];
    const h = hint.replace(/\s+/g, '');
    const inParen = (h.match(/[（(]([^）)]+)[）)]/) || [])[1];
    const parts = [inParen, h.replace(/[（(][^）)]*[）)]/g, '')].filter(Boolean).flatMap(x => x.split(/[・、,，／/]/));
    const towns = [];
    for (const part of parts) {
        let t = part.replace(/^(.*?[^\d０-９\-－])([0-9０-９]+)[-－][0-9０-９]+([-－][0-9０-９]+)?.*$/, '$1$2丁目');
        let prev;
        do { prev = t; t = t.replace(/(交差点|付近|周辺|沿い|方面|の近く|近く|の駅前|駅前|エリア|出口|前)$/, ''); } while (t !== prev);
        // 町名・通り名・駅名らしいものだけ使う（「24時間営業の情報あり」のような説明文は捨てる）
        if (t.length >= 2 && /(町|通|丁目|駅|条|区|市|村)$/.test(t)) towns.push(chomeToKanji(t));
    }
    // 町名だけだと同じ名前の町がほかの市にもあるので、物件の「名古屋市北区」を前に付けた形から試す
    const area = (propertyAddr.match(/^(.*?[都道府県])?(.*?市)?(.*?区)?/) || [''])[0].replace(/^.*?[都道府県]/, '');
    return [...new Set(towns.flatMap(t => (area && !/[市区]/.test(t) ? [area + t, t] : [t])))];
}

async function locateFacility(row) {
    const km = row.kind === 'car' ? 15 : 2.5;
    const box = boxAround(property.lat, property.lng, km);
    const name = stripLine(row.name);
    const plain = name.split(/\s*[&＆・／/(（【]/)[0].trim();
    const tries = [[name, box], [`${name} ${row.hint}`, box], [name.replace(/\s+/g, ''), box]];
    if (name !== row.name) tries.unshift([row.name, box]);
    if (plain && plain !== name) tries.push([plain, box]);
    // 駅は「志賀本通駅」より「志賀本通」で入っていることが多い
    if (/駅$/.test(name)) tries.push([name.replace(/駅$/, ''), box]);
    for (const [q, b] of tries) {
        const hit = await nominatim(q, b);
        if (hit) return { ...hit, approx: false };
    }
    for (const q of hintVariants(row.hint).slice(0, 4)) {
        const hit = await nominatim(q, box);
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
    markTooFar(row);
}

// 目印からの推定などで同じ地点に複数のピンが落ちたら、まわりに円く並べ直す（約30m）
function spreadDuplicates() {
    const groups = new Map();
    for (const r of rows) {
        if (r.lat == null) continue;
        const key = `${r.lat.toFixed(4)},${r.lng.toFixed(4)}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(r);
    }
    for (const g of groups.values()) {
        if (g.length < 2) continue;
        const dLat = 30 / 111000, dLng = 30 / (111000 * Math.cos(g[0].lat * Math.PI / 180));
        g.forEach((r, i) => {
            const a = (2 * Math.PI * i) / g.length;
            r.lat += dLat * Math.sin(a); r.lng += dLng * Math.cos(a);
            r.approx = true;
        });
    }
}

// 紙面に載る施設: 見つかった・遠すぎない・会員が「載せない」にしていない
const onSheet = r => r.lat != null && !r.tooFar && !r.excluded;

// 番号は紙面に載る施設だけに振る（見つからない・遠すぎる・載せない施設に番号を残すと①③⑨のように飛ぶ）
function renumber() {
    const walk = rows.filter(r => r.kind === 'walk' && onSheet(r)).sort((a, b) => a.minutes - b.minutes);
    const car = rows.filter(r => r.kind === 'car' && onSheet(r)).sort((a, b) => a.minutes - b.minutes);
    const rest = rows.filter(r => !onSheet(r));
    rows = [...walk, ...car, ...rest];
    rows.forEach((r, i) => { r.no = onSheet(r) ? i + 1 : ''; });
}

// 徒歩25分（2km）を超えたら、同じ名前の別の場所に当たった可能性が高い。紙面から外し、ドラッグで直せるようにする
function markTooFar(r) {
    r.tooFar = r.kind === 'walk' && r.lat != null && r.minutes > CONFIG.walkMaxMinutes;
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
        L.marker([r.lat, r.lng], { icon: pinIcon(r.excluded ? '×' : r.tooFar ? '?' : r.no, r.excluded || r.tooFar ? '#999' : r.kind === 'car' ? '#7a6a3a' : '#2f6f8f'), draggable: true })
            .on('dragend', async e => { Object.assign(r, e.target.getLatLng()); r.approx = false; await measure(r); renumber(); drawEditMap(); drawRowTable(); })
            .bindTooltip(r.excluded ? `${r.name}（載せない）` : r.tooFar ? `${r.name}（遠すぎるため紙面から外しています。正しい場所へドラッグしてください）` : `${r.no}. ${r.name}`).addTo(markerLayer);
    }
    const walk = rows.filter(r => r.kind === 'walk' && r.lat != null && !r.tooFar);
    const dists = walk.map(r => haversine(property, r)).sort((a, b) => a - b);
    const limit = Math.max(700, (dists[Math.floor(dists.length / 2)] || 0) * 2.2);
    const walkPts = walk.filter(r => haversine(property, r) <= limit).map(r => [r.lat, r.lng]);
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
    const btn = (r, i) => r.lat == null || r.tooFar ? '' : `<button type="button" class="toggleRow${r.excluded ? ' secondary' : ''}" data-i="${i}">${r.excluded ? '載せる' : '載せない'}</button>`;
    const where = r => {
        if (r.lat == null) return '<span class="warn">見つからず（紙面に載りません。そのままで大丈夫です）</span>';
        if (r.excluded) return '<span class="warn">載せない（紙面から外しています）</span>';
        return (r.kind === 'car' ? '車' : '徒歩') + `約${r.minutes}分`
            + (r.tooFar ? '<span class="warn">（遠すぎます。別の場所に当たった可能性が高いので紙面から外しています。地図で灰色の？を正しい場所へドラッグしてください）</span>' : '')
            + (r.minutesApprox ? '<span class="warn">（概算）</span>' : '')
            + (r.approx ? '<span class="warn">（店名が地図データになく、目印から推定。だいたいの場所に出ています。違っていたら「載せない」でよい）</span>' : '');
    };
    const tr = rows.map((r, i) => `<tr${r.excluded ? ' style="opacity:.55"' : ''}><td>${r.no}</td><td>${esc(r.name)}${r.unchecked ? '<br><span class="warn">AIが実在を確かめきれていません</span>' : ''}</td><td>${esc(r.type)}</td><td>${where(r)}</td><td>${btn(r, i)}</td><td>${esc(r.note)}</td></tr>`).join('');
    $('rowTable').innerHTML = `<tr><th>#</th><th>施設名</th><th>種類</th><th>所要</th><th>紙面</th><th>吹き出し</th></tr>${tr}`;
    for (const b of $('rowTable').querySelectorAll('button.toggleRow')) b.addEventListener('click', () => toggleRow(rows[Number(b.dataset.i)]));
}

// 貼った表を書き換えずに、施設を紙面から外す／戻す（番号を詰め直し、A4 ができていれば作り直す）
async function toggleRow(r) {
    r.excluded = !r.excluded;
    renumber();
    drawEditMap();
    drawRowTable();
    setStatus(`${r.name} を${r.excluded ? '紙面から外しました' : '紙面に戻しました'}。`);
    if (!$('sheetHost').hidden) await buildSheet();
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
        propertyAddr = addr;
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
        spreadDuplicates();
        renumber();
        drawEditMap();
        drawRowTable();
        const miss = rows.filter(r => r.lat == null).length;
        const far = rows.filter(r => r.tooFar).length;
        const approx = rows.filter(r => r.approx).length;
        setStatus(`ピンを立てました（${rows.length - miss - far}/${rows.length}件）。` + (p.approx ? '\n物件の位置は住所の一部から推定しています。★をドラッグして合わせてください。' : '') + (approx ? `\n${approx}件は目印から推定した位置です。` : '') + (miss ? `\n${miss}件は見つかりませんでした。住所・目印を足すか、紙面から外してください。` : '') + (far ? `\n${far}件は徒歩${CONFIG.walkMaxMinutes}分より遠く、別の場所に当たった可能性があるため紙面から外しました（地図の灰色の？）。` : '') + (miss || approx ? '\n推定の店は、だいたいの場所に出ています。違っていたり載せたくない店は、下の一覧の「載せない」を押してください。' : ''));
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

function isWhiteMap() {
    return $('mapStyle').value === 'white';
}

// 白地図: 表示範囲の道路・線路・川・公園を OSM から取り、線と面だけで描く（地名・店名は描かない）
async function drawWhiteMap(ctx, W, H, xy, u) {
    const b = editMap.getBounds();
    const bbox = [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map(v => v.toFixed(6)).join(',');
    const q = `[out:json][timeout:25];(
way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|pedestrian|service)(_link)?$"](${bbox});
way["railway"~"^(rail|subway|light_rail|narrow_gauge)$"](${bbox});
way["waterway"~"^(river|canal|stream)$"](${bbox});
way["natural"="water"](${bbox});
way["leisure"="park"](${bbox});
);out geom;`;
    let res;
    for (let i = 0; i < 3; i++) { // Overpass は混んでいると 429/504 を返すので少し待って取り直す
        res = await fetch(CONFIG.overpassUrl, { method: 'POST', body: 'data=' + encodeURIComponent(q), headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).catch(() => null);
        if (res && res.ok) break;
        setStatus(`白地図のデータを取り直しています…（${i + 1}回目）`);
        await new Promise(ok => setTimeout(ok, 4000 * (i + 1)));
    }
    if (!res || !res.ok) throw new Error('白地図のデータを取得できませんでした（' + (res ? res.status : '通信エラー') + '）。少し待ってもう一度押してください');
    const ways = (await res.json()).elements.filter(e => e.geometry && e.geometry.length > 1);
    const path = (w, close) => {
        ctx.beginPath();
        w.geometry.forEach((g, i) => { const [x, y] = xy(g.lat, g.lon); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
        if (close) ctx.closePath();
    };
    ctx.fillStyle = '#f6f4ef'; ctx.fillRect(0, 0, W, H);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    for (const w of ways) {
        const t = w.tags || {};
        if (t.leisure === 'park') { path(w, true); ctx.fillStyle = '#e3eedb'; ctx.fill(); }
        else if (t.natural === 'water') { path(w, true); ctx.fillStyle = '#d6e6f2'; ctx.fill(); }
    }
    for (const w of ways.filter(w => (w.tags || {}).waterway)) {
        path(w); ctx.strokeStyle = '#d6e6f2'; ctx.lineWidth = (w.tags.waterway === 'stream' ? 3 : 8) * u; ctx.stroke();
    }
    const roadWidth = { motorway: 10, trunk: 10, primary: 9, secondary: 8, tertiary: 6.5, unclassified: 4.5, residential: 4.5, living_street: 4, pedestrian: 3.5, service: 2.5 };
    const roads = ways.filter(w => (w.tags || {}).highway).map(w => ({ w, width: roadWidth[w.tags.highway.replace('_link', '')] || 3 })).sort((a, c) => a.width - c.width);
    for (const pass of [0, 1]) { // 縁取り → 白い道
        for (const { w, width } of roads) {
            path(w);
            ctx.strokeStyle = pass ? '#ffffff' : '#d9d4ca';
            ctx.lineWidth = (pass ? width : width + 1.6) * u;
            ctx.stroke();
        }
    }
    for (const w of ways.filter(w => (w.tags || {}).railway)) {
        const under = w.tags.railway === 'subway' || w.tags.tunnel === 'yes' || Number(w.tags.layer) < 0;
        path(w);
        ctx.strokeStyle = under ? '#b9b4ab' : '#8d8a84'; ctx.lineWidth = (under ? 2.2 : 3) * u;
        ctx.setLineDash(under ? [6 * u, 5 * u] : []); ctx.stroke(); ctx.setLineDash([]);
    }
}

async function drawTiles(ctx, W, H, origin, zoom) {
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
    const u = W / 760; // 紙面での見た目をそろえる基準
    const xy = (lat, lng) => { const p = editMap.project([lat, lng], zoom); return [p.x - origin.x, p.y - origin.y]; };
    if (isWhiteMap()) await drawWhiteMap(ctx, W, H, xy, u);
    else await drawTiles(ctx, W, H, origin, zoom);

    // 最寄り駅（徒歩・種類に「駅」）→物件の動線
    const station = rows.filter(r => r.kind === 'walk' && /駅/.test(r.type + r.name) && r.route && onSheet(r)).sort((a, b) => a.minutes - b.minutes)[0];
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
    // 施設ピンは物件ラベルより手前に描く。近すぎるピンは描く位置だけ押し離す
    const R = 13 * u;
    const pins = [];
    for (const r of rows) {
        if (!onSheet(r)) continue;
        const [x, y] = xy(r.lat, r.lng);
        r.offMap = x < R || y < R || x > W - R || y > H - R;
        if (!r.offMap) pins.push({ r, x, y });
    }
    for (let k = 0; k < 30; k++) {
        let moved = false;
        for (let i = 0; i < pins.length; i++) {
            for (let j = i + 1; j < pins.length; j++) {
                const a = pins[i], b = pins[j];
                const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 0.01, need = R * 2.15;
                if (d >= need) continue;
                const push = (need - d) / 2, ux = d > 0.01 ? dx / d : 1, uy = d > 0.01 ? dy / d : 0;
                a.x -= ux * push; a.y -= uy * push; b.x += ux * push; b.y += uy * push;
                moved = true;
            }
        }
        // 物件の★と物件名ラベルの上にも重ねない
        const lx0 = px - tw / 2 - 6 * u - R, lx1 = px + tw / 2 + 6 * u + R, ly0 = py + 21 * u - R, ly1 = py + 43 * u + R;
        for (const p of pins) {
            const dx = p.x - px, dy = p.y - py, d = Math.hypot(dx, dy) || 0.01, need = 17 * u + R + 2 * u;
            if (d < need) { p.x = px + dx / d * need; p.y = py + dy / d * need; moved = true; }
            if (p.x > lx0 && p.x < lx1 && p.y > ly0 && p.y < ly1) {
                if (p.y - ly0 < ly1 - p.y) p.y = ly0; else p.y = ly1;
                moved = true;
            }
        }
        if (!moved) break;
    }
    // 白地図は地名が無いので、駅だけ名前を添える
    if (isWhiteMap()) {
        ctx.font = `700 ${12 * u}px sans-serif`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
        for (const { r, x, y } of pins.filter(p => /駅/.test(p.r.type + p.r.name))) {
            const label = (r.name.match(/[^\s]+駅/) || [r.name])[0];
            const lw = ctx.measureText(label).width;
            const lx = x + R + 4 * u + lw > W ? x - R - 4 * u - lw : x + R + 4 * u;
            ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.fillRect(lx - 3 * u, y - 9 * u, lw + 6 * u, 18 * u);
            ctx.fillStyle = '#4a4a4a'; ctx.fillText(label, lx, y + 1);
        }
    }
    for (const { r, x, y } of pins) dot(x, y, R, r.kind === 'car' ? '#7a6a3a' : '#2f6f8f', String(r.no), `700 ${14 * u}px sans-serif`);
    return canvas.toDataURL('image/png');
}

function sheetHtml(imgSrc) {
    const li = r => `<li class="${r.kind}"><span class="no">${r.no}</span><span class="name">${esc(r.name)}</span><span class="min">${r.kind === 'car' ? '車' : '徒歩'}${r.minutesApprox ? '約' : ''}${r.minutes}分${r.offMap ? '（地図外）' : ''}</span>${r.note ? `<span class="note">${esc(r.note)}</span>` : ''}</li>`;
    const walk = rows.filter(r => r.kind === 'walk' && onSheet(r));
    const car = rows.filter(r => r.kind === 'car' && onSheet(r));
    const approx = rows.some(r => r.minutesApprox && onSheet(r));
    const dense = walk.length + car.length > 6 ? ' dense' : '';
    return `<div class="sheet${dense}">
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
        $('finishPanel').hidden = false;
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
<!-- AI仕上げ用: 地図画像・施設名・徒歩分・出典は変えず、見た目（配色・フォント・余白・吹き出しの形）だけを整えてください。地図画像は src="map.png" のままにしてください（叩き台ページが差し込みます）。 -->
<style>${css}</style></head><body>${sheetHtml(MAP_PLACEHOLDER)}</body></html>`;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([doc], { type: 'text/html' }));
    const d = new Date(), z = n => String(n).padStart(2, '0');
    a.download = `${property.name}_周辺MAP_叩き台_${d.getFullYear()}${z(d.getMonth() + 1)}${z(d.getDate())}_${z(d.getHours())}${z(d.getMinutes())}.html`;
    a.click();
}

// ---------- AIの仕上げHTMLを取り込む ----------
// 地図画像は数MBあり、チャットAIに渡すと返せない（途中で切れる）ので、仕上げ用HTMLでは
// map.png という仮の名前にしておき、戻ってきたHTMLにここで差し込む。
const MAP_PLACEHOLDER = 'map.png';

function finishCheck(html) {
    const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, '');
    const plain = s => s.replace(/\s+/g, '');
    const lost = [];
    for (const r of rows.filter(onSheet)) {
        const min = `${r.kind === 'car' ? '車' : '徒歩'}${r.minutesApprox ? '約' : ''}${r.minutes}分`;
        if (!text.includes(plain(r.name))) lost.push(`${r.no}. ${r.name} の名前`);
        else if (!text.includes(min)) lost.push(`${r.no}. ${r.name} の「${min}」`);
    }
    if (!text.includes('OpenStreetMap')) lost.push('出典表記（© OpenStreetMap contributors）');
    if (!html.includes(MAP_PLACEHOLDER)) lost.push('地図画像（src="map.png"）');
    return lost;
}

function previewFinish() {
    let html = $('finishIn').value.trim().replace(/^```[a-z]*\s*/i, '').replace(/```\s*$/, '');
    const start = html.search(/<!DOCTYPE|<html/i);
    if (start < 0) { $('finishCheck').textContent = 'HTMLが見つかりません。<!DOCTYPE html> から </html> まで貼ってください。'; return; }
    html = html.slice(start);
    const lost = finishCheck(html);
    $('finishCheck').innerHTML = lost.length
        ? `<span class="warn">元の叩き台と違うところがあります。チャットに「情報は変えないで」と伝えて出し直してもらってください。\n・${lost.map(esc).join('\n・')}</span>`
        : '施設名・徒歩分・出典は元の叩き台と同じです。';
    const frame = $('finishFrame');
    frame.srcdoc = html.split(`"${MAP_PLACEHOLDER}"`).join(`"${sheetDataUrl}"`).split(`'${MAP_PLACEHOLDER}'`).join(`'${sheetDataUrl}'`);
    frame.style.display = 'block';
    $('btnFinishPrint').disabled = false;
}

$('btnRun').addEventListener('click', run);
$('btnFinish').addEventListener('click', previewFinish);
$('btnFinishPrint').addEventListener('click', () => $('finishFrame').contentWindow.print());
$('btnSample').addEventListener('click', () => {
    $('propName').value = SAMPLE.name;
    $('propAddr').value = SAMPLE.addr;
    $('areaCopy').value = SAMPLE.area;
    $('tableIn').value = SAMPLE.table;
});
$('btnSheet').addEventListener('click', buildSheet);

// 初級モード（初期表示）と中級の機能の切り替え。選んだ表示はこの端末に覚えておく
function setBeginner(on) {
    document.body.classList.toggle('beginner', on);
    $('modeLabel').textContent = on ? 'いまは「初級」の画面です。' : 'いまは中級の機能も表示しています。';
    $('btnMode').textContent = on ? '中級の機能を表示' : '初級の画面に戻す';
    try { localStorage.setItem('shuhenOsmMode', on ? 'beginner' : 'advanced'); } catch (e) { /* 保存できない環境では毎回初級 */ }
}
$('btnMode').addEventListener('click', () => setBeginner(!document.body.classList.contains('beginner')));
let savedMode = null;
try { savedMode = localStorage.getItem('shuhenOsmMode'); } catch (e) { /* noop */ }
setBeginner(savedMode !== 'advanced');
$('btnPrint').addEventListener('click', () => window.print());
$('btnHtml').addEventListener('click', saveHtml);
