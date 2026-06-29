# DB ERD

이 문서는 `backend/src/portfolio_app/schema.sql`의 현재 SQLite 스키마를 기준으로 작성했습니다.
현재 애플리케이션 스키마 버전은 `11`입니다.

```mermaid
erDiagram
    schema_migrations {
      integer version PK
      text applied_at
    }
    settings {
      text key PK
      text value
      text updated_at
    }
    fx_rates {
      integer id PK
      text base_currency
      text quote_currency
      real rate
      text source
      text fetched_at
      real change_percent
    }
    goals {
      integer id PK
      text name
      text type
      real target_amount_krw
      text created_at
      text updated_at
    }
    backups {
      integer id PK
      text path
      text reason
      text created_at
    }
    toss_order_import_runs {
      integer id PK
      text account_seq
      text status_filter
      text symbol_filter
      text from_date
      text to_date
      text run_status
      integer imported_count
      text error_message
      text started_at
      text completed_at
    }
    toss_orders {
      integer id PK
      text account_seq
      text order_id
      text symbol
      text side
      text order_type
      text time_in_force
      text order_status
      text price
      text quantity
      text order_amount
      text currency
      text ordered_at
      text canceled_at
      text filled_quantity
      text average_filled_price
      text filled_amount
      text commission
      text tax
      text filled_at
      text settlement_date
      text raw_json
      integer import_run_id FK
      text imported_at
      text updated_at
    }
    toss_order_import_runs ||--o{ toss_orders : import_run_id
```

Toss account and holding data is not represented as local relational source
tables. It is fetched from Toss APIs at read time. Imported Toss order history is
a read-only local cache and does not drive holdings valuation.

## 테이블 역할

| 테이블 | 역할 |
| --- | --- |
| `schema_migrations` | 적용된 스키마 버전을 기록합니다. 현재 `SCHEMA_VERSION = 11`입니다. |
| `settings` | 앱 설정을 key-value 형태로 저장합니다. |
| `fx_rates` | Toss USD/KRW 환율과 선택적 전일대비 변경율 스냅샷을 저장합니다. |
| `goals` | 순자산 목표와 월 소득 목표를 저장합니다. |
| `backups` | 앱이 생성하거나 감지한 SQLite 백업 파일의 메타데이터를 저장합니다. |
| `toss_order_import_runs` | 계좌별 Toss 주문내역 가져오기 실행 상태와 실패 메시지를 저장합니다. |
| `toss_orders` | Toss 주문 응답을 `(account_seq, order_id)` 기준으로 upsert한 읽기 전용 주문내역 캐시입니다. |

## 제거된 로컬 원장 테이블

다음 테이블은 Toss-only brokerage slice에서 더 이상 fresh schema에 생성되지 않으며,
마이그레이션 v10에서 제거됩니다.

- `accounts`
- `assets`
- `holdings`
- `transactions`
- `price_snapshots`
- `portfolio_snapshots`
- legacy `import_runs`
- legacy `import_rows`

## 주요 제약

| 대상 | 제약 |
| --- | --- |
| `fx_rates(base_currency, quote_currency, fetched_at)` | 같은 시각의 동일 통화쌍 환율은 중복될 수 없습니다. |
| `fx_rates.base_currency`, `fx_rates.quote_currency` | 각각 `USD`, `KRW` 중 하나여야 합니다. |
| `goals.type` | `net_worth`, `monthly_income` 중 하나여야 합니다. |
| `goals.target_amount_krw` | 0보다 커야 합니다. |
| `toss_order_import_runs.status_filter` | `OPEN`, `CLOSED` 중 하나여야 합니다. |
| `toss_order_import_runs.run_status` | `running`, `success`, `failed` 중 하나여야 합니다. |
| `toss_order_import_runs.imported_count` | 0 이상이어야 합니다. |
| `toss_orders(account_seq, order_id)` | 계좌별 Toss 주문 식별자는 중복될 수 없습니다. |
| `toss_orders.import_run_id` | 참조한 가져오기 실행이 삭제되면 `NULL`로 보존됩니다. |

## 주요 인덱스

| 인덱스 | 목적 |
| --- | --- |
| `idx_fx_rates_summary_pair_latest` | 통화쌍별 최신 환율을 찾습니다. |
| `idx_toss_orders_account_ordered_at` | 계좌별 주문내역을 주문 시각 역순으로 조회합니다. |
| `idx_toss_orders_account_status` | 계좌와 Toss 주문 상태별 조회를 보조합니다. |
| `idx_toss_orders_account_symbol` | 계좌와 종목별 주문내역 조회를 보조합니다. |

## 논리적 참조

`goals`는 다른 테이블을 직접 참조하지 않습니다. 목표 진행률은 런타임에
Toss holdings와 Toss USD/KRW 환율로 만든 `PortfolioSummary`와 비교해 산출됩니다.

`fx_rates`도 FK를 갖지 않습니다. Toss summary 계산에서 USD 보유자산의 KRW
평가가 필요할 때 Toss FX provider가 반환한 환율을 사용할 수 있습니다.
