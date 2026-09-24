-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Create a table to store your documents
create table policies (
  id bigserial primary key,
  content text, -- corresponds to Document.pageContent
  metadata jsonb, -- corresponds to Document.metadata
  embedding vector(768) -- 768 works for Gemini text-embedding-004
);

-- Create a function to search for policies
create or replace function match_policies (
  query_embedding vector(768),
  match_threshold float,
  match_count int
)
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language sql stable
as $$
  select
    policies.id,
    policies.content,
    policies.metadata,
    1 - (policies.embedding <=> query_embedding) as similarity
  from policies
  where 1 - (policies.embedding <=> query_embedding) > match_threshold
  order by policies.embedding <=> query_embedding
  limit match_count;
$$;
