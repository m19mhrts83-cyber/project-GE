-- FlowForge 修正文の待ち箱に「取り消し」を足す（2026-11-21）。
-- kind=undo の行は、ref_id の送信の直前の状態まで、Mac のプログラムが FlowForge の「元に戻す」を押す。
alter table public.flowforge_edit_queue
  add column if not exists kind text not null default 'edit' check (kind in ('edit', 'undo')),
  add column if not exists ref_id uuid references public.flowforge_edit_queue (id);
