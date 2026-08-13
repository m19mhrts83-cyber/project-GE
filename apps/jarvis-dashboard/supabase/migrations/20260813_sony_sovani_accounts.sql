-- 真治のソニー生命を一時払と SOVANI（月4,000円）に分ける。
-- 子ども SOVANI（珠己・円香・紗和）は教育用の継続貯蓄基準として別口座。
update public.portfolio_accounts
set
  name = 'ソニー生命（真治・一時払）',
  notes = 'KURASHIFT Core。変額確定年金15年70歳一時払。SOVANIとは分けて評価／対アクサ比較対象'
where id = 'sony_life';

insert into public.portfolio_accounts (id, name, kind, institution, ingest, notes)
values
  (
    'sony_life_sovani',
    'ソニー生命（真治・SOVANI）',
    'insurance_sony',
    'ソニー生命',
    'monthly_form',
    '月4,000円。2023-07〜大垣共立32,725円のうち4,000円。一時払とは分けて評価。公式評価は未取得'
  ),
  (
    'sony_life_sovani_kids',
    'ソニー生命 SOVANI（子ども）',
    'insurance_sony',
    'ソニー生命',
    'monthly_form',
    '珠己・円香・紗和 各月4,000円。教育・資産運用の勉強用。このまま貯め続けた場合の基準値。成人の対アクサ評価には混ぜない'
  )
on conflict (id) do update
set
  name = excluded.name,
  notes = excluded.notes,
  active = true;
