-- IFA石川さんメモ＋アクサを保険配分の正とする notes 更新
insert into public.advisor_notes (advisor, note_date, body, related_accounts)
values (
  'ishikawa',
  current_date,
  'アクサ生命の特別勘定比率は石川さん（IFA）のアドバイスを反映した正とする。ソニー・プルデンシャルも同方針で揃えた。今後の比率変更はまずアクサを更新し、/portfolio で他社との差分を確認してから動かす。月額・配分％はスクレイプ優先、失敗時はスナップショット。',
  array['axa_life','sony_life','sony_life_chikage','prudential_life','prudential_life_chikage']
);

update public.portfolio_accounts
set notes = 'IFA石川さん反映の配分正本（参考）。週次で評価額取得。特別勘定はスクレイプ／snap'
where id = 'axa_life';

update public.portfolio_accounts
set notes = coalesce(notes,'') || case
  when notes is null or notes = '' then '対アクサ比較対象'
  when notes like '%対アクサ%' then ''
  else '／対アクサ比較対象'
end
where id in ('sony_life','sony_life_chikage','prudential_life','prudential_life_chikage');
