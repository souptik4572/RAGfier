from __future__ import annotations

from typing import Any, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel

from app.utils.messages import get_message

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


def error_payload(message_key: str, *, detail: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": get_message(message_key)}
    if detail is not None:
        payload["detail"] = detail
    return payload


def success_payload(message_key: str, **data: Any) -> dict[str, Any]:
    return {"message": get_message(message_key), **data}


def build_response(
    model_type: type[ResponseModelT],
    message_key: str,
    **data: Any,
) -> ResponseModelT:
    return model_type(**success_payload(message_key, **data))


def with_message(model: ResponseModelT, message_key: str) -> ResponseModelT:
    return model.model_copy(update={"message": get_message(message_key)})


def raise_api_error(status_code: int, message_key: str, *, detail: Any = None) -> None:
    raise HTTPException(status_code=status_code, detail=error_payload(message_key, detail=detail))
