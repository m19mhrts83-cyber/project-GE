-- KURASHIFT: 保険 契約者貸付（負債）口座
insert into public.portfolio_accounts (id, name, kind, institution, ingest, notes)
values
  ('sony_life_policy_loan', 'ソニー契約者貸付（真治）', 'insurance_loan', 'ソニー生命', 'web_playwright', '解約返戻照会ページの契約者貸付＋自動振替。不動産頭金枠の把握用'),
  ('sony_life_chikage_policy_loan', 'ソニー契約者貸付（千景）', 'insurance_loan', 'ソニー生命', 'web_playwright', '同上・千景名義'),
  ('prudential_life_policy_loan', 'PRU契約者貸付（真治）', 'insurance_loan', 'プルデンシャル生命', 'manual', '手登録 PRUDENTIAL_LOAN_JPY'),
  ('prudential_life_chikage_policy_loan', 'PRU契約者貸付（千景）', 'insurance_loan', 'プルデンシャル生命', 'manual', '手登録 PRUDENTIAL_CHIKAGE_LOAN_JPY')
on conflict (id) do nothing;
