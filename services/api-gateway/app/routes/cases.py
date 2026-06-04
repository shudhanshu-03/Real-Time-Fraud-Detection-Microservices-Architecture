import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from app.config import settings

router = APIRouter(prefix="/cases", tags=["cases"])


@router.api_route("", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def forward_case(request: Request, path: str = ""):
    """
    Forwards case requests to the internal Case Management Service.
    """
    body = await request.body()
    url = f"{settings.case_service_url}/api/v1/cases"
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
        raise HTTPException(status_code=502, detail=f"Error connecting to upstream Case Management Service: {str(exc)}")
