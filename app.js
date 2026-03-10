// グローバル変数
let map;
let markers = [];
let infoWindow;
let apiKey = '';
let currentPlaces = []; // 検索結果を保存
let currentStationName = ''; // 現在の駅名を保存

// ページ読み込み時の初期化
document.addEventListener('DOMContentLoaded', () => {
    // ローカルストレージからAPIキーを読み込む
    const savedApiKey = localStorage.getItem('googleMapsApiKey');
    if (savedApiKey) {
        document.getElementById('apiKeyInput').value = savedApiKey;
        apiKey = savedApiKey;
    }

    // APIキーの変更を監視
    document.getElementById('apiKeyInput').addEventListener('change', (e) => {
        apiKey = e.target.value;
        localStorage.setItem('googleMapsApiKey', apiKey);
    });

    // Enterキーで検索
    document.getElementById('stationInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            searchRealEstate();
        }
    });
});

// Google Maps APIを動的に読み込む
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

// エラーメッセージを表示
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    // 結果セクションを非表示
    document.getElementById('resultsSection').style.display = 'none';
    
    // ボタンを元に戻す
    resetSearchButton();
}

// エラーメッセージを非表示
function hideError() {
    document.getElementById('errorMessage').style.display = 'none';
}

// 検索ボタンの状態を変更
function setSearchButtonLoading(loading) {
    const button = document.getElementById('searchButton');
    const buttonText = button.querySelector('.button-text');
    const spinner = button.querySelector('.loading-spinner');
    
    if (loading) {
        button.disabled = true;
        buttonText.style.display = 'none';
        spinner.style.display = 'inline';
    } else {
        button.disabled = false;
        buttonText.style.display = 'inline';
        spinner.style.display = 'none';
    }
}

// 検索ボタンをリセット
function resetSearchButton() {
    setSearchButtonLoading(false);
}

// メイン検索関数
async function searchRealEstate() {
    const stationName = document.getElementById('stationInput').value.trim();
    const currentApiKey = document.getElementById('apiKeyInput').value.trim();
    
    // バリデーション
    if (!currentApiKey) {
        showError('Google Maps API Keyを入力してください。');
        return;
    }
    
    if (!stationName) {
        showError('駅名を入力してください。');
        return;
    }
    
    // APIキーを更新
    apiKey = currentApiKey;
    localStorage.setItem('googleMapsApiKey', apiKey);
    
    hideError();
    setSearchButtonLoading(true);
    
    // Google Maps APIを読み込んで検索を実行
    loadGoogleMapsScript(() => {
        performSearch(stationName);
    });
}

// 実際の検索処理
async function performSearch(stationName) {
    try {
        // 1. 駅の位置情報を取得（Geocoding API）
        const location = await getStationLocation(stationName);
        
        if (!location) {
            showError('駅が見つかりませんでした。駅名を確認してください。');
            return;
        }
        
        // 2. 周辺の不動産会社を検索（Places API）
        const places = await searchNearbyRealEstateCompanies(location);
        
        if (places.length === 0) {
            showError('周辺に不動産賃貸管理会社が見つかりませんでした。');
            return;
        }
        
        // 3. 地図を初期化
        initializeMap(location);
        
        // 4. 駅名を保存
        currentStationName = stationName;
        
        // 5. 結果を表示（問い合わせフォームURLは後で取得）
        displayResults(stationName, places, location);
        
        // 6. 各会社の問い合わせフォームURLを取得（非同期）
        fetchContactFormsForAllPlaces(places);
        
        resetSearchButton();
        
    } catch (error) {
        console.error('検索エラー:', error);
        showError(`検索中にエラーが発生しました: ${error.message}`);
    }
}

// 駅の位置情報を取得
function getStationLocation(stationName) {
    return new Promise((resolve, reject) => {
        const geocoder = new google.maps.Geocoder();
        
        geocoder.geocode(
            { 
                address: stationName,
                region: 'JP'
            },
            (results, status) => {
                if (status === 'OK' && results[0]) {
                    resolve({
                        lat: results[0].geometry.location.lat(),
                        lng: results[0].geometry.location.lng()
                    });
                } else {
                    resolve(null);
                }
            }
        );
    });
}

// 周辺の不動産会社を検索
function searchNearbyRealEstateCompanies(location) {
    return new Promise((resolve, reject) => {
        const service = new google.maps.places.PlacesService(document.createElement('div'));
        
        const request = {
            location: new google.maps.LatLng(location.lat, location.lng),
            radius: 2000, // 2km圏内
            keyword: '不動産 賃貸 管理',
            language: 'ja'
        };
        
        service.nearbySearch(request, (results, status) => {
            if (status === google.maps.places.PlacesServiceStatus.OK) {
                // 詳細情報を取得
                Promise.all(
                    results.map(place => getPlaceDetails(place.place_id))
                ).then(detailedPlaces => {
                    resolve(detailedPlaces.filter(p => p !== null));
                });
            } else {
                resolve([]);
            }
        });
    });
}

// 住所から県と市を抽出
function extractPrefectureAndCity(address) {
    if (!address) return { prefecture: '-', city: '-' };
    
    // 日本の都道府県リスト
    const prefectures = [
        '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
        '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
        '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
        '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
        '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
        '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
        '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
    ];
    
    let prefecture = '-';
    let city = '-';
    
    // 県を抽出
    for (const pref of prefectures) {
        if (address.includes(pref)) {
            prefecture = pref;
            // 県の後の市区町村を抽出
            const afterPref = address.split(pref)[1];
            if (afterPref) {
                // 市区町村を抽出（最初の市・区・町・村まで）
                const cityMatch = afterPref.match(/^([^0-9]+?[市区町村])/);
                if (cityMatch) {
                    city = cityMatch[1];
                }
            }
            break;
        }
    }
    
    return { prefecture, city };
}

// すべての会社の問い合わせフォームURLを取得
async function fetchContactFormsForAllPlaces(places) {
    const promises = places.map((place, index) => 
        fetchContactFormUrl(place.website, index)
    );
    
    await Promise.all(promises);
    
    // テーブルビューを更新
    if (document.getElementById('tableView').style.display !== 'none') {
        createTableView(currentPlaces);
    }
}

// 問い合わせフォームURLを取得（ウェブサイトから抽出）
async function fetchContactFormUrl(websiteUrl, placeIndex) {
    if (!websiteUrl) {
        if (currentPlaces[placeIndex]) {
            currentPlaces[placeIndex].contactFormUrl = null;
            currentPlaces[placeIndex].email = null;
        }
        return;
    }
    
    try {
        // CORS制限を回避するため、直接フェッチはできないので
        // 一般的な問い合わせページのパターンを生成
        const contactFormUrl = guessContactFormUrl(websiteUrl);
        
        if (currentPlaces[placeIndex]) {
            currentPlaces[placeIndex].contactFormUrl = contactFormUrl;
            currentPlaces[placeIndex].email = null; // メールアドレスは取得不可
        }
    } catch (error) {
        console.error('問い合わせフォームURL取得エラー:', error);
        if (currentPlaces[placeIndex]) {
            currentPlaces[placeIndex].contactFormUrl = null;
            currentPlaces[placeIndex].email = null;
        }
    }
}

// 問い合わせフォームURLを推測
function guessContactFormUrl(websiteUrl) {
    if (!websiteUrl) return null;
    
    try {
        const url = new URL(websiteUrl);
        const baseUrl = `${url.protocol}//${url.host}`;
        
        // 一般的な問い合わせページのパターン
        const contactPaths = [
            '/contact',
            '/contact/',
            '/inquiry',
            '/inquiry/',
            '/form',
            '/form/',
            '/toiawase',
            '/toiawase/',
            '/otoiawase',
            '/otoiawase/',
            '/contact-us',
            '/contact-us/',
            '/contactus',
            '/contactus/'
        ];
        
        // 最も一般的なパターンを返す
        return `${baseUrl}/contact`;
    } catch (error) {
        return websiteUrl;
    }
}

// 場所の詳細情報を取得
function getPlaceDetails(placeId) {
    return new Promise((resolve) => {
        const service = new google.maps.places.PlacesService(document.createElement('div'));
        
        service.getDetails(
            {
                placeId: placeId,
                fields: ['name', 'formatted_address', 'formatted_phone_number', 
                        'rating', 'user_ratings_total', 'opening_hours', 
                        'geometry', 'website', 'url']
            },
            (place, status) => {
                if (status === google.maps.places.PlacesServiceStatus.OK) {
                    resolve(place);
                } else {
                    resolve(null);
                }
            }
        );
    });
}

// 地図を初期化
function initializeMap(location) {
    const mapElement = document.getElementById('map');
    
    map = new google.maps.Map(mapElement, {
        center: location,
        zoom: 14,
        mapTypeControl: true,
        streetViewControl: true,
        fullscreenControl: true
    });
    
    infoWindow = new google.maps.InfoWindow();
    
    // 駅の位置にマーカーを追加
    new google.maps.Marker({
        position: location,
        map: map,
        title: '検索地点',
        icon: {
            url: 'http://maps.google.com/mapfiles/ms/icons/blue-dot.png'
        }
    });
    
    // 既存のマーカーをクリア
    markers.forEach(marker => marker.setMap(null));
    markers = [];
}

// 結果を表示
function displayResults(stationName, places, centerLocation) {
    // 結果をグローバル変数に保存
    currentPlaces = places.map(place => {
        const { prefecture, city } = extractPrefectureAndCity(place.formatted_address);
        return {
            ...place,
            prefecture,
            city,
            contactFormUrl: '読込中...',
            email: null
        };
    });
    
    // 結果セクションを表示
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('resultsTitle').textContent = `「${stationName}」周辺の不動産賃貸管理会社`;
    document.getElementById('resultsCount').textContent = `${places.length}件の結果`;
    
    // カードビューを作成
    createCardView(currentPlaces);
    
    // テーブルビューを作成
    createTableView(currentPlaces);
    
    // 地図にマーカーを追加
    places.forEach((place, index) => {
        addMarkerToMap(place, index + 1);
    });
    
    // 結果セクションにスクロール
    document.getElementById('resultsSection').scrollIntoView({ 
        behavior: 'smooth',
        block: 'start'
    });
}

// カードビューを作成
function createCardView(places) {
    const cardView = document.getElementById('cardView');
    cardView.innerHTML = '';
    
    places.forEach((place, index) => {
        const card = createResultCard(place, index + 1);
        cardView.appendChild(card);
    });
}

// テーブルビューを作成
function createTableView(places) {
    const tbody = document.getElementById('resultsTableBody');
    tbody.innerHTML = '';
    
    places.forEach((place, index) => {
        const row = document.createElement('tr');
        row.onclick = () => focusOnMarker(index);
        row.style.cursor = 'pointer';
        
        // No. （灰色背景）
        const noCell = createTableCell(index + 1);
        noCell.style.backgroundColor = '#f0f0f0';
        noCell.style.fontWeight = 'bold';
        row.appendChild(noCell);
        
        // 県
        row.appendChild(createTableCell(place.prefecture || '-'));
        
        // 市
        row.appendChild(createTableCell(place.city || '-'));
        
        // 最寄り駅
        row.appendChild(createTableCell(currentStationName || '-'));
        
        // 会社名
        row.appendChild(createTableCell(place.name || '-'));
        
        // 会社URL
        const urlCell = document.createElement('td');
        if (place.website) {
            const urlLink = document.createElement('a');
            urlLink.href = place.website;
            urlLink.textContent = 'サイト';
            urlLink.target = '_blank';
            urlLink.onclick = (e) => e.stopPropagation();
            urlCell.appendChild(urlLink);
        } else {
            urlCell.textContent = '-';
        }
        row.appendChild(urlCell);
        
        // 問合せフォームURL
        const contactCell = document.createElement('td');
        if (place.contactFormUrl === '読込中...') {
            contactCell.textContent = '読込中...';
            contactCell.style.color = '#999';
            contactCell.style.fontStyle = 'italic';
        } else if (place.contactFormUrl) {
            const contactLink = document.createElement('a');
            contactLink.href = place.contactFormUrl;
            contactLink.textContent = 'フォーム';
            contactLink.target = '_blank';
            contactLink.onclick = (e) => e.stopPropagation();
            contactCell.appendChild(contactLink);
        } else {
            contactCell.textContent = '-';
        }
        row.appendChild(contactCell);
        
        // TEL
        const phoneCell = document.createElement('td');
        if (place.formatted_phone_number) {
            phoneCell.textContent = place.formatted_phone_number;
        } else {
            phoneCell.textContent = '-';
        }
        row.appendChild(phoneCell);
        
        // mail
        row.appendChild(createTableCell(place.email || '-'));
        
        tbody.appendChild(row);
    });
}

// テーブルセルを作成
function createTableCell(content) {
    const cell = document.createElement('td');
    cell.textContent = content;
    return cell;
}

// ビュー切り替え
function switchView(viewType) {
    const cardView = document.getElementById('cardView');
    const tableView = document.getElementById('tableView');
    const cardBtn = document.getElementById('cardViewBtn');
    const tableBtn = document.getElementById('tableViewBtn');
    const copyBtn = document.getElementById('copyTableBtn');
    
    if (viewType === 'card') {
        cardView.style.display = 'grid';
        tableView.style.display = 'none';
        cardBtn.classList.add('active');
        tableBtn.classList.remove('active');
        copyBtn.style.display = 'none';
    } else {
        cardView.style.display = 'none';
        tableView.style.display = 'block';
        cardBtn.classList.remove('active');
        tableBtn.classList.add('active');
        copyBtn.style.display = 'block';
    }
}

// テーブルをクリップボードにコピー
function copyTableToClipboard() {
    // タブ区切りテキストを作成（No.列は除外）
    let text = '県\t市\t最寄り駅\t会社名\t会社URL\t問合せフォームURL\tTEL\tmail\n';
    
    currentPlaces.forEach((place, index) => {
        const row = [
            place.prefecture || '-',
            place.city || '-',
            currentStationName || '-',
            place.name || '-',
            place.website || '-',
            (place.contactFormUrl && place.contactFormUrl !== '読込中...') ? place.contactFormUrl : '-',
            place.formatted_phone_number || '-',
            place.email || '-'
        ];
        text += row.join('\t') + '\n';
    });
    
    // クリップボードにコピー
    navigator.clipboard.writeText(text).then(() => {
        // 成功メッセージを表示
        const copyBtn = document.getElementById('copyTableBtn');
        const originalText = copyBtn.innerHTML;
        copyBtn.innerHTML = '✓ コピーしました！';
        copyBtn.style.background = '#45a049';
        
        setTimeout(() => {
            copyBtn.innerHTML = originalText;
            copyBtn.style.background = '#4caf50';
        }, 2000);
    }).catch(err => {
        console.error('コピーに失敗しました:', err);
        alert('コピーに失敗しました。ブラウザの設定を確認してください。');
    });
}

// 結果カードを作成
function createResultCard(place, index) {
    const card = document.createElement('div');
    card.className = 'result-card';
    card.onclick = () => focusOnMarker(index - 1);
    
    let cardHTML = `
        <h3>${index}. ${place.name}</h3>
        <div class="result-info">
    `;
    
    // 住所
    if (place.formatted_address) {
        cardHTML += `
            <div class="info-row">
                <span class="info-label">📍 住所:</span>
                <span>${place.formatted_address}</span>
            </div>
        `;
    }
    
    // 電話番号
    if (place.formatted_phone_number) {
        cardHTML += `
            <div class="info-row">
                <span class="info-label">📞 電話:</span>
                <span><a href="tel:${place.formatted_phone_number}">${place.formatted_phone_number}</a></span>
            </div>
        `;
    }
    
    // 評価
    if (place.rating) {
        const stars = '★'.repeat(Math.round(place.rating)) + '☆'.repeat(5 - Math.round(place.rating));
        cardHTML += `
            <div class="info-row">
                <span class="info-label">⭐ 評価:</span>
                <div class="rating">
                    <span class="stars">${stars}</span>
                    <span class="rating-value">${place.rating}</span>
                    <span>(${place.user_ratings_total || 0}件)</span>
                </div>
            </div>
        `;
    }
    
    // 営業時間
    if (place.opening_hours) {
        const isOpen = place.opening_hours.isOpen();
        cardHTML += `
            <div class="info-row">
                <span class="info-label">🕒 営業:</span>
                <span class="${isOpen ? 'open-now' : 'closed-now'}">
                    ${isOpen ? '営業中' : '営業時間外'}
                </span>
            </div>
        `;
    }
    
    // ウェブサイト
    if (place.website) {
        cardHTML += `
            <div class="info-row">
                <span class="info-label">🌐 Web:</span>
                <span><a href="${place.website}" target="_blank">公式サイト</a></span>
            </div>
        `;
    }
    
    cardHTML += `
        </div>
        <a href="${place.url}" target="_blank" class="view-on-maps">
            Google Mapで見る →
        </a>
    `;
    
    card.innerHTML = cardHTML;
    return card;
}

// 地図にマーカーを追加
function addMarkerToMap(place, index) {
    const marker = new google.maps.Marker({
        position: place.geometry.location,
        map: map,
        title: place.name,
        label: {
            text: index.toString(),
            color: 'white',
            fontWeight: 'bold'
        },
        animation: google.maps.Animation.DROP
    });
    
    // クリック時の情報ウィンドウ
    marker.addListener('click', () => {
        let content = `
            <div style="padding: 10px; max-width: 300px;">
                <h3 style="margin-bottom: 10px;">${place.name}</h3>
                <p style="margin-bottom: 5px;">${place.formatted_address || ''}</p>
        `;
        
        if (place.formatted_phone_number) {
            content += `<p style="margin-bottom: 5px;">📞 ${place.formatted_phone_number}</p>`;
        }
        
        if (place.rating) {
            content += `<p style="margin-bottom: 5px;">⭐ ${place.rating} (${place.user_ratings_total || 0}件)</p>`;
        }
        
        content += `
                <a href="${place.url}" target="_blank" 
                   style="display: inline-block; margin-top: 10px; color: #4285f4; text-decoration: none; font-weight: bold;">
                    Google Mapで見る →
                </a>
            </div>
        `;
        
        infoWindow.setContent(content);
        infoWindow.open(map, marker);
    });
    
    markers.push(marker);
}

// マーカーにフォーカス
function focusOnMarker(index) {
    if (markers[index]) {
        map.setCenter(markers[index].getPosition());
        map.setZoom(16);
        google.maps.event.trigger(markers[index], 'click');
    }
}
