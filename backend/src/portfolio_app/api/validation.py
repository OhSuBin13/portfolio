from fastapi import HTTPException, status

ACCOUNT_SEQ_REQUIRED_MESSAGE = "Toss 계좌 식별자를 입력해 주세요."


def normalize_account_seq(account_seq: str) -> str:
    normalized = account_seq.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ACCOUNT_SEQ_REQUIRED_MESSAGE,
        )
    return normalized
