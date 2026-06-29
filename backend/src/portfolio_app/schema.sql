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
