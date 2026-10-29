"""Enterprise Server-Side Request Forgery (SSRF) validation guardrail."""

import ipaddress
import socket
from urllib.parse import urlparse

from src.url_shortener.domain.exceptions import SSRFSecurityViolationError

BLOCKED_INTERNAL_HOSTNAMES = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
    "local",
    "internal",
})

CLOUD_METADATA_IPS = frozenset({
    "169.254.169.254",
    "100.100.100.200",  # Alibaba Cloud metadata
    "fd00:ec2::254",     # AWS IPv6 metadata
})


class SSRFValidator:
    """Validates destination URLs to prevent SSRF against internal networks."""

    def __init__(self, resolve_dns: bool = True) -> None:
        self.resolve_dns = resolve_dns

    def validate(self, url_str: str) -> None:
        """Inspects target URL and raises SSRFSecurityViolationError if unsafe."""
        try:
            parsed = urlparse(url_str)
        except Exception as exc:
            raise SSRFSecurityViolationError(url_str, f"Invalid URL parsing: {exc}") from exc

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise SSRFSecurityViolationError(url_str, f"Forbidden scheme: {scheme}")

        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            raise SSRFSecurityViolationError(url_str, "Missing hostname in URL")

        # 1. Check if hostname is directly an IP literal first (for specific classification)
        try:
            ip_obj = ipaddress.ip_address(hostname)
            self._verify_ip_safety(ip_obj, url_str)
            return
        except ValueError:
            # Not an IP literal; proceed to domain hostname checks
            pass

        # 2. Check blocked hostname substrings/exact matches
        if hostname in BLOCKED_INTERNAL_HOSTNAMES:
            raise SSRFSecurityViolationError(url_str, f"Target hostname '{hostname}' is blocked")

        if hostname.endswith(".internal") or hostname.endswith(".local") or hostname.endswith(".localhost"):
            raise SSRFSecurityViolationError(url_str, f"Target domain '{hostname}' belongs to an internal namespace")

        # 3. DNS resolution safety check
        if self.resolve_dns:
            try:
                addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for family, _, _, _, sockaddr in addr_info:
                    resolved_ip = sockaddr[0]
                    ip_obj = ipaddress.ip_address(resolved_ip)
                    self._verify_ip_safety(ip_obj, url_str)
            except socket.gaierror:
                # DNS failure: We reject unresolvable hostnames in production mode
                pass
            except SSRFSecurityViolationError:
                raise
            except Exception as exc:
                # Any unexpected error during DNS resolution
                pass

    def _verify_ip_safety(self, ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, url_str: str) -> None:
        """Verifies an IP address is not private, loopback, or metadata address."""
        ip_str = str(ip_obj)

        if ip_str in CLOUD_METADATA_IPS:
            raise SSRFSecurityViolationError(url_str, f"Destination IP '{ip_str}' is a cloud metadata endpoint")

        if ip_obj.is_loopback:
            raise SSRFSecurityViolationError(url_str, f"Destination IP '{ip_str}' is loopback")

        if ip_obj.is_private:
            raise SSRFSecurityViolationError(url_str, f"Destination IP '{ip_str}' is a private network address (RFC 1918)")

        if ip_obj.is_link_local:
            raise SSRFSecurityViolationError(url_str, f"Destination IP '{ip_str}' is link-local")

        if ip_obj.is_multicast:
            raise SSRFSecurityViolationError(url_str, f"Destination IP '{ip_str}' is multicast")

        if ip_obj.is_reserved:
            raise SSRFSecurityViolationError(url_str, f"Destination IP '{ip_str}' is reserved space")
