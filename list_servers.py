# list_servers.py
import os
import sys
import json
import getpass
import asyncio

ROUTE_LOGICALS = "/vpn/v1/logicals"  # add query if needed, e.g. "?SecureCoreFilter=all"

def get_credentials():
    u = os.getenv("PROTON_USERNAME") or input("Proton username/email: ").strip()
    p = os.getenv("PROTON_PASSWORD") or getpass.getpass("Proton password: ")
    return u, p

def build_session():
    from proton.vpn.session import VPNSession
    return VPNSession()

def authenticate_once():
    u, p = get_credentials()
    s = build_session()
    s.authenticate(u, p)  # will raise if wrong
    if not getattr(s, "authenticated", False):
        print("Authentication did not complete (authenticated=False).", file=sys.stderr)
        sys.exit(5)
    return s

async def fetch_logicals(session):
    from proton.vpn.session.utils import rest_api_request
    raw = await rest_api_request(session, ROUTE_LOGICALS, return_raw=True)
    if getattr(raw, "status_code", None) != 200:
        body = getattr(raw, "text", "")[:200]
        raise RuntimeError(f"Server list failed: {raw.status_code} {body}")
    data = raw.json if isinstance(raw.json, dict) else raw.json()
    return data.get("LogicalServers", data)

def main():
    try:
        s = authenticate_once()
        logicals = asyncio.run(fetch_logicals(s))
        with open('/output/server_list.json', 'w') as f:
            json.dump(logicals, f, indent=2)
        print("Server list written to server_list.json")
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(6)

if __name__ == "__main__":
    main()
