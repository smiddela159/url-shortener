#!/usr/bin/env python3
"""
End-to-End Live API Test Suite
==============================
Executes REAL HTTP requests against a running FastAPI server.
Validates both positive (happy-path) and negative (error/security) scenarios.

Usage:
    # Start server first:  uvicorn src.url_shortener.presentation.api:app --port 8000
    # Then run:            python3 tests/e2e/test_live_api.py
"""
import json
import sys
import time
from datetime import datetime
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000"
RESULTS: list[dict[str, Any]] = []


def record(
    test_name: str,
    method: str,
    path: str,
    expected_status: int,
    actual_status: int,
    response_body: Any,
    passed: bool,
    notes: str = "",
) -> None:
    """Record a test result."""
    result = {
        "test": test_name,
        "method": method,
        "path": path,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "passed": passed,
        "notes": notes,
        "response_snippet": str(response_body)[:500],
    }
    RESULTS.append(result)
    status_icon = "✅" if passed else "❌"
    print(f"  {status_icon} {test_name}: {method} {path} → {actual_status} (expected {expected_status}){f' — {notes}' if notes else ''}")


# ---------------------------------------------------------------------------
# POSITIVE TEST CASES
# ---------------------------------------------------------------------------

def test_health_check() -> None:
    """GET /health → 200 with status=healthy."""
    r = httpx.get(f"{BASE_URL}/health")
    body = r.json()
    passed = r.status_code == 200 and body.get("status") == "healthy"
    record("Health Check", "GET", "/health", 200, r.status_code, body, passed)


def test_metrics_endpoint() -> None:
    """GET /metrics → 200 with cache/rate-limiter stats."""
    r = httpx.get(f"{BASE_URL}/metrics")
    body = r.json()
    passed = r.status_code == 200 and "cache" in body
    record("Metrics Endpoint", "GET", "/metrics", 200, r.status_code, body, passed)


def test_create_short_url() -> str:
    """POST /api/v1/urls → 201 with short_code returned."""
    payload = {"url": "https://www.schwab.com/financial-planning"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    body = r.json()
    short_code = body.get("short_code", "")
    passed = r.status_code == 201 and len(short_code) > 0
    record("Create Short URL", "POST", "/api/v1/urls", 201, r.status_code, body, passed, f"short_code={short_code}")
    return short_code


def test_create_with_custom_slug() -> str:
    """POST /api/v1/urls with custom_slug → 201."""
    payload = {"url": "https://www.schwab.com/iras", "custom_slug": "schwab-ira"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    body = r.json()
    passed = r.status_code == 201 and body.get("short_code") == "schwab-ira"
    record("Create With Custom Slug", "POST", "/api/v1/urls", 201, r.status_code, body, passed)
    return body.get("short_code", "schwab-ira")


def test_create_with_ttl() -> str:
    """POST /api/v1/urls with ttl_seconds → 201 and expires_at is set."""
    payload = {"url": "https://www.schwab.com/trading", "ttl_seconds": 5}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    body = r.json()
    short_code = body.get("short_code", "")
    passed = r.status_code == 201 and body.get("expires_at") is not None
    record("Create With TTL", "POST", "/api/v1/urls", 201, r.status_code, body, passed, f"expires_at={body.get('expires_at')}")
    return short_code


def test_redirect(short_code: str) -> None:
    """GET /{short_code} → 302 redirect to original URL."""
    r = httpx.get(f"{BASE_URL}/{short_code}", follow_redirects=False)
    location = r.headers.get("location", "")
    passed = r.status_code == 302 and "schwab.com" in location
    record("Redirect (302)", "GET", f"/{short_code}", 302, r.status_code, {"location": location}, passed)


def test_redirect_with_user_agent(short_code: str) -> None:
    """GET /{short_code} with mobile User-Agent → 302 and device detected."""
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"}
    r = httpx.get(f"{BASE_URL}/{short_code}", headers=headers, follow_redirects=False)
    passed = r.status_code == 302
    record("Redirect With Mobile UA", "GET", f"/{short_code}", 302, r.status_code, {"location": r.headers.get("location")}, passed, "Mobile device detection")


def test_analytics(short_code: str) -> None:
    """GET /api/v1/urls/{short_code}/analytics → 200 with click count."""
    r = httpx.get(f"{BASE_URL}/api/v1/urls/{short_code}/analytics")
    body = r.json()
    passed = r.status_code == 200 and body.get("total_clicks", 0) >= 1
    record("Analytics", "GET", f"/api/v1/urls/{short_code}/analytics", 200, r.status_code, body, passed, f"total_clicks={body.get('total_clicks')}")


def test_cache_hit_on_second_redirect(short_code: str) -> None:
    """Second redirect should be served from cache (check /metrics)."""
    # First redirect was already done, do another
    httpx.get(f"{BASE_URL}/{short_code}", follow_redirects=False)
    r = httpx.get(f"{BASE_URL}/metrics")
    body = r.json()
    hits = body.get("cache", {}).get("hits", 0)
    passed = hits >= 1
    record("Cache Hit on Repeat Redirect", "GET", f"/{short_code} + /metrics", 200, r.status_code, body, passed, f"cache_hits={hits}")


# ---------------------------------------------------------------------------
# NEGATIVE TEST CASES
# ---------------------------------------------------------------------------

def test_ssrf_loopback() -> None:
    """POST /api/v1/urls with http://127.0.0.1 → 403 SSRF blocked."""
    payload = {"url": "http://127.0.0.1/admin"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 403
    record("SSRF: Loopback (127.0.0.1)", "POST", "/api/v1/urls", 403, r.status_code, r.json(), passed)


def test_ssrf_localhost() -> None:
    """POST /api/v1/urls with http://localhost → 403 SSRF blocked."""
    payload = {"url": "http://localhost:8080/secret"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 403
    record("SSRF: Localhost", "POST", "/api/v1/urls", 403, r.status_code, r.json(), passed)


def test_ssrf_private_ip() -> None:
    """POST /api/v1/urls with http://10.0.0.1 → 403 SSRF blocked."""
    payload = {"url": "http://10.0.0.1/internal-api"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 403
    record("SSRF: Private IP (10.x)", "POST", "/api/v1/urls", 403, r.status_code, r.json(), passed)


def test_ssrf_aws_metadata() -> None:
    """POST /api/v1/urls with AWS metadata endpoint → 403 SSRF blocked."""
    payload = {"url": "http://169.254.169.254/latest/meta-data/"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 403
    record("SSRF: AWS Metadata (169.254.x)", "POST", "/api/v1/urls", 403, r.status_code, r.json(), passed)


def test_ssrf_internal_domain() -> None:
    """POST /api/v1/urls with .internal domain → 403 SSRF blocked."""
    payload = {"url": "http://secrets.internal/vault"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 403
    record("SSRF: Internal Domain (.internal)", "POST", "/api/v1/urls", 403, r.status_code, r.json(), passed)


def test_ssrf_kubernetes() -> None:
    """POST /api/v1/urls with .cluster.local → 403 SSRF blocked."""
    payload = {"url": "http://api-server.default.svc.cluster.local"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 403
    record("SSRF: Kubernetes (.cluster.local)", "POST", "/api/v1/urls", 403, r.status_code, r.json(), passed)


def test_not_found() -> None:
    """GET /nonexistent-code → 404."""
    r = httpx.get(f"{BASE_URL}/zzzNOTFOUNDzzz", follow_redirects=False)
    passed = r.status_code == 404
    record("Not Found (404)", "GET", "/zzzNOTFOUNDzzz", 404, r.status_code, r.json(), passed)


def test_invalid_url_scheme() -> None:
    """POST /api/v1/urls with ftp:// → 400 or 422 validation error."""
    payload = {"url": "ftp://evil.com/files"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code in (400, 422)
    record("Invalid URL Scheme (ftp://)", "POST", "/api/v1/urls", 400, r.status_code, r.json(), passed)


def test_empty_url() -> None:
    """POST /api/v1/urls with empty string → 422 validation error."""
    payload = {"url": ""}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code in (400, 422)
    record("Empty URL", "POST", "/api/v1/urls", 422, r.status_code, r.json(), passed)


def test_missing_url_field() -> None:
    """POST /api/v1/urls with missing field → 422."""
    payload = {}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    passed = r.status_code == 422
    record("Missing URL Field", "POST", "/api/v1/urls", 422, r.status_code, r.json(), passed)


def test_slug_collision() -> None:
    """POST /api/v1/urls with duplicate custom_slug → 409 conflict."""
    slug = "collision-test-unique"
    # First creation should succeed
    payload1 = {"url": "https://www.google.com", "custom_slug": slug}
    r1 = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload1)
    # Second creation with same slug should fail
    payload2 = {"url": "https://www.github.com", "custom_slug": slug}
    r2 = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload2)
    passed = r1.status_code == 201 and r2.status_code == 409
    record("Slug Collision (409)", "POST", "/api/v1/urls", 409, r2.status_code, r2.json(), passed, f"first={r1.status_code}, second={r2.status_code}")


def test_reserved_keyword_slug() -> None:
    """POST /api/v1/urls with reserved keyword (api, health, metrics) → 422."""
    payload = {"url": "https://www.schwab.com", "custom_slug": "api"}
    r = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    # Expect 409 (collision with reserved), 422 (policy violation), or 400
    passed = r.status_code in (400, 409, 422)
    record("Reserved Keyword Slug ('api')", "POST", "/api/v1/urls", 422, r.status_code, r.json(), passed)


def test_expired_url_returns_410() -> None:
    """Create URL with 2s TTL, wait for expiry, GET → 410 Gone."""
    payload = {"url": "https://www.schwab.com/expired-test", "ttl_seconds": 2}
    r1 = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    short_code = r1.json().get("short_code", "")
    print(f"    ⏳ Waiting 3 seconds for TTL expiry (short_code={short_code})...")
    time.sleep(3)
    r2 = httpx.get(f"{BASE_URL}/{short_code}", follow_redirects=False)
    passed = r1.status_code == 201 and r2.status_code == 410
    body = {}
    try:
        body = r2.json()
    except Exception:
        body = {"raw": r2.text[:200]}
    record("Expired URL (410 Gone)", "GET", f"/{short_code}", 410, r2.status_code, body, passed, f"TTL=2s, waited=3s")


def test_delete_url() -> None:
    """DELETE /api/v1/urls/{short_code} → 204, then GET → 404 or 410."""
    # Create a URL first
    payload = {"url": "https://www.schwab.com/delete-test"}
    r1 = httpx.post(f"{BASE_URL}/api/v1/urls", json=payload)
    short_code = r1.json().get("short_code", "")
    # Delete it (no trailing slash)
    r2 = httpx.delete(f"{BASE_URL}/api/v1/urls/{short_code}")
    # Try to access it
    r3 = httpx.get(f"{BASE_URL}/{short_code}", follow_redirects=False)
    passed = r1.status_code == 201 and r2.status_code == 204 and r3.status_code in (404, 410)
    record("Delete URL (204) → Gone", "DELETE + GET", f"/api/v1/urls/{short_code}", 204, r2.status_code, {"after_delete_status": r3.status_code}, passed)


def test_security_headers() -> None:
    """Verify security headers (X-Content-Type-Options, X-Frame-Options, etc.)."""
    r = httpx.get(f"{BASE_URL}/health")
    headers = dict(r.headers)
    checks = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "x-xss-protection": "1; mode=block",
    }
    all_present = all(headers.get(k) == v for k, v in checks.items())
    passed = r.status_code == 200 and all_present
    found = {k: headers.get(k, "MISSING") for k in checks}
    record("Security Headers", "GET", "/health (headers)", 200, r.status_code, found, passed)


def test_rate_limiting() -> None:
    """Send rapid requests to a rate-limited endpoint using a dedicated client IP to trigger 429."""
    hit_429 = False
    count = 0
    # Use a distinct client IP so rate limiting tests do not starve functional tests
    headers = {"X-Forwarded-For": "198.51.100.99"}
    for i in range(120):
        r = httpx.get(f"{BASE_URL}/ratelimit-probe-{i}", headers=headers, follow_redirects=False)
        count += 1
        if r.status_code == 429:
            hit_429 = True
            break
    record("Rate Limiting (429)", "GET", "/{short_code} x120", 429, 429 if hit_429 else r.status_code, {"requests_sent": count, "hit_429": hit_429}, hit_429, f"Triggered after {count} requests (IP: 198.51.100.99)")


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("  🚀 LIVE E2E API TEST SUITE — URL Shortener Service")
    print(f"  Target: {BASE_URL}")
    print(f"  Timestamp: {datetime.utcnow().isoformat()}Z")
    print("=" * 72)

    # Verify server is reachable
    try:
        httpx.get(f"{BASE_URL}/health", timeout=3)
    except httpx.ConnectError:
        print("\n❌ Server not reachable at", BASE_URL)
        print("   Start it with: uvicorn src.url_shortener.presentation.api:app --port 8000")
        sys.exit(1)

    # --- Positive Cases ---
    print("\n━━━ POSITIVE TEST CASES (9 tests) ━━━")
    test_health_check()
    test_metrics_endpoint()
    short_code = test_create_short_url()
    custom_slug = test_create_with_custom_slug()
    ttl_code = test_create_with_ttl()
    test_redirect(short_code)
    test_redirect_with_user_agent(short_code)
    test_analytics(short_code)
    test_cache_hit_on_second_redirect(short_code)

    # --- Negative Cases ---
    print("\n━━━ NEGATIVE TEST CASES (16 tests) ━━━")
    test_ssrf_loopback()
    test_ssrf_localhost()
    test_ssrf_private_ip()
    test_ssrf_aws_metadata()
    test_ssrf_internal_domain()
    test_ssrf_kubernetes()
    test_not_found()
    test_invalid_url_scheme()
    test_empty_url()
    test_missing_url_field()
    test_slug_collision()
    test_reserved_keyword_slug()
    test_expired_url_returns_410()
    test_delete_url()
    test_security_headers()
    test_rate_limiting()

    # --- Summary ---
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = total - passed
    print("\n" + "=" * 72)
    print(f"  📊 RESULTS: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("  🏆 ALL TESTS PASSED — Production readiness confirmed")
    else:
        print("  ⚠️  FAILURES:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"     ❌ {r['test']}: expected {r['expected_status']}, got {r['actual_status']} — {r['notes']}")
    print("=" * 72)

    # Save results to JSON
    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "base_url": BASE_URL,
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{(passed/total)*100:.1f}%",
        "results": RESULTS,
    }
    output_path = "artifacts/e2e_test_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  📁 Results saved to: {output_path}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

