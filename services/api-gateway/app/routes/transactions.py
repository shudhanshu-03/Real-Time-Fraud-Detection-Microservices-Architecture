import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from app.config import settings

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("")
async def forward_transaction(request: Request):
    """
    Forwards transaction POST requests to the internal Transaction Service.
    """
    body = await request.body()
    url = f"{settings.transaction_service_url}/api/v1/transactions"

    headers = dict(request.headers)
    # Remove host header so httpx uses the correct target host
    headers.pop("host", None)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, content=body, headers=headers, timeout=settings.proxy_timeout_seconds)
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Error connecting to upstream Transaction Service: {str(exc)}")
