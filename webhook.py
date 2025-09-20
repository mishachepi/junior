import os
import httpx
from fastapi import FastAPI, Request, Response

FORWARD_URL = os.environ.get("FORWARD_URL", "https://httpbin.org/anything")

app = FastAPI()

client = httpx.AsyncClient()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_request(path: str, request: Request):
    """
    get and forward request
    """
    forward_to_url = f"{FORWARD_URL}/{path}"

    body = await request.body()
    
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}

    proxied_response = await client.request(
        method=request.method,
        url=forward_to_url,
        params=request.query_params,
        content=body,
        headers=headers
    )

    return Response(
        content=proxied_response.content,
        status_code=proxied_response.status_code,
        headers=dict(proxied_response.headers)
    )
