# google_calendar_mcp_server.py
# Servidor MCP (por stdio) para Google Calendar / Gmail.

import sys, json, re, time, datetime as dt
from typing import Dict, Any, Optional
from urllib import request, parse, error

# === Carga de config con credenciales ===
import config

# === Soporte MCP mínimo (usa tu mcp_minimal.py) ===
try:
    import mcp_minimal
except ImportError:
    # mínima copia por si no está en el PYTHONPATH
    import sys as _sys, json as _json, re as _re
    from typing import Dict as _Dict, Any as _Any, Optional as _Optional, Callable as _Callable
    ENC = "utf-8"
    def _respond(obj: _Dict[str, _Any]) -> None:
        data = _json.dumps(obj).encode(ENC)
        header = ("Content-Length: {ln}\r\nContent-Type: application/json\r\n\r\n"
                  .format(ln=len(data))).encode(ENC)
        _sys.stdout.buffer.write(header)
        _sys.stdout.buffer.write(data)
        _sys.stdout.flush()
    def _read_request() -> _Optional[_Dict[str,_Any]]:
        headers = b""
        while b"\r\n\r\n" not in headers:
            ch = _sys.stdin.buffer.read(1)
            if not ch: return None
            headers += ch
        header_text = headers.decode(ENC, errors="ignore")
        m = _re.search(r"Content-Length:\s*(\d+)", header_text, _re.I)
        if not m: return None
        length = int(m.group(1))
        body = _sys.stdin.buffer.read(length)
        try:
            return _json.loads(body.decode(ENC, errors="ignore"))
        except Exception:
            return None
    def _serve(tools: _Dict[str, _Callable[..., _Any]],
               server_name: str = "mcp-minimal",
               version: str = "0.1.0") -> None:
        while True:
            req = _read_request()
            if not req:
                return
            method = req.get("method"); req_id = req.get("id")
            if method == "initialize":
                _respond({"jsonrpc":"2.0","id":req_id,"result":{
                    "protocolVersion":"2025-06-18",
                    "serverInfo": {"name": server_name, "version": version},
                    "capabilities":{"tools":{"listChanged": False}}
                }})
            elif method == "tools/list":
                _respond({"jsonrpc":"2.0","id":req_id,"result":{
                    "tools":[{"name":k,"description":(v.__doc__ or "")} for k,v in tools.items()]
                }})
            elif method == "tools/call":
                params = req.get("params",{}); name = params.get("name"); args = params.get("arguments") or {}
                if name not in tools:
                    _respond({"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":"Herramienta no encontrada: {}".format(name)}})
                else:
                    try:
                        out = tools[name](**args) if isinstance(args, dict) else tools[name]()
                        _respond({"jsonrpc":"2.0","id":req_id,"result":{"content": out}})
                    except Exception as e:
                        _respond({"jsonrpc":"2.0","id":req_id,"error":{"code":-32000,"message":str(e)}})
            else:
                _respond({"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":"Método desconocido: {}".format(method)}})
    # expone API similar
    class mcp_minimal:
        respond = _respond
        serve = staticmethod(_serve)

ENC = "utf-8"

# ============ HTTP helpers ============

def http_get(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    req = request.Request(url, headers=headers, method="GET")
    try:
        resp = request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode(ENC))
    except error.HTTPError as e:
        err = e.read().decode(ENC, errors="ignore")
        raise RuntimeError("HTTP {} {}: {}".format(e.code, e.reason, err))

def http_post(url: str, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    body = json.dumps(data).encode(ENC)
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        resp = request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode(ENC))
    except error.HTTPError as e:
        err = e.read().decode(ENC, errors="ignore")
        raise RuntimeError("HTTP {} {}: {}".format(e.code, e.reason, err))

# ============ OAuth2 ============

def google_access_token() -> str:
    """Intercambia refresh_token por access_token."""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "refresh_token": config.REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    body = parse.urlencode(data).encode("utf-8")
    req = request.Request(token_url, data=body, headers={"Content-Type":"application/x-www-form-urlencoded"}, method="POST")
    try:
        resp = request.urlopen(req, timeout=30)
        out = json.loads(resp.read().decode("utf-8"))
        return out["access_token"]
    except error.HTTPError as e:
        raise RuntimeError("OAuth refresh error: {}".format(e.read().decode("utf-8", "ignore")))

# ============ Parse de fechas/horas ============

def parse_when(when_text: str) -> dt.datetime:
    """
    Acepta:
      - "hoy HH:MM"
      - "mañana HH:MM" / "manana HH:MM"
      - "YYYY-MM-DD HH:MM"
    Devuelve datetime local (naive); se usará timeZone en el cuerpo del evento.
    """
    t = (when_text or "").strip()
    tl = t.lower()
    now = dt.datetime.now()
    # YYYY-MM-DD HH:MM
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})", t)
    if m:
        y, mo, d, hh, mm = map(int, m.groups())
        return dt.datetime(y, mo, d, hh, mm, 0)

    # hoy/mañana HH:MM
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        base = now.date()
        if "mañana" in tl or "manana" in tl:
            base = base + dt.timedelta(days=1)
        return dt.datetime.combine(base, dt.time(hh, mm, 0))

    # fallback: hoy 15:00
    return dt.datetime.combine(now.date(), dt.time(15, 0, 0))

def parse_day_ref(s: str) -> dt.date:
    """Convierte 'hoy'/'mañana'/'pasado mañana' o 'YYYY-MM-DD' a date (local)."""
    s = (s or "").strip().lower()
    today = dt.datetime.now().date()
    if s in ("hoy", ""):
        return today
    if s in ("mañana", "manana"):
        return today + dt.timedelta(days=1)
    if s in ("pasado mañana", "pasado manana"):
        return today + dt.timedelta(days=2)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = map(int, m.groups())
        return dt.date(y, mo, d)
    return today

# ============ Calendar / Gmail ops ============

def calendar_create_event(title: str, when: str, duration_minutes: int = 60, meet_link: bool=False) -> Dict[str, Any]:
    """Crea un evento en Calendar."""
    access = google_access_token()
    tz = getattr(config, "TIMEZONE", "America/Guatemala") or "America/Guatemala"

    start_dt = parse_when(when)
    end_dt = start_dt + dt.timedelta(minutes=int(duration_minutes or 60))

    payload = {
        "summary": title or "Evento",
        "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
        "end":   {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz},
    }

    query = ""
    if meet_link:
        payload["conferenceData"] = {"createRequest": {"requestId": "mcp-{}".format(int(time.time()))}}
        query = "?conferenceDataVersion=1"

    cal_id = getattr(config, "CALENDAR_ID", "primary") or "primary"
    url = ("https://www.googleapis.com/calendar/v3/calendars/{}/events{}"
           .format(parse.quote(cal_id), query))
    headers = {"Authorization": "Bearer {}".format(access), "Content-Type": "application/json"}

    out = http_post(url, payload, headers)
    return {"id": out.get("id"), "htmlLink": out.get("htmlLink"), "hangoutLink": out.get("hangoutLink")}


# --- Helpers de zona horaria para RFC3339 (UTC "Z") ---
def tz_offset_minutes_for(tz_name: str) -> int:
    known = {
        "America/Guatemala": -6*60,
        "America/Belize": -6*60,
        "America/Costa_Rica": -6*60,
        "America/El_Salvador": -6*60,
        "America/Tegucigalpa": -6*60,
    }
    if tz_name in known:
        return known[tz_name]
    import time as _time
    if _time.daylight and _time.localtime().tm_isdst:
        return int(-_time.altzone // 60)
    return int(-_time.timezone // 60)

def to_rfc3339_utc(dt_local: dt.datetime, tz_name: str) -> str:
    off_min = tz_offset_minutes_for(tz_name)
    dt_utc = dt_local - dt.timedelta(minutes=off_min)  # UTC = local - offset
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def calendar_list_day(when: str = "hoy") -> Dict[str, Any]:
    """Lista eventos de un día (usa timeMin/timeMax en UTC con 'Z')."""
    access = google_access_token()
    tz = getattr(config, "TIMEZONE", "America/Guatemala") or "America/Guatemala"
    target = parse_day_ref(when)

    start_dt_local = dt.datetime.combine(target, dt.time(0, 0, 0))
    end_dt_local   = dt.datetime.combine(target, dt.time(23, 59, 59))

    # RFC3339 en UTC (Z) — evita el 400
    tmin = to_rfc3339_utc(start_dt_local, tz)
    tmax = to_rfc3339_utc(end_dt_local,   tz)

    cal_id = getattr(config, "CALENDAR_ID", "primary") or "primary"
    url = ("https://www.googleapis.com/calendar/v3/calendars/"
           f"{parse.quote(cal_id)}/events?"
           f"timeMin={parse.quote(tmin)}&timeMax={parse.quote(tmax)}"
           f"&singleEvents=true&orderBy=startTime")
    out = http_get(url, headers={"Authorization": f"Bearer {access}"})

    events = []
    for it in out.get("items", []):
        start = it.get("start",{}).get("dateTime") or it.get("start",{}).get("date")
        end   = it.get("end",{}).get("dateTime") or it.get("end",{}).get("date")
        events.append({
            "summary": it.get("summary","(sin título)"),
            "start": start, "end": end,
            "hangoutLink": it.get("hangoutLink")
        })
    return {"events": events, "count": len(events), "day": str(target)}


def gmail_send_summary(text: str) -> Dict[str, Any]:
    """Envía un email con la agenda de hoy."""
    access = google_access_token()
    from_addr = getattr(config, "SENDER_EMAIL", "") or ""
    to_addr   = getattr(config, "USER_EMAIL", "") or from_addr
    subject   = "Resumen del día"
    # Mensaje simple RFC 822
    msg = "From: {}\r\nTo: {}\r\nSubject: {}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{}".format(
        from_addr, to_addr, subject, text
    ).encode("utf-8")

    # base64url
    import base64
    raw = base64.urlsafe_b64encode(msg).decode("utf-8").rstrip("=")

    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    headers = {"Authorization": "Bearer {}".format(access), "Content-Type": "application/json"}
    payload = {"raw": raw}
    out = http_post(url, payload, headers)
    return {"id": out.get("id", "")}

# ============ Herramientas MCP (callables) ============

def get_daily_agenda(when: Optional[str] = None) -> Dict[str, str]:
    """Devuelve la agenda de un día. Arg opcional: when = 'hoy'|'mañana'|'pasado mañana'|'YYYY-MM-DD'."""
    w = (when or "hoy").strip()
    agenda = calendar_list_day(w)
    if not agenda["count"]:
        return {"text": "Agenda de {}: no tienes eventos.".format(w)}
    lines = ["Agenda de {}:".format(w)]
    for ev in agenda["events"]:
        lines.append("- {} → {}: {}".format(ev["start"], ev["end"], ev["summary"]))
    return {"text": "\n".join(lines)}

def get_agenda(when: Optional[str] = None) -> Dict[str, str]:
    """Alias de get_daily_agenda."""
    return get_daily_agenda(when)

def create_calendar_event(title: Optional[str] = None,
                          when: Optional[str] = None,
                          duration_minutes: Optional[int] = None,
                          meet_link: Optional[bool] = None) -> Dict[str, str]:
    """Crea un evento. Args: title, when, duration_minutes, meet_link? (True/False)"""
    t = title or "Evento"
    w = when or "hoy 15:00"
    d = int(duration_minutes or 60)
    m = bool(meet_link)
    out = calendar_create_event(t, w, d, m)
    text = "¡Listo! Creé '{}'. Enlace: {}".format(t, out.get("htmlLink") or "(N/A)")
    if out.get("hangoutLink"):
        text += "\nMeet: {}".format(out["hangoutLink"])
    return {"text": text}

def send_daily_summary() -> Dict[str, str]:
    """Envía un correo con la agenda de hoy."""
    agenda = calendar_list_day("hoy")
    if not agenda["count"]:
        text = "Resumen: Hoy no hay eventos programados."
    else:
        lines = ["Resumen del día:"]
        for ev in agenda["events"]:
            lines.append("- {} → {}: {}".format(ev["start"], ev["end"], ev["summary"]))
        text = "\n".join(lines)
    status = gmail_send_summary(text)
    return {"text": "Enviado (id: {})".format(status.get("id",""))}

# ============ Entrypoint MCP ============

if __name__ == "__main__":
    tools = {
        "get_daily_agenda": get_daily_agenda,
        "get_agenda": get_agenda,
        "create_calendar_event": create_calendar_event,
        "send_daily_summary": send_daily_summary,
    }
    name = getattr(config, "SERVER_NAME", "google-calendar-mcp-thonny")
    ver  = getattr(config, "SERVER_VERSION", "0.2.0")
    mcp_minimal.serve(tools, server_name=name, version=ver)
