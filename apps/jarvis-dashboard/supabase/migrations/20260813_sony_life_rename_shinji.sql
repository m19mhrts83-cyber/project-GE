-- ソニー生命の表示名を商品名「変額」から契約者「真治」へ揃える。
-- 千景側も変額確定年金のため、「変額 vs 千景」だと区分が崩れる。
update public.portfolio_accounts
set
  name = 'ソニー生命（真治）',
  notes = 'KURASHIFT Core。変額確定年金15年70歳一時払。千景と分けて表示／対アクサ比較対象'
where id = 'sony_life';

update public.portfolio_accounts
set
  notes = 'KURASHIFT Core。変額確定年金15年65歳。真治と分けて表示／対アクサ比較対象'
where id = 'sony_life_chikage';
