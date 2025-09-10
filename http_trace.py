# http_trace.py
import os
import sys
import json
import time
import types
import traceback
from datetime import datetime

REDACT_HEADERS = {
    "authorization",
    "cookie",
    "x-pm-session",
    "x-pm-uid",
    "x-pm-apitoken",
    "x-pm-appversion",
}
REDACT_KEYS = {
    "password",
    "pass",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "code_verifier",
    "code",
    "uid",
    "modulus",
    "salt",
    "totp",
}

HTTP_LOG = os.getenv("HTTP_LOG", "/logs/http.jsonl")
HTTP_TRACE = os.getenv("HTTP_TRACE", "0") == "1"
HTTP_CAPTURE_BODIES = os.getenv("HTTP_CAPTURE_BODIES", "json")  # none|json|all
HTTP_MAX_BODY = int(os.getenv("HTTP_MAX_BODY", "50000"))

def _ensure_dir(path: str):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass

def _open_log():
    _ensure_dir(HTTP_LOG)
    try:
        return open(HTTP_LOG, "a", encoding="utf-8")
    except Exception:
        return sys.stderr

_log_fp = None
def _log(entry: dict):
    global _log_fp
    if _log_fp is None:
        _log_fp = _open_log()
    try:
        _log_fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _log_fp.flush()
    except Exception:
        # last resort
        sys.stderr.write("[http-trace] failed to write log\n")

def _now_iso():
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

def _redact_headers(hdrs: dict):
    out = {}
    for k, v in hdrs.items():
        if k.lower() in REDACT_HEADERS:
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out

def _redact_json(obj):
    try:
        if isinstance(obj, dict):
            return {k: ("<redacted>" if k.lower() in REDACT_KEYS else _redact_json(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_redact_json(x) for x in obj]
        return obj
    except Exception:
        return obj

def _maybe_body_from_request(prep):
    # requests.PreparedRequest
    ct = None
    try:
        ct = prep.headers.get("Content-Type", "")
    except Exception:
        pass
    body = getattr(prep, "body", None)
    if body is None:
        return None, ct
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8", "replace")
        except Exception:
            pass
    if HTTP_CAPTURE_BODIES == "none":
        return None, ct
    if HTTP_CAPTURE_BODIES == "json" and ct and "json" not in ct.lower():
        return None, ct
    if isinstance(body, (str, bytes)) and len(body) > HTTP_MAX_BODY:
        return f"<truncated {len(body)} bytes>", ct
    # Try redact JSON
    if isinstance(body, str) and "json" in (ct or "").lower():
        try:
            parsed = json.loads(body)
            return json.dumps(_redact_json(parsed)), ct
        except Exception:
            pass
    return body, ct

def _maybe_body_from_response(resp):
    ct = resp.headers.get("Content-Type", "")
    if HTTP_CAPTURE_BODIES == "none":
        return None, ct
    if HTTP_CAPTURE_BODIES == "json" and "json" not in ct.lower():
        return None, ct
    text = None
    try:
        text = resp.text
    except Exception:
        return None, ct
    if text and len(text) > HTTP_MAX_BODY:
        return f"<truncated {len(text)} chars>", ct
    # try redact JSON
    if text and "json" in ct.lower():
        try:
            parsed = resp.json()
            return json.dumps(_redact_json(parsed)), ct
        except Exception:
            pass
    return text, ct

def _caller_hint():
    try:
        for f in reversed(traceback.extract_stack(limit=20)):
            # show first user frame under proton or app code
            if "/proton/" in (f.filename or "") or "/app/" in (f.filename or ""):
                return {"file": f.filename, "line": f.lineno, "func": f.name}
        return None
    except Exception:
        return None

def install_requests_trace():
    try:
        import requests
    except Exception:
        return

    if getattr(requests.Session.send, "__wrapped__", None):
        return  # already patched

    _orig_send = requests.Session.send

    def _wrapped_send(self, request, **kwargs):
        t0 = time.time()
        req_body, req_ct = _maybe_body_from_request(request)
        entry = {
            "ts": _now_iso(),
            "lib": "requests",
            "event": "http",
            "phase": "request",
            "method": request.method,
            "url": request.url,
            "headers": _redact_headers(request.headers),
            "content_type": req_ct,
            "body": req_body,
            "caller": _caller_hint(),
        }
        _log(entry)
        try:
            resp = _orig_send(self, request, **kwargs)
        except Exception as e:
            _log({
                "ts": _now_iso(),
                "lib": "requests",
                "event": "http",
                "phase": "error",
                "error": repr(e),
                "elapsed_ms": int((time.time() - t0) * 1000),
                "caller": _caller_hint(),
            })
            raise
        resp_body, resp_ct = _maybe_body_from_response(resp)
        _log({
            "ts": _now_iso(),
            "lib": "requests",
            "event": "http",
            "phase": "response",
            "status": resp.status_code,
            "url": request.url,
            "headers": _redact_headers(getattr(resp, "headers", {})),
            "content_type": resp_ct,
            "body": resp_body,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "caller": _caller_hint(),
        })
        return resp

    _wrapped_send.__wrapped__ = _orig_send
    requests.Session.send = _wrapped_send

def install_aiohttp_trace():
    try:
        import aiohttp
    except Exception:
        return
    cs = getattr(aiohttp, "ClientSession", None)
    if cs is None:
        return
    if getattr(cs._request, "__wrapped__", None):
        return

    _orig_req = cs._request

    async def _wrapped_request(self, method, url, **kwargs):
        t0 = time.time()
        headers = kwargs.get("headers", {}) or {}
        data = kwargs.get("data")
        json_body = kwargs.get("json")
        body = None
        ct = headers.get("Content-Type", "")
        if json_body is not None:
            try:
                body = json.dumps(_redact_json(json_body))
                ct = "application/json"
            except Exception:
                pass
        elif data is not None:
            body = str(data)
        if HTTP_CAPTURE_BODIES == "none" or (HTTP_CAPTURE_BODIES == "json" and ct and "json" not in ct.lower()):
            body = None

        _log({
            "ts": _now_iso(),
            "lib": "aiohttp",
            "event": "http",
            "phase": "request",
            "method": method,
            "url": str(url),
            "headers": _redact_headers(headers),
            "content_type": ct,
            "body": body if (body and len(body) <= HTTP_MAX_BODY) else (f"<truncated {len(body)}>" if body else None),
            "caller": _caller_hint(),
        })
        try:
            resp = await _orig_req(self, method, url, **kwargs)
        except Exception as e:
            _log({
                "ts": _now_iso(),
                "lib": "aiohttp",
                "event": "http",
                "phase": "error",
                "error": repr(e),
                "caller": _caller_hint(),
                "elapsed_ms": int((time.time() - t0) * 1000),
            })
            raise

        try:
            ct2 = resp.headers.get("Content-Type", "")
        except Exception:
            ct2 = ""
        body2 = None
        if HTTP_CAPTURE_BODIES != "none" and (HTTP_CAPTURE_BODIES == "all" or "json" in ct2.lower()):
            try:
                txt = await resp.text()
                if len(txt) > HTTP_MAX_BODY:
                    body2 = f"<truncated {len(txt)} chars>"
                else:
                    if "json" in ct2.lower():
                        try:
                            parsed = json.loads(txt)
                            txt = json.dumps(_redact_json(parsed))
                        except Exception:
                            pass
                    body2 = txt
            except Exception:
                body2 = None

        _log({
            "ts": _now_iso(),
            "lib": "aiohttp",
            "event": "http",
            "phase": "response",
            "status": resp.status,
            "url": str(url),
            "headers": _redact_headers(getattr(resp, "headers", {})),
            "content_type": ct2,
            "body": body2,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "caller": _caller_hint(),
        })
        return resp

    _wrapped_request.__wrapped__ = _orig_req
    cs._request = _wrapped_request

def install_logging_tweaks():
    # Optional: verbose urllib3 debug logs (headers only).
    import logging
    lvl = os.getenv("HTTP_DEBUG_LOGGING", "").upper()
    if lvl in ("1", "TRUE", "YES", "DEBUG"):
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("aiohttp.client").setLevel(logging.DEBUG)

def enable_tracing_if_requested():
    if not HTTP_TRACE:
        return
    try:
        install_requests_trace()
    except Exception:
        pass
    try:
        install_aiohttp_trace()
    except Exception:
        pass
    try:
        install_logging_tweaks()
    except Exception:
        pass
