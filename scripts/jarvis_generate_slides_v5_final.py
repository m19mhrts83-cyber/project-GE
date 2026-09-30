#!/usr/bin/env python3
"""
NotebookLM Studio スライド生成 v5 Final
- 5人家族完全指定（丸テーブル構図・紗和小4含む大人2子ども3）
- マスタースタイル（白背景・手描き水彩ゆるキャラ）完全再現
- 男子校アピール控えめ（スライド2）
- 全7枚構成厳守
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz

PROFILE_DIR = Path.home() / "Library/Application Support/notebooklm-studio/chrome_profile"
NOTEBOOK_URL = "https://notebook.google.com/notebook/20b6c702-1eba-4061-91e7-7dcf0592e19a"
OUTPUT_DIR = Path("/Users/matsunomasaharu2/Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ/200_NoteBookLM/09_家族受験会議2026秋_円香と珠己/★アウトプット")
SLIDES_PNG_DIR = OUTPUT_DIR / "slides_png_v5"
PDF_PATH = OUTPUT_DIR / "2026秋_家族受験会議スライド_円香と珠己.pdf"

PROMPT = """登録ソース「05_スライド構成案_家族会議プレゼン.md」および「NotebookLM_マスタースタイル_cute-illustration.md」に従い、指定の順序で【全7枚】のスライドデッキを作成してください。

【全スライド共通のデザイントーン（初期マスタースタイルを厳守）】
- 背景: 完全な純白 #FFFFFF。部屋の内装、壁、窓、家具、床、風景などの立体的な背景は一切描かないこと。余白たっぷりのシンプルな手描き水彩デザイン。
- 人物: 2〜3頭身のデフォルメ手描きゆるキャラ。丸顔、点は目、線は口。髪はシンプルな塊。
- 色彩: 水彩風の淡い色（クリーム、薄い青、薄いオレンジ、薄い緑、薄い黄色）。ベタ塗りではなく優しいムラ塗り。グラデーションやドロップシャドウ、3D表現は完全禁止。
- 文字: 丸ゴシック風。見出しは黄色やオレンジのマーカー風ハイライト帯。

【スライドの枚数と順序（全7枚・順序変更禁止）】

■ スライド 1：表紙（5人家族の作戦会議）
- タイトル: 2026秋 家族受験会議
- サブタイトル: 円香・珠己の未来をひらく作戦会議 〜みんなで決める秋の学校見学〜
- 下部ハイライト帯: 「選択肢は親が出す。最後に決めるのは君たち自身！」
- イラスト（中央）: 純白の背景（#FFFFFF）の中央に、低い丸テーブル（ちゃぶ台）を囲む【5人家族】を描く。部屋の壁や窓などの背景は一切描かない。
  家族5人の内訳（大人2人、子ども3人の合計5人厳守！絶対に4人や6人にしないこと）：
  ① お父さん（水色セーター）
  ② お母さん（緑のワンピース）
  ③ 中3長女の円香（オレンジのパーカー）
  ④ 小6長男の珠己（青白ボーダーの服）
  ⑤ 小4次女の妹・紗和（黄色い服を着た小さな女の子）
  丸テーブルの上にはカレンダーと学校案内のパンフレットが広げられている。

■ スライド 2：【珠己】秋の学校見学プラン
※男子校のアピールは控えめにし、秋のお祭りと体験を楽しむ前向きな見学プランにする。
- 見出し: 珠己のわくわく学校見学 〜秋のお祭りと体験に行ってみよう〜
- プラン（3校）：
  ① 9/19(土) 名古屋中学校「愛校祭」（予約不要！楽しい文化祭）
  ② 9/20(日) 南山中学校男子部「飛翔祭」（部活発表や模擬店がいっぱい！）
  ③ 10/3(土) 星城中学校「オープンスクール」（地元豊明・校舎見学や体験授業）
- 父の言葉: 「連休に名古屋中と南山のお祭りを覗いて、10月は星城の体験に行ってみようか！行ってみよう！」
- イラスト: 白背景に、文化祭のゲートをくぐり、部活発表や模擬店に目を輝かせる男の子のゆるキャラ。

■ スライド 3：【円香】秋の高校見学プラン
- 見出し: 円香の高校選び 〜春日丘を本命に、英語・海外の可能性を広げる〜
- 候補校：
  - 【大本命】11/7(土) 春日丘高校「学校・入試説明会」（高校校舎で入試対策を直接解説）
  - 【英語・海外に強い選択肢】
    - 光ヶ丘女子：9/19(土) 文化祭（全国屈指の英語・留学実績）
    - 清林館：9/26(土) 授業体験会（手厚い英語教育・1年留学）
    - 名古屋国際：9/26(土) 文化祭 / 11/21(土) 説明会（御器所・IB国際バカロレア）
- イラスト: 白背景に、地球儀や英語の本を持って未来を見つめる女の子のゆるキャラ。

■ スライド 4：【円香・日程調整】9月26日(土)の選択
- 見出し: 9月26日(土)はどうする？ 〜授業体験 vs 文化祭〜
- 整理：
  - 【推奨案：体験重視】清林館の「授業体験会」へ参加！（一度体験授業を受けてみたい希望を尊重）
    ※聖霊高は11/8オープンスクール、名国は11/21説明会に回せば全てカバー可能！
  - 【対案：文化祭重視】女子校文化祭重視なら聖霊高校の「聖霊祭」へ！
- 父の言葉: 「まずは9月26日は清林館の体験授業に行ってみる流れで調整しよう！」（※「円香はどう感じる？」は含めないこと）
- イラスト: 白背景に、カレンダーの9/26を見つめ、2つのルート（体験型／文化祭型）を見比べて選ぶ女の子のゆるキャラ。

■ スライド 5：【円香】高校入学後も見据えて
- 見出し: 高校生活とこれからの学び 〜通学ルートと坪田塾の活用〜
- ポイント：
  - 通学イメージ：春日丘（神領駅）、名古屋国際（御器所駅）、清林館（佐屋駅）
  - 放課後の自立学習：千種駅・車道駅すぐの「坪田塾」（ビリギャルでおなじみ）
  - 心理学×教えない指導：性格タイプに合わせた自学自習習慣。高校入学後の中だるみも安心！
- イラスト: 白背景に、電車に乗って通学し、明るい自習室で楽しく自学自習する女の子のゆるキャラ。

■ スライド 6：【父からのメッセージ】山下さんの教えと人間性の成長
- 見出し: お父さんからのメッセージ 〜人を馬鹿にせず、馬鹿にされない人へ〜
- アース山下誠治氏の動画（後半：成長する人・しない人の違い）視聴と3つの教え：
  ① 人を馬鹿にしない！馬鹿にされない人間へ（人間性の成長）：心に余裕を持ち、自分も人も大切にできる人になろう。すべては一生幸せに生きてほしいから。
  ② 1日10分の法則（コンフォートゾーンを出る）：無理な努力はいらない。今の自分より「毎日あと10分」だけ歯を食いしばれば、4ヶ月で1.5倍成長できる！志望校に手が届く！
  ③ 決めるのは自分自身（主体性の引き渡し）：親は情報集めや送迎を全力でサポートする。でも、最後に進路を決めて向き合うのは自分自身だ！
- イラスト: 白背景に、男の子が小さな「10分」のブロックを積み上げて階段を一歩ずつ登っていく優しい手描きイラスト。

■ スライド 7：まとめ（これからの進め方）
- 見出し: これからの進め方 〜自分で見て、納得して決めよう！〜
- 3つのステップ：
  - Step 1: まずはお祭り（文化祭）や体験授業へ行ってみる
  - Step 2: 実際の校舎や先輩を見て「ここに行きたい！」を見つける
  - Step 3: 決めた目標に向かって、毎日10分ずつ前に進もう！
- 親の約束: 「情報集めや送迎、どんなサポートも全力でするよ。一緒に頑張ろう！」
- イラスト: 白背景（#FFFFFF）に、【5人家族全員（父、母、円香、珠己、小4の紗和：合計5人）】が笑顔で「エイエイオー！」と手を掲げている優しい手描き水彩イラスト。部屋などの背景は描かず白背景。"""


def run_generation():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SLIDES_PNG_DIR.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()
    browser = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
        accept_downloads=True,
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto(NOTEBOOK_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # 1. 「スライド資料」タイルをクリック
    print("Step 1: Clicking 'スライド資料' tile...")
    ok = page.evaluate("""() => {
        const panel = document.querySelector('section.studio-panel');
        if (!panel) return false;
        const el = [...panel.querySelectorAll('*')].find(
            e => (e.innerText || '').trim() === 'スライド資料'
        );
        if (!el) return false;
        (el.closest('button') || el.closest('[role=button]') || el).click();
        return true;
    }""")
    if not ok:
        page.locator("section.studio-panel").get_by_text("スライド資料", exact=True).first.click(force=True)
    page.wait_for_timeout(2500)

    # 2. プロンプト入力
    print("Step 2: Filling prompt...")
    ta = page.locator('textarea[aria-label="指示"]')
    if ta.count() == 0:
        ta = page.locator("textarea")
    ta.first.fill(PROMPT)
    page.wait_for_timeout(1000)

    # 3. 「生成」ボタンクリック
    print("Step 3: Clicking '生成' button...")
    gen_btn = page.locator('button:has-text("生成")').first
    gen_btn.click(force=True)
    print("Generation triggered successfully!")
    page.wait_for_timeout(3000)

    # 4. 生成完了ポーリング
    print("Step 4: Polling for generation to finish...")
    start_time = time.time()
    saw_generating = False
    while time.time() - start_time < 420:  # 最大7分
        page.wait_for_timeout(10000)
        t = page.locator("section.studio-panel").inner_text()
        elapsed = int(time.time() - start_time)
        if "スライド資料を生成しています" in t or "生成しています" in t:
            saw_generating = True
            print(f"[{elapsed}s] Generating in progress...")
        else:
            if saw_generating:
                print(f"[{elapsed}s] Generation finished! Waiting 5s...")
                page.wait_for_timeout(5000)
                break
            else:
                print(f"[{elapsed}s] Waiting for indicator...")

    page.wait_for_timeout(3000)

    # 5. ダウンロードURLのキャプチャ
    print("Step 5: Capturing download URL...")
    panel = page.locator("section.studio-panel")
    container = panel.locator(".artifact-library-container")
    first_item = container.locator("> *").first
    print("Newest artifact item:", repr(first_item.inner_text()[:60]))

    more_btn = first_item.locator('button:has-text("more_vert")').first
    if not more_btn.is_visible():
        more_btn = panel.locator('button:has-text("more_vert")').first

    more_btn.click(force=True)
    page.wait_for_timeout(1500)

    pdf_item = page.locator('[role="menuitem"]:has-text("PDF")').first
    print("PDF menu item visible:", pdf_item.is_visible())

    dl_url = None
    try:
        with browser.expect_page(timeout=8000) as p_info:
            pdf_item.click(force=True)
        popup = p_info.value
        try:
            with popup.expect_download(timeout=10000) as dl_info:
                dl = dl_info.value
                dl_url = dl.url
                print("Captured download URL:", dl_url)
        except Exception as e:
            print("Download listener note:", e)
    except Exception as e:
        print("Popup listener note:", e)

    browser.close()
    pw.stop()
    return dl_url


def fetch_pdf(dl_url: str):
    print(f"\nStep 6: Fetching PDF binary from URL: {dl_url[:80]}...")
    pw = sync_playwright().start()
    browser = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    page.goto(NOTEBOOK_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    res = page.request.get(dl_url)
    print("Fetch response status:", res.status)
    if res.ok:
        PDF_PATH.write_bytes(res.body())
        print(f"SUCCESS! Wrote {len(res.body())} bytes to {PDF_PATH}")
    else:
        print("ERROR: Fetch failed with status", res.status)
        browser.close()
        pw.stop()
        return False

    browser.close()
    pw.stop()
    return True


def render_png():
    print("\nStep 7: Rendering PDF pages to PNG...")
    doc = fitz.open(str(PDF_PATH))
    print(f"Total pages: {len(doc)}")
    for i, p in enumerate(doc):
        pix = p.get_pixmap(dpi=150)
        img_file = SLIDES_PNG_DIR / f"slide_{i+1}.png"
        pix.save(str(img_file))
        print(f"Rendered: {img_file} ({pix.width}x{pix.height})")


def main():
    dl_url = run_generation()
    if not dl_url:
        print("ERROR: Could not capture download URL!")
        return 1
    if not fetch_pdf(dl_url):
        return 1
    render_png()
    print("\nALL TASKS COMPLETED SUCCESSFULLY!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
