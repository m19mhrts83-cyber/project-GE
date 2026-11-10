-- (5) ロゴに合わせたデザイン（案A: 紺＋オレンジ）の段階公開スイッチ（2026-11-10）。追加のみ。
-- 最初はオフ。松野さんの指示があるまで owner（松野さんだけ）より先には進めない。
insert into public.qa_feature_flags (feature, note) values
  ('brand_theme', '(5) ロゴに合わせたデザイン（案A: 紺を土台にオレンジで目立たせる）')
on conflict (feature) do nothing;
