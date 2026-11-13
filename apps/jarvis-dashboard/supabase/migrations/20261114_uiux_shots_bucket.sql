-- UI/UX の好みループ（Nody /uiux）の画像置き場。2026-11-14
-- 非公開バケット。読み書きは service_role（loopware のサーバ・scripts/jarvis_uiux_loop.py）だけ。
-- 画面には loopware のサーバが1時間の署名付き URL を出す。既存の表には触らない。
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('uiux-shots', 'uiux-shots', false, 5242880, array['image/png', 'image/jpeg', 'image/webp', 'image/gif'])
on conflict (id) do nothing;
