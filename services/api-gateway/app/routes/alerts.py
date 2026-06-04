import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from app.config import settings

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.api_route("", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def forward_alert(request: Request, path: str = ""):
    """
    Forwards alert requests to the internal Alert Service.
    """
    body = await request.body()
    url = f"{settings.alert_service_url}/api/v1/alerts"
    if path:
        url = f"{url}/{path}"

    headers = dict(request.headers)
    # Remove host header so httpx uses the correct target host
    headers.pop("host", None)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=url,
                content=body,
                headers=headers,
                params=request.query_params,
                timeout=settings.proxy_timeout_seconds
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Error connecting to upstream Alert Service: {str(exc)}")
