from fastapi import HTTPException


def validate_keyword(keyword: str) -> str:
    value = keyword.strip()
    if len(value) < 3:
        raise HTTPException(status_code=400, detail="Keyword must be at least 3 characters")
    return value
