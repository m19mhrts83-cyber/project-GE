-- glucon_material_items: cycle_closed status（Q6 · グルコン日経過で活動材料を注入対象外に）
-- 適用: scripts/jarvis_supabase_apply_sql.py 本ファイル

alter table public.glucon_material_items
  drop constraint if exists glucon_material_items_status_check;

alter table public.glucon_material_items
  add constraint glucon_material_items_status_check
  check (status in ('pending', 'used', 'skipped', 'cycle_closed'));

comment on column public.glucon_material_items.status is
  'pending | used | skipped | cycle_closed（活動材料·グルコン日経過）';
