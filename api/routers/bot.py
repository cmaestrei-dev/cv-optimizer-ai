"""Tokens del bot local: la persona los crea y revoca desde la web; el bot los usa en vez de una sesión."""

from fastapi import APIRouter, HTTPException, Response, status

from api.auth import PersonAccount
from api.schemas import BotTokenCreatedOut, BotTokenIn, BotTokenOut
from core.bot import tokens

router = APIRouter(tags=["bot"])


def _out(info: tokens.TokenInfo) -> BotTokenOut:
    return BotTokenOut(id=info.id, label=info.label, hint=info.hint, created_at=info.created_at, last_used_at=info.last_used_at)


@router.get("/bot-tokens", response_model=list[BotTokenOut])
def list_tokens(account: PersonAccount) -> list[BotTokenOut]:
    return [_out(t) for t in tokens.list_active(account.username)]


@router.post("/bot-tokens", response_model=BotTokenCreatedOut, status_code=status.HTTP_201_CREATED)
def create_token(body: BotTokenIn, account: PersonAccount) -> BotTokenCreatedOut:
    try:
        info, plain = tokens.create(account.username, body.label)
    except tokens.TokenLimitError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return BotTokenCreatedOut(**_out(info).model_dump(), token=plain)


@router.delete("/bot-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: int, account: PersonAccount) -> Response:
    tokens.revoke(account.username, token_id)  # NotFoundError → 404 (mismo mensaje exista o no en otra cuenta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
