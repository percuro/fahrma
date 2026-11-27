"""The client's address as the app sees it (behind the reverse proxy: from X-Forwarded-For)."""

import ipaddress

from fastapi import Request


def client_ip(request: Request | None) -> str:
    return request.client.host if request is not None and request.client else "unknown"


def ip_prefix(address: str | None) -> str | None:
    """The network an address belongs to, never the address itself: IPv4 /24, IPv6 /48."""
    if not address:
        return None
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))
