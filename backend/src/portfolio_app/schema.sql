create table if not exists schema_migrations (
  version integer primary key,
  applied_at text not null default current_timestamp
);

create table if not exists fx_rates (
  id integer primary key,
  base_currency text not null check (base_currency in ('USD','KRW')),
  quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
  rate real not null,
  source text not null,
  fetched_at text not null,
  change_percent real,
  unique(base_currency, quote_currency, fetched_at)
);

create index if not exists idx_fx_rates_summary_pair_latest
on fx_rates(base_currency, quote_currency, fetched_at desc, id desc);

create table if not exists goals (
  id integer primary key,
  name text not null,
  type text not null check (type in ('net_worth','monthly_income')),
  target_amount_krw real not null check (target_amount_krw > 0),
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists backups (
  id integer primary key,
  path text not null,
  reason text not null,
  created_at text not null default current_timestamp
);

create table if not exists settings (
  key text primary key,
  value text not null,
  updated_at text not null default current_timestamp
);

create table if not exists toss_order_import_runs (
  id integer primary key,
  account_seq text not null,
  status_filter text not null check (status_filter in ('OPEN','CLOSED')),
  symbol_filter text,
  from_date text,
  to_date text,
  run_status text not null check (run_status in ('running','success','failed')),
  imported_count integer not null default 0 check (imported_count >= 0),
  error_message text not null default '',
  started_at text not null default current_timestamp,
  completed_at text
);

create table if not exists toss_orders (
  id integer primary key,
  account_seq text not null,
  order_id text not null,
  symbol text not null,
  side text not null,
  order_type text not null,
  time_in_force text not null,
  order_status text not null,
  price text,
  quantity text not null,
  order_amount text,
  currency text not null,
  ordered_at text not null,
  canceled_at text,
  filled_quantity text not null,
  average_filled_price text,
  filled_amount text,
  commission text,
  tax text,
  filled_at text,
  settlement_date text,
  raw_json text not null,
  import_run_id integer references toss_order_import_runs(id) on delete set null,
  imported_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique(account_seq, order_id)
);

create index if not exists idx_toss_orders_account_ordered_at
on toss_orders(account_seq, ordered_at desc, id desc);

create index if not exists idx_toss_orders_account_status
on toss_orders(account_seq, order_status, ordered_at desc, id desc);

create index if not exists idx_toss_orders_account_symbol
on toss_orders(account_seq, symbol, ordered_at desc, id desc);
