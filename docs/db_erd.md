# DB ERD

이 문서는 `backend/src/portfolio_app/schema.sql`의 현재 SQLite 스키마를 기준으로 작성했습니다.
현재 애플리케이션 스키마 버전은 `1`입니다.

```mermaid
erDiagram
    accounts ||--o{ holdings : owns
    assets ||--o{ holdings : tracks
    accounts |o--o{ transactions : records
    assets |o--o{ transactions : records
    assets ||--o{ price_snapshots : priced_by
    import_runs ||--o{ import_rows : contains

    schema_migrations {
        integer version PK
        text applied_at
    }

    accounts {
        integer id PK
        text name
        text type
        text currency
        text created_at
        text updated_at
    }

    assets {
        integer id PK
        text symbol
        text name
        text type
        text currency
        text market
        real manual_price_krw
        text created_at
        text updated_at
    }

    holdings {
        integer id PK
        integer account_id FK
        integer asset_id FK
        real quantity
        real average_cost
        text created_at
        text updated_at
    }

    transactions {
        integer id PK
        text occurred_on
        text type
        integer account_id FK
        integer asset_id FK
        real quantity
        real amount
        text currency
        real fx_rate_to_krw
        text memo
        text created_at
    }

    price_snapshots {
        integer id PK
        integer asset_id FK
        text source
        real price
        text currency
        real price_krw
        text fetched_at
        text status
        text error_message
    }

    fx_rates {
        integer id PK
        text base_currency
        text quote_currency
        real rate
        text source
        text fetched_at
    }

    goals {
        integer id PK
        text name
        text type
        real target_amount_krw
        text created_at
        text updated_at
    }

    import_runs {
        integer id PK
        text filename
        text status
        text created_at
    }

    import_rows {
        integer id PK
        integer import_run_id FK
        integer row_number
        text status
        text raw_json
        text message
    }

    backups {
        integer id PK
        text path
        text reason
        text created_at
    }

    settings {
        text key PK
        text value
        text updated_at
    }
```

## 테이블 역할

| 테이블 | 역할 |
| --- | --- |
| `schema_migrations` | 적용된 스키마 버전을 기록합니다. 현재 `SCHEMA_VERSION = 1`입니다. |
| `accounts` | 현금, 적금, 증권, 가상자산 지갑, 부채 계좌를 저장합니다. |
| `assets` | 현금성 자산, 적금, 주식/ETF, 가상자산, 부채 같은 평가 대상 자산을 저장합니다. |
| `holdings` | 특정 계좌가 특정 자산을 얼마나 보유하는지 저장하는 현재 잔고 테이블입니다. |
| `transactions` | 입금, 출금, 매수, 매도, 배당, 이자, 수수료, 부채 상환, 조정 이력을 저장합니다. |
| `price_snapshots` | 자산별 수동 가격 또는 시장 데이터 동기화 결과를 시간순으로 저장합니다. |
| `fx_rates` | 외화 자산 평가에 사용할 환율 스냅샷을 저장합니다. |
| `goals` | 순자산 목표와 월 소득 목표를 저장합니다. |
| `import_runs` | CSV 가져오기 실행 단위를 저장하기 위한 테이블입니다. |
| `import_rows` | CSV 가져오기 실행에 포함된 개별 행과 매핑 상태를 저장합니다. |
| `backups` | 앱이 생성하거나 감지한 SQLite 백업 파일의 메타데이터를 저장합니다. |
| `settings` | 앱 설정을 key-value 형태로 저장합니다. |

## 관계와 삭제 규칙

| 관계 | 제약 | 삭제 동작 |
| --- | --- | --- |
| `holdings.account_id` -> `accounts.id` | 필수 FK | 계좌 삭제 시 보유자산도 삭제됩니다. |
| `holdings.asset_id` -> `assets.id` | 필수 FK | 자산 삭제 시 보유자산도 삭제됩니다. |
| `transactions.account_id` -> `accounts.id` | 선택 FK | 계좌 삭제 시 거래 이력의 계좌 참조만 `NULL`이 됩니다. |
| `transactions.asset_id` -> `assets.id` | 선택 FK | 자산 삭제 시 거래 이력의 자산 참조만 `NULL`이 됩니다. |
| `price_snapshots.asset_id` -> `assets.id` | 필수 FK | 자산 삭제 시 가격 스냅샷도 삭제됩니다. |
| `import_rows.import_run_id` -> `import_runs.id` | 필수 FK | 가져오기 실행 삭제 시 행 기록도 삭제됩니다. |

## 주요 제약

| 대상 | 제약 |
| --- | --- |
| `accounts.type` | `cash`, `savings`, `brokerage`, `crypto_wallet`, `debt` 중 하나여야 합니다. |
| `assets.type` | `cash`, `savings`, `stock_etf`, `crypto`, `debt` 중 하나여야 합니다. |
| `assets(symbol, market)` | `symbol`이 `NULL`이 아닐 때 같은 시장에서 중복될 수 없습니다. |
| `holdings(account_id, asset_id)` | 한 계좌와 한 자산 조합은 하나의 현재 잔고만 가질 수 있습니다. |
| `transactions.type` | `deposit`, `withdrawal`, `buy`, `sell`, `dividend`, `interest`, `fee`, `debt_payment`, `adjustment` 중 하나여야 합니다. |
| `price_snapshots.status` | `ok`, `stale`, `failed`, `manual` 중 하나여야 합니다. |
| `fx_rates(base_currency, quote_currency, fetched_at)` | 같은 시각의 동일 통화쌍 환율은 중복될 수 없습니다. |
| `goals.type` | `net_worth`, `monthly_income` 중 하나여야 합니다. |
| `import_runs.status` | `previewed`, `confirmed`, `failed` 중 하나여야 합니다. |
| `import_rows.status` | `mapped`, `ignored`, `error` 중 하나여야 합니다. |

## 논리적 참조

`fx_rates`는 FK를 갖지 않습니다. 대신 요약 계산 시 `assets.currency`와 `fx_rates.base_currency`를 비교하고, `quote_currency = 'KRW'`인 최신 환율을 조회합니다.

`goals`도 다른 테이블을 직접 참조하지 않습니다. 목표 진행률은 런타임에 `holdings`, `assets`, `transactions`, `price_snapshots`, `fx_rates`를 바탕으로 계산한 순자산 또는 월 소득과 비교해 산출됩니다.
