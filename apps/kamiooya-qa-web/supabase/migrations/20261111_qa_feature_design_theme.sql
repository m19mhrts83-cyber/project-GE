-- (5) ロゴに合わせた配色（案A）の段階公開スイッチ。追加のみ。最初は off（誰にも出ない）。
insert into public.qa_feature_flags (feature, stage)
values ('design_theme', 'off')
on conflict (feature) do nothing;
