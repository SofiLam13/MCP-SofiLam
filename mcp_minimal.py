# mcp_minimal.py
# Base mínima para construir servidores MCP por stdio (Python 3.7+).

import sys, json, re
from typing import Dict, Any, Optional, Callable

ENC = "utf-8"

def respond(obj: Dict[str, Any]) -> None:
    data = json.dumps(obj).encode(ENC)
    header = ("Content-Length: {ln}\r\nContent-Type: application/json\r\n\r\n"
              .format(ln=len(data))).encode(ENC)
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(data)
    sys.stdout.flush()

def read_request() -> Optional[Dict[str, Any]]:
    headers = b""
    while b"\r\n\r\n" not in headers:
        ch = sys.stdin.buffer.read(1)
        if not ch:
            return None
        headers += ch
    header_text = headers.decode(ENC, errors="ignore")
    m = re.search(r"Content-Length:\s*(\d+)", header_text, re.I)
    if not m:
        return None
    length = int(m.group(1))
    body = sys.stdin.buffer.read(length)
    try:
        return json.loads(body.decode(ENC, errors="ignore"))
    except Exception:
        return None

def serve(tools: Dict[str, Callable[..., Any]],
          server_name: str = "mcp-minimal",
          version: str = "0.1.0") -> None:
    while True:
        req = read_request()
        if not req:
            return
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            respond({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "serverInfo": {"name": server_name, "version": version},
                    "capabilities": {"tools": {"listChanged": False}}
                }
            })
        elif method == "tools/list":
            respond({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [{"name": k, "description": (v.__doc__ or "")}
                              for k, v in tools.items()]
                }
            })
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in tools:
                respond({"jsonrpc": "2.0", "id": req_id,
                         "error": {"code": -32601, "message": "Herramienta no encontrada: {}".format(name)}})
            else:
                try:
                    out = tools[name](**args) if isinstance(args, dict) else tools[name]()
                    respond({"jsonrpc": "2.0", "id": req_id, "result": {"content": out}})
                except Exception as e:
                    respond({"jsonrpc": "2.0", "id": req_id,
                             "error": {"code": -32000, "message": str(e)}})
        else:
            respond({"jsonrpc": "2.0", "id": req_id,
                     "error": {"code": -32601, "message": "Método desconocido: {}".format(method)}})

if __name__ == "__main__":
    def ping() -> Dict[str, str]:
        """Responde pong."""
        return {"text": "pong"}
    serve({"ping": ping})
