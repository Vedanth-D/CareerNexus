import logging
import json
import sys
from datetime import datetime, timezone

# Configure dedicated Security Logger
security_logger = logging.getLogger("security_audit")
security_logger.setLevel(logging.INFO)

# Avoid duplicate handlers
if not security_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [SECURITY] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%SZ'
    )
    handler.setFormatter(formatter)
    security_logger.addHandler(handler)

def _format_event(event_type: str, client_ip: str, user_id: str = None, email: str = "", detail: str = "", status: str = "INFO") -> str:
    log_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "client_ip": client_ip,
        "user_id": user_id,
        "email": email,
        "detail": detail,
        "status": status
    }
    return json.dumps(log_payload)

def log_auth_event(event_type: str, client_ip: str, email: str = "", success: bool = True, detail: str = ""):
    status = "SUCCESS" if success else "FAILED"
    msg = _format_event(event_type, client_ip=client_ip, email=email, detail=detail, status=status)
    if success:
        security_logger.info(msg)
    else:
        security_logger.warning(msg)

def log_security_event(event_type: str, client_ip: str, user_id: int = None, detail: str = ""):
    msg = _format_event(event_type, client_ip=client_ip, user_id=str(user_id) if user_id else None, detail=detail, status="ALERT")
    security_logger.warning(msg)

def log_api_error(endpoint: str, client_ip: str, status_code: int, error_msg: str, user_id: int = None):
    detail = f"Endpoint: {endpoint} | Status: {status_code} | Error: {error_msg}"
    msg = _format_event("API_ERROR", client_ip=client_ip, user_id=str(user_id) if user_id else None, detail=detail, status="ERROR")
    security_logger.error(msg)
