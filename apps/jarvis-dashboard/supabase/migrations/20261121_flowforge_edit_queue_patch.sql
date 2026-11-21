-- FlowForge 修正文の待ち箱に「直接編集」を足す（2026-11-21）。
-- kind=patch: ops.operations を、Mac のプログラムがノード ID・矢印 ID の指定で直接適用する（AIアシスタントを通さない）。
-- kind=edit で ops.lockStructure=true: ノードか矢印が増減したら、送信前の状態まで自動で戻す。
alter table public.flowforge_edit_queue add column if not exists ops jsonb;
alter table public.flowforge_edit_queue drop constraint if exists flowforge_edit_queue_kind_check;
alter table public.flowforge_edit_queue
  add constraint flowforge_edit_queue_kind_check check (kind in ('edit', 'undo', 'patch'));
