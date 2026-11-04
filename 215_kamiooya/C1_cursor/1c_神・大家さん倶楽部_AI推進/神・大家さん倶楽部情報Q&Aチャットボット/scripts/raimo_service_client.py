"""Private automation transport; never put server proof in browser state or a URL."""
import os
from urllib.parse import urlsplit

ORIGIN = "https://ma-54t2keqdelz3.raimo-app.buzz"
PREFIX = "/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0"

def service_payload(url, payload=None):
    parsed=urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != urlsplit(ORIGIN).netloc or not parsed.path.startswith(PREFIX+"/") or parsed.query:
        raise ValueError("untrusted_raimo_destination")
    secret=os.environ.get("RAIMO_AUTH_GATEWAY_SECRET", "")
    if len(secret)<32:
        raise RuntimeError("RAIMO_AUTH_GATEWAY_SECRET is required for private ingestion")
    return {**(payload or {}), "__gateway_secret":secret}

def service_post(page, url, **kwargs):
    kwargs["data"]=service_payload(url,kwargs.get("data") or {})
    return page.request.post(url, **kwargs)

def service_get(page, url, **kwargs):
    data=service_payload(url)
    target=url.replace(PREFIX+"/", PREFIX+"/internal/read/",1)
    return page.request.post(target,data=data,**kwargs)
