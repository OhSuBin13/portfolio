# Buy/Sell Cash Leg Design

Date: 2026-06-23
Status: Draft for review

## 1. Purpose

매수와 매도 거래가 시장성 자산 보유 수량만 바꾸는 현재 모델을 보완한다.
목표는 실제 현금 잔고와 보유자산이 함께 움직이게 해서 순자산, 성장기록,
거래 장부가 같은 경제적 사건을 일관되게 설명하도록 만드는 것이다.

이 설계는 전체 회계 시스템을 도입하지 않는다. 이 앱은 개인용 로컬
포트폴리오 앱이며, 필요한 범위는 증권 매매에서 발생하는 현금 결제 흐름을
명시하는 것이다.

## 2. Current Behavior

현재 `apply_transaction()`은 하나의 거래가 하나의 `holdings` row만 변경한다고
가정한다.

- `buy`: 시장성 자산 수량을 늘리고 평균단가를 갱신한다.
- `sell`: 시장성 자산 수량을 줄이고 평균단가는 유지한다.
- `deposit`, `withdrawal`, `dividend`, `interest`, `fee`: 현금성 자산 잔고를 바꾼다.
- `debt_payment`: 부채 자산 잔고를 줄인다.
- `adjustment`: 선택한 자산의 잔고를 직접 맞춘다.

이 구조에서는 매수 시 결제 현금이 줄지 않고, 매도 시 결제 현금이 늘지
않는다. 사용자가 현금 거래를 별도로 입력하면 순자산이 이중 계상될 수 있고,
입력하지 않으면 매수 금액이 외부 유입이나 투자 성과처럼 보일 수 있다.

성장기록은 `deposit`, `withdrawal`, `debt_payment`를 외부 현금흐름으로 보고,
`dividend`, `interest`를 소득으로 본다. 따라서 매매 현금 leg는 외부
현금흐름과 분리되어야 한다.

## 3. Goals

- 매수 한 번이 시장성 자산 증가와 결제 현금 감소를 같은 DB transaction에서
  처리한다.
- 매도 한 번이 시장성 자산 감소와 결제 현금 증가를 같은 DB transaction에서
  처리한다.
- 매매 결제 현금흐름은 성장률 계산에서 외부 입출금으로 취급하지 않는다.
- 기존 입금, 출금, 배당, 이자, 수수료, 부채 상환, 조정 거래의 의미를 유지한다.
- 기존 수동 시작잔고 입력과 직접 보유자산 조정 흐름을 깨지 않는다.
- 과거 `buy`/`sell` 거래는 자동 추정으로 현금 leg를 만들지 않는다.

## 4. Non-Goals

- 전체 double-entry accounting ledger 도입.
- 자동 FX 환전 거래 생성.
- 세금, 실현손익, FIFO/LIFO 세무 원장 계산.
- 증권사 체결내역 자동 반영.
- 과거 매매 거래의 자동 현금 보정.

## 5. Options Considered

### Option A: `buy`/`sell` row에 현금 필드 추가

`transactions`에 `settlement_account_id`, `settlement_asset_id`,
`settlement_amount` 같은 필드를 추가한다. 구현은 작지만 한 row가 두 holdings를
바꾸게 되어 현재 `TransactionCommand`와 repository 경계가 흐려진다. 거래 장부도
시장 leg와 현금 leg를 분리해서 설명하기 어렵다.

### Option B: 완전한 transaction legs 테이블 도입

`transaction_groups`와 `transaction_legs`를 새로 만들고 모든 거래를 leg 기반으로
재모델링한다. 장기적으로 가장 정합적이지만 현재 앱의 단일 row 기반 테스트,
API, UI를 광범위하게 바꿔야 한다.

### Option C: 기존 `transactions` row를 유지하되 매매만 grouped legs로 저장

매수/매도 명령은 하나의 trade group 아래 여러 `transactions` row를 만든다.
시장성 자산 leg는 기존 `buy`/`sell` 타입을 사용하고, 결제 현금 leg는 새 내부
현금흐름 타입을 사용한다. 기존 단일 거래 타입은 계속 단일 row로 처리한다.

권장안은 Option C이다. 현재 모델과 테스트를 가장 많이 보존하면서도 매매의
현금 이동을 명시할 수 있다.

## 6. Recommended Model

### 6.1 Trade Group

새 테이블 `transaction_groups`를 둔다.

```sql
create table transaction_groups (
  id integer primary key,
  type text not null check (type in ('trade')),
  occurred_on text not null,
  memo text not null default '',
  created_at text not null default current_timestamp
);
```

`transactions`에는 다음 컬럼을 추가한다.

```sql
group_id integer references transaction_groups(id) on delete set null,
group_role text check (
  group_role is null
  or group_role in ('market_leg', 'cash_leg', 'fee_leg')
)
```

기존 거래는 `group_id = null`이다. 새 매매 거래만 group을 가진다.

### 6.2 Internal Cash Leg Types

`transactions.type`에 내부 결제 타입을 추가한다.

- `trade_cash_out`: 매수 결제 현금 감소.
- `trade_cash_in`: 매도 결제 현금 증가.

이 두 타입은 cash-like asset, 즉 `cash` 또는 `savings` 자산에만 기록할 수 있다.
성장기록의 외부 현금흐름 조회에는 포함하지 않는다. 거래 장부에서는 기본적으로
상위 trade group 하나로 보여주고, 상세 보기에서 leg를 펼칠 수 있게 한다.

### 6.3 Buy Command

매수 명령은 다음 입력을 받는다.

- `occurred_on`
- `market_account_id`
- `market_asset_id`
- `settlement_account_id`
- `settlement_asset_id`
- `quantity`
- `gross_amount`
- `currency`
- `fx_rate_to_krw`
- `fee_amount`
- `memo`

처리 순서는 하나의 DB transaction 안에서 실행한다.

1. 시장성 자산이 `stock_etf`인지 확인한다.
2. 결제 자산이 `cash` 또는 `savings`인지 확인한다.
3. 시장성 자산 통화와 결제 자산 통화가 같은지 확인한다.
4. 비-KRW 통화이면 `fx_rate_to_krw`가 있는지 확인한다.
5. `quantity`, `gross_amount`, `fee_amount`가 유효한지 확인한다.
6. 결제 현금 잔고가 `gross_amount + fee_amount` 이상인지 확인한다.
7. `transaction_groups` row를 만든다.
8. `buy` market leg를 만들고 시장성 보유 수량과 평균단가를 갱신한다.
9. `trade_cash_out` cash leg를 만들고 결제 현금 잔고를 `gross_amount`만큼 줄인다.
10. `fee_amount > 0`이면 같은 group에 `fee` leg를 만들고 결제 현금 잔고를
    `fee_amount`만큼 추가로 줄인다.

평균단가는 `gross_amount + fee_amount`를 기준으로 갱신한다. 이는 사용자가
실제로 투자한 취득 원가를 보유자산 평균단가에 반영하기 위한 정책이다.

### 6.4 Sell Command

매도 명령은 다음 입력을 받는다.

- `occurred_on`
- `market_account_id`
- `market_asset_id`
- `settlement_account_id`
- `settlement_asset_id`
- `quantity`
- `gross_amount`
- `currency`
- `fx_rate_to_krw`
- `fee_amount`
- `memo`

처리 순서는 하나의 DB transaction 안에서 실행한다.

1. 시장성 자산 보유 수량이 매도 수량 이상인지 확인한다.
2. 결제 자산이 `cash` 또는 `savings`인지 확인한다.
3. 시장성 자산 통화와 결제 자산 통화가 같은지 확인한다.
4. 비-KRW 통화이면 `fx_rate_to_krw`가 있는지 확인한다.
5. `gross_amount - fee_amount`가 0 이상인지 확인한다.
6. `transaction_groups` row를 만든다.
7. `sell` market leg를 만들고 시장성 보유 수량을 줄인다.
8. `trade_cash_in` cash leg를 만들고 결제 현금 잔고를 `gross_amount`만큼 늘린다.
9. `fee_amount > 0`이면 같은 group에 `fee` leg를 만들고 결제 현금 잔고를
   `fee_amount`만큼 줄인다.

매도는 기존 정책처럼 평균단가를 유지한다. 실현손익 계산은 후속 기능으로 둔다.

## 7. API Shape

기존 `POST /api/transactions`는 단일-leg 거래용으로 유지한다.

새 엔드포인트를 추가한다.

```text
POST /api/trades
GET /api/trades
GET /api/trades/{group_id}
```

`POST /api/trades`는 `type = buy | sell`을 받으며, 성공 시 group과 legs를 함께
반환한다. 기존 `GET /api/transactions`는 group metadata를 포함해 row를 반환하되,
UI가 기본적으로 trade group 단위로 표시할 수 있도록 별도 `GET /api/trades`를
제공한다.

기존 `/api/transactions`에 `buy`/`sell` POST를 계속 허용할지는 구현 단계에서
다음 정책으로 전환한다.

- 초기 전환 기간: legacy `buy`/`sell` POST는 유지하되 응답 또는 UI에서
  "현금 미반영"으로 표시한다.
- 전환 완료 후: UI는 `/api/trades`만 사용하고, 직접 `buy`/`sell` 단일-leg
  API 호출은 400으로 거부한다.

## 8. UI Flow

거래 화면에서 `매수` 또는 `매도`를 선택하면 일반 거래 form이 trade form으로
전환된다.

필수 입력:

- 시장 계좌와 시장 자산.
- 결제 현금 계좌와 결제 현금 자산.
- 수량.
- 총 체결금액.
- 수수료. 기본값은 0.
- 외화 거래 환율.

입금, 출금, 배당, 이자, 수수료, 부채 상환, 조정은 기존 단일 거래 form을 사용한다.
매수/매도가 아닌 타입에서는 수량 입력칸을 숨기거나 비활성화한다.

거래 장부는 기본적으로 한 매매를 한 행으로 보여준다.

- 매수: `시장 자산 +수량`, `결제 현금 -금액`.
- 매도: `시장 자산 -수량`, `결제 현금 +금액`.
- 상세 펼침: market leg, cash leg, fee leg.

## 9. Growth And Summary Semantics

요약 계산은 holdings를 기준으로 하므로 trade group 도입 후에도 별도 계산 경로가
필요하지 않다. 중요한 변화는 holdings가 실제 현금 결제까지 반영하게 된다는 점이다.

성장기록의 외부 현금흐름은 계속 다음 타입만 포함한다.

- `deposit`
- `withdrawal`
- `debt_payment`

소득은 계속 다음 타입만 포함한다.

- `dividend`
- `interest`

`trade_cash_out`, `trade_cash_in`, `buy`, `sell`, `fee`, `adjustment`는 외부
현금흐름에서 제외한다. 따라서 현금을 주식으로 바꾸거나 주식을 현금으로 바꾸는
내부 재배분은 성장률을 왜곡하지 않는다.

## 10. Migration Policy

기존 `buy`/`sell` 거래는 자동 보정하지 않는다. 과거 거래만 보고 어떤 현금
계좌에서 결제되었는지, 수수료가 얼마였는지, 사용자가 이미 별도 입출금을
넣었는지 알 수 없기 때문이다.

마이그레이션은 다음만 수행한다.

1. `transaction_groups` 테이블 생성.
2. `transactions.group_id`, `transactions.group_role` 컬럼 추가.
3. `transactions.type` check constraint에 `trade_cash_out`, `trade_cash_in` 추가.
4. 기존 row는 모두 group 없는 legacy row로 유지.

UI에서는 group 없는 기존 `buy`/`sell`을 "현금 미반영 기존 거래"로 표시할 수 있다.
사용자는 필요하면 수동 조정이나 새 trade 입력으로 앞으로의 거래만 정합적으로
관리한다.

## 11. Error Handling

대표 오류 메시지는 다음 정책을 따른다.

- 결제 현금 계좌를 선택하지 않음: `결제 현금 계좌를 선택해 주세요.`
- 결제 현금 자산이 cash-like가 아님: `매매 결제는 현금성 자산으로만 처리할 수 있습니다.`
- 통화 불일치: `시장 자산 통화와 결제 현금 통화가 같아야 합니다.`
- 현금 부족: `결제 현금 잔고가 부족합니다.`
- 보유 수량 부족: `보유 수량보다 많이 매도할 수 없습니다.`
- 외화 환율 누락: `외화 매매에는 환율을 입력해 주세요.`

모든 leg 생성과 holdings 갱신은 하나의 DB transaction 안에서 처리한다. 중간 오류가
나면 group, market leg, cash leg, fee leg, holdings 변경이 모두 rollback되어야 한다.

## 12. Testing Strategy

Backend service tests:

- 매수는 시장성 보유 수량을 늘리고 결제 현금을 줄인다.
- 매도는 시장성 보유 수량을 줄이고 결제 현금을 늘린다.
- 수수료는 평균단가와 결제 현금에 정책대로 반영된다.
- 현금 부족, 수량 부족, 통화 불일치, 환율 누락을 거부한다.
- leg 중 하나가 실패하면 모든 holdings와 transaction row가 rollback된다.
- `trade_cash_out`과 `trade_cash_in`은 성장기록 외부 현금흐름에 포함되지 않는다.

API tests:

- `POST /api/trades` request/response schema.
- group과 legs가 함께 반환되는지.
- 기존 `/api/transactions` 단일-leg 거래가 계속 동작하는지.
- legacy `buy`/`sell` 정책이 의도대로 유지 또는 거부되는지.

Frontend tests:

- 매수/매도 선택 시 결제 현금 계좌/자산 필드가 나타난다.
- 매수/매도 외 거래에서는 수량 필드가 숨겨지거나 비활성화된다.
- trade payload가 `buildTransactionPayload()`와 분리된 trade 전용 builder를 사용한다.
- 거래 장부가 grouped trade를 한 행으로 표시하고 leg 상세를 확인할 수 있다.

## 13. Implementation Sequence

1. 서비스 레벨 RED 테스트로 buy/sell cash leg 요구사항을 고정한다.
2. `transaction_groups`와 `transactions` group metadata migration을 추가한다.
3. repository helper를 추가해 group과 legs를 하나의 transaction으로 저장한다.
4. `apply_trade()` service를 추가하고 기존 `apply_transaction()`은 단일-leg 전용으로 둔다.
5. `/api/trades` route와 Pydantic request/response model을 추가한다.
6. 성장기록 cashflow 조회가 내부 trade cash types를 제외한다는 회귀 테스트를 추가한다.
7. 거래 화면을 trade form과 single-leg form으로 분리한다.
8. legacy `buy`/`sell` 처리 정책을 UI/API에서 명확히 적용한다.

## 14. Review Checklist

- 새 설계는 전체 double-entry ledger가 아니라 매매 결제 cash leg만 다룬다.
- 기존 수동 잔고 조정과 단일 거래 타입의 의미를 보존한다.
- 매매 내부 현금흐름은 성장률 외부 현금흐름에서 제외된다.
- 과거 `buy`/`sell`은 자동 보정하지 않는다.
- 구현 범위는 backend service, migration, API, frontend form, tests로 분해 가능하다.
