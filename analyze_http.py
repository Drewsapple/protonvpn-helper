# analyze_http.py
import json
from collections import deque, defaultdict
from urllib.parse import urlparse

path = "logs/http.jsonl"  # adjust if needed

def norm_url(u):
    # collapse query param order for grouping
    pu = urlparse(u)
    return f"{pu.scheme}://{pu.netloc}{pu.path}"

reqs = deque()
pairs = []
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("event") != "http":
            continue
        if ev.get("phase") == "request":
            reqs.append(ev)
        elif ev.get("phase") == "response":
            # pair with the last request (best-effort)
            if reqs:
                r = reqs.popleft()
                if norm_url(r["url"]) != norm_url(ev.get("url", r["url"])):
                    # URL mismatch; keep pairing but annotate
                    pass
                pairs.append((r, ev))

# Summarize
print("== Sequence of calls ==")
for i, (req, resp) in enumerate(pairs, 1):
    u = req["url"]
    n = norm_url(u)
    print(f"{i:02d}. {req.get('lib','?')} {req['method']} {n} -> {resp.get('status')}")
    # If likely serverlist or loads, hint it
    if "/vpn/v1/logicals" in n:
        print("    NOTE: logicals (server list)")
    if "/vpn/v1/loads" in n:
        print("    NOTE: loads (live loads)")

print("\n== Group by endpoint (status counts) ==")
agg = defaultdict(lambda: defaultdict(int))
for req, resp in pairs:
    n = norm_url(req["url"])
    agg[n][resp.get("status")] += 1
for n, counts in agg.items():
    print(n, dict(counts))
