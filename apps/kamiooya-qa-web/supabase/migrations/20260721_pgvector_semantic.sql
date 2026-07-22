create extension if not exists vector with schema extensions;

alter table public.comments
  add column if not exists embedding extensions.vector(768);

alter table public.knowledge_chunks
  add column if not exists embedding extensions.vector(768);

create or replace function public.match_comments_semantic(
  query_embedding extensions.vector(768),
  match_threshold float default 0.55,
  match_count int default 20
)
returns table (
  source_type text,
  comment_id text,
  posted_at timestamptz,
  author_name text,
  content text,
  similarity float
)
language sql
stable
as $$
  select
    c.source_type,
    c.comment_id,
    c.posted_at,
    c.author_name,
    c.content,
    1 - (c.embedding <=> query_embedding) as similarity
  from public.comments c
  where c.embedding is not null
    and 1 - (c.embedding <=> query_embedding) >= match_threshold
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function public.match_chunks_semantic(
  query_embedding extensions.vector(768),
  match_threshold float default 0.55,
  match_count int default 12
)
returns table (
  chunk_key text,
  source_id bigint,
  start_sec integer,
  end_sec integer,
  speaker text,
  content text,
  similarity float
)
language sql
stable
as $$
  select
    kc.chunk_key,
    kc.source_id,
    kc.start_sec,
    kc.end_sec,
    kc.speaker,
    kc.content,
    1 - (kc.embedding <=> query_embedding) as similarity
  from public.knowledge_chunks kc
  where kc.embedding is not null
    and 1 - (kc.embedding <=> query_embedding) >= match_threshold
  order by kc.embedding <=> query_embedding
  limit match_count;
$$;

create index if not exists comments_embedding_ivfflat_idx
  on public.comments using ivfflat (embedding extensions.vector_cosine_ops)
  with (lists = 100);

create index if not exists knowledge_chunks_embedding_ivfflat_idx
  on public.knowledge_chunks using ivfflat (embedding extensions.vector_cosine_ops)
  with (lists = 100);
