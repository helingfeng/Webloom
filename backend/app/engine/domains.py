"""全局变量域名规范化：忽略端口，支持粘贴完整 HTTP URL。"""

import ipaddress
import re
from urllib.parse import urlparse


def normalize_domain(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if not value:
        return ""
    try:
        return str(ipaddress.ip_address(value.strip("[]")))
    except ValueError:
        pass
    if value.startswith("*."):
        value = value[2:]
    value = value.lstrip(".")
    parsed = urlparse(value if "://" in value else "//" + value)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError("域名仅接受主机名或 http/https 地址")
    host = (parsed.hostname or "").rstrip(".")
    if not host:
        raise ValueError("域名格式不合法")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("域名格式不合法") from exc
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if len(host) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
        for part in host.split(".")
    ):
        raise ValueError("域名格式不合法，请填写 example.com 或完整 http/https 地址")
    return host
