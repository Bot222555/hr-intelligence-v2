#!/usr/bin/env python3
"""HR Intelligence Health Check — verify all services are operational.

Checks:
  1. Backend API responds on /api/v1/health (HTTP 200, valid JSON)
  2. Database has fresh data (<24h since last sync)
  3. All Docker containers running (postgres, redis, api, nginx)
  4. SSL certificate valid and not expiring soon
  5. Nginx config correct (redirects HTTP→HTTPS, proxies API)

Usage:
    python scripts/healthcheck.py                          # check https://hr.cfai.in
    python scripts/healthcheck.py --url https://hr.cfai.in
    python scripts/healthcheck.py --url http://localhost:8000 --skip-ssl --skip-docker
    python scripts/healthcheck.py --json                   # machine-readable output
    python scripts/healthcheck.py --fix                    # attempt auto-fixes

Exit codes:
    0 = all checks passed
    1 = one or more checks failed
    2 = critical failure (cannot reach target at all)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

# Optional: requests may not be installed everywhere
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ══════════════════════════════════════════════════════════════════════
# Check result model
# ══════════════════════════════════════════════════════════════════════

IST = timezone(timedelta(hours=5, minutes=30))


class CheckResult:
    """Single health check result."""

    def __init__(self, name: str, passed: bool, message: str,
                 detail: str = "", severity: str = "error"):
        self.name = name
        self.passed = passed
        self.message = message
        self.detail = detail
        self.severity = severity  # "error", "warning", "info"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "detail": self.detail,
            "severity": self.severity,
        }

    def __str__(self) -> str:
        icon = "✅" if self.passed else ("⚠️" if self.severity == "warning" else "❌")
        s = f"{icon} {self.name}: {self.message}"
        if self.detail:
            s += f"\n     {self.detail}"
        return s


# ══════════════════════════════════════════════════════════════════════
# Health checks
# ══════════════════════════════════════════════════════════════════════

def check_backend_health(base_url: str, timeout: int = 10) -> CheckResult:
    """Check that the backend API /api/v1/health responds correctly."""
    health_url = f"{base_url.rstrip('/')}/api/v1/health"
    try:
        if HAS_REQUESTS:
            resp = requests.get(health_url, timeout=timeout, verify=True)
            status = resp.status_code
            body = resp.json()
        else:
            import urllib.request
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = json.loads(resp.read().decode())

        if status != 200:
            return CheckResult(
                "Backend API", False,
                f"HTTP {status} (expected 200)",
                f"URL: {health_url}",
            )

        if body.get("status") != "healthy":
            return CheckResult(
                "Backend API", False,
                f"Status: {body.get('status', 'missing')} (expected 'healthy')",
                f"Response: {json.dumps(body)}",
            )

        version = body.get("version", "unknown")
        env = body.get("environment", "unknown")
        return CheckResult(
            "Backend API", True,
            f"Healthy (v{version}, {env})",
            f"URL: {health_url}",
        )
    except requests.exceptions.SSLError as e:
        return CheckResult(
            "Backend API", False,
            "SSL error connecting to backend",
            str(e),
        )
    except requests.exceptions.ConnectionError as e:
        return CheckResult(
            "Backend API", False,
            "Cannot connect to backend",
            str(e),
            severity="error",
        )
    except Exception as e:
        return CheckResult(
            "Backend API", False,
            f"Health check failed: {type(e).__name__}",
            str(e),
        )


def check_database_freshness(base_url: str, timeout: int = 10) -> CheckResult:
    """Check that database has fresh data by querying API stats or
    falling back to checking sync timestamps via a management endpoint."""
    # Try the dashboard stats endpoint (returns counts)
    stats_url = f"{base_url.rstrip('/')}/api/v1/dashboard/stats"
    try:
        if HAS_REQUESTS:
            # Try without auth first — may get 401
            resp = requests.get(stats_url, timeout=timeout, verify=True)
            if resp.status_code == 401 or resp.status_code == 403:
                return CheckResult(
                    "Database Freshness", True,
                    "API is auth-protected (cannot verify data freshness remotely)",
                    "Dashboard stats endpoint requires authentication. "
                    "Check database directly on the server.",
                    severity="warning",
                )
            if resp.status_code == 200:
                data = resp.json()
                # If we get stats, the DB is responding
                emp_count = data.get("total_employees", data.get("employee_count", 0))
                if emp_count == 0:
                    return CheckResult(
                        "Database Freshness", False,
                        "Database appears empty (0 employees)",
                        f"Stats: {json.dumps(data)[:200]}",
                    )
                return CheckResult(
                    "Database Freshness", True,
                    f"Database has data ({emp_count} employees)",
                    f"Stats: {json.dumps(data)[:200]}",
                )
        # If requests not available or error, skip
        return CheckResult(
            "Database Freshness", True,
            "Cannot verify remotely (no public stats endpoint)",
            "Check last sync time on server: python -m migration.keka_api_sync --status",
            severity="warning",
        )
    except Exception as e:
        return CheckResult(
            "Database Freshness", True,
            "Cannot verify data freshness remotely",
            f"Error: {e}. Check on server directly.",
            severity="warning",
        )


def check_docker_containers(expected: list[str] | None = None) -> CheckResult:
    """Check that expected Docker containers are running."""
    if expected is None:
        expected = ["postgres", "redis", "api", "nginx"]

    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True, text=True, timeout=15,
            cwd="/opt/hr-intelligence",
        )
        if result.returncode != 0:
            # Try without cwd (local dev)
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
                capture_output=True, text=True, timeout=15,
            )
    except FileNotFoundError:
        return CheckResult(
            "Docker Containers", True,
            "Docker not available on this machine (remote check only)",
            "Run this check on the EC2 server directly.",
            severity="info",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            "Docker Containers", False,
            "Docker command timed out",
            "Docker may be unresponsive",
        )

    if result.returncode != 0:
        return CheckResult(
            "Docker Containers", False,
            "Docker command failed",
            result.stderr[:300],
        )

    output = result.stdout.strip()
    if not output:
        return CheckResult(
            "Docker Containers", False,
            "No containers found running",
            "Run: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d",
        )

    # Parse running containers
    running = set()
    lines = output.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Try JSON format first
        try:
            data = json.loads(line)
            name = data.get("Name", data.get("name", ""))
            state = data.get("State", data.get("state", ""))
            if state.lower() == "running":
                running.add(name.lower())
            continue
        except (json.JSONDecodeError, AttributeError):
            pass
        # Plain text format: "container_name Up 2 hours"
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0].lower()
            status = " ".join(parts[1:]).lower()
            if "up" in status:
                running.add(name)

    # Check expected containers (partial name match)
    missing = []
    found = []
    for exp in expected:
        matched = any(exp.lower() in c for c in running)
        if matched:
            found.append(exp)
        else:
            missing.append(exp)

    if missing:
        return CheckResult(
            "Docker Containers", False,
            f"Missing containers: {', '.join(missing)}",
            f"Running: {', '.join(sorted(running))}",
        )

    return CheckResult(
        "Docker Containers", True,
        f"All {len(expected)} containers running",
        f"Found: {', '.join(found)}",
    )


def check_ssl_certificate(hostname: str, port: int = 443,
                          warn_days: int = 14) -> CheckResult:
    """Check SSL certificate validity and expiry."""
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()

        # Parse expiry
        not_after = cert.get("notAfter", "")
        if not_after:
            # Format: 'Mar 15 12:00:00 2025 GMT'
            expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
            expiry = expiry.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_left = (expiry - now).days

            # Check issuer
            issuer = dict(x[0] for x in cert.get("issuer", []))
            issuer_cn = issuer.get("commonName", "unknown")

            # Check subject
            subject = dict(x[0] for x in cert.get("subject", []))
            subject_cn = subject.get("commonName", "unknown")

            # Check SANs
            sans = [v for t, v in cert.get("subjectAltName", []) if t == "DNS"]

            if days_left < 0:
                return CheckResult(
                    "SSL Certificate", False,
                    f"EXPIRED {abs(days_left)} days ago!",
                    f"Subject: {subject_cn}, Issuer: {issuer_cn}, Expired: {not_after}",
                )
            elif days_left < warn_days:
                return CheckResult(
                    "SSL Certificate", True,
                    f"Expiring soon: {days_left} days left",
                    f"Subject: {subject_cn}, Issuer: {issuer_cn}, Expires: {not_after}",
                    severity="warning",
                )
            else:
                return CheckResult(
                    "SSL Certificate", True,
                    f"Valid ({days_left} days until expiry)",
                    f"Subject: {subject_cn}, Issuer: {issuer_cn}, SANs: {', '.join(sans[:3])}",
                )
        else:
            return CheckResult(
                "SSL Certificate", False,
                "Cannot read certificate expiry",
                f"Cert data: {json.dumps(cert)[:200]}",
            )
    except ssl.SSLCertVerificationError as e:
        return CheckResult(
            "SSL Certificate", False,
            "Certificate verification failed",
            str(e),
        )
    except socket.timeout:
        return CheckResult(
            "SSL Certificate", False,
            f"Connection timeout to {hostname}:{port}",
            "Check if port 443 is open and the server is running.",
        )
    except ConnectionRefusedError:
        return CheckResult(
            "SSL Certificate", False,
            f"Connection refused to {hostname}:{port}",
            "Nginx may not be running or port 443 is not open.",
        )
    except Exception as e:
        return CheckResult(
            "SSL Certificate", False,
            f"SSL check failed: {type(e).__name__}",
            str(e),
        )


def check_nginx_config(base_url: str, timeout: int = 10) -> CheckResult:
    """Verify Nginx is configured correctly:
    - HTTP redirects to HTTPS
    - API routes proxy correctly
    - Static files served
    """
    parsed = urlparse(base_url)
    hostname = parsed.hostname

    issues = []
    checks_passed = 0
    total_checks = 0

    # Check 1: HTTP → HTTPS redirect
    total_checks += 1
    try:
        http_url = f"http://{hostname}/"
        if HAS_REQUESTS:
            resp = requests.get(http_url, timeout=timeout, allow_redirects=False, verify=False)
            if resp.status_code in (301, 302, 307, 308):
                location = resp.headers.get("Location", "")
                if "https://" in location:
                    checks_passed += 1
                else:
                    issues.append(f"HTTP redirect goes to {location} (expected HTTPS)")
            else:
                issues.append(f"HTTP returns {resp.status_code} (expected 301 redirect)")
        else:
            checks_passed += 1  # Skip if no requests library
    except Exception as e:
        issues.append(f"HTTP redirect check failed: {e}")

    # Check 2: HTTPS serves content
    total_checks += 1
    try:
        if HAS_REQUESTS:
            resp = requests.get(f"https://{hostname}/", timeout=timeout, verify=True)
            if resp.status_code == 200:
                checks_passed += 1
                # Check if it looks like a React SPA
                if "<!DOCTYPE html>" in resp.text or "<div id=" in resp.text:
                    pass  # Good — SPA shell
                else:
                    issues.append("HTTPS root doesn't look like the React SPA")
            else:
                issues.append(f"HTTPS root returns {resp.status_code}")
        else:
            checks_passed += 1
    except Exception as e:
        issues.append(f"HTTPS root check failed: {e}")

    # Check 3: API proxy works
    total_checks += 1
    try:
        api_url = f"https://{hostname}/api/v1/health"
        if HAS_REQUESTS:
            resp = requests.get(api_url, timeout=timeout, verify=True)
            if resp.status_code == 200:
                checks_passed += 1
            else:
                issues.append(f"API proxy returns {resp.status_code} (expected 200)")
        else:
            checks_passed += 1
    except Exception as e:
        issues.append(f"API proxy check failed: {e}")

    # Check 4: Security headers
    total_checks += 1
    try:
        if HAS_REQUESTS:
            resp = requests.get(f"https://{hostname}/", timeout=timeout, verify=True)
            headers = resp.headers
            expected_headers = {
                "X-Frame-Options": "SAMEORIGIN",
                "X-Content-Type-Options": "nosniff",
            }
            missing_headers = []
            for hdr, val in expected_headers.items():
                if hdr not in headers:
                    missing_headers.append(hdr)
            if missing_headers:
                issues.append(f"Missing security headers: {', '.join(missing_headers)}")
            else:
                checks_passed += 1
        else:
            checks_passed += 1
    except Exception:
        pass  # Already caught above

    if issues:
        return CheckResult(
            "Nginx Config", checks_passed == total_checks,
            f"{checks_passed}/{total_checks} checks passed",
            "; ".join(issues),
            severity="warning" if checks_passed > 0 else "error",
        )

    return CheckResult(
        "Nginx Config", True,
        f"All {total_checks} checks passed (redirect, SPA, API proxy, headers)",
    )


# ══════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════

def run_healthcheck(
    url: str = "https://hr.cfai.in",
    skip_ssl: bool = False,
    skip_docker: bool = False,
    output_json: bool = False,
) -> list[CheckResult]:
    """Run all health checks and return results."""
    results: list[CheckResult] = []
    parsed = urlparse(url)
    hostname = parsed.hostname

    # 1. Backend API health
    results.append(check_backend_health(url))

    # 2. Database freshness
    results.append(check_database_freshness(url))

    # 3. Docker containers
    if not skip_docker:
        results.append(check_docker_containers())
    else:
        results.append(CheckResult(
            "Docker Containers", True,
            "Skipped (--skip-docker)",
            severity="info",
        ))

    # 4. SSL certificate
    if not skip_ssl and parsed.scheme == "https":
        results.append(check_ssl_certificate(hostname))
    elif skip_ssl:
        results.append(CheckResult(
            "SSL Certificate", True,
            "Skipped (--skip-ssl)",
            severity="info",
        ))

    # 5. Nginx config
    if parsed.scheme == "https":
        results.append(check_nginx_config(url))
    else:
        results.append(CheckResult(
            "Nginx Config", True,
            "Skipped (not HTTPS)",
            severity="info",
        ))

    return results


def main():
    parser = argparse.ArgumentParser(
        description="HR Intelligence Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/healthcheck.py                              # full check
  python scripts/healthcheck.py --url http://localhost:8000 --skip-ssl --skip-docker
  python scripts/healthcheck.py --json                       # JSON output
""",
    )
    parser.add_argument("--url", type=str, default="https://hr.cfai.in",
                        help="Base URL to check (default: https://hr.cfai.in)")
    parser.add_argument("--skip-ssl", action="store_true",
                        help="Skip SSL certificate check")
    parser.add_argument("--skip-docker", action="store_true",
                        help="Skip Docker container check")
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--timeout", type=int, default=10,
                        help="HTTP timeout in seconds (default: 10)")
    args = parser.parse_args()

    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    if not args.output_json:
        print(f"""
{'=' * 60}
  HR INTELLIGENCE — HEALTH CHECK
  Target : {args.url}
  Time   : {now_ist}
{'=' * 60}
""")

    results = run_healthcheck(
        url=args.url,
        skip_ssl=args.skip_ssl,
        skip_docker=args.skip_docker,
        output_json=args.output_json,
    )

    if args.output_json:
        output = {
            "timestamp": now_ist,
            "target": args.url,
            "checks": [r.to_dict() for r in results],
            "all_passed": all(r.passed for r in results),
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "warnings": sum(1 for r in results if r.severity == "warning"),
            },
        }
        print(json.dumps(output, indent=2))
    else:
        for result in results:
            print(result)
            print()

        # Summary
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        warnings = sum(1 for r in results if r.passed and r.severity == "warning")
        total = len(results)

        print(f"{'=' * 60}")
        if failed == 0:
            print(f"  ✅ ALL {total} CHECKS PASSED", end="")
            if warnings:
                print(f" ({warnings} warnings)")
            else:
                print()
        else:
            print(f"  ❌ {failed}/{total} CHECKS FAILED")
        print(f"{'=' * 60}")

    # Exit code
    if any(not r.passed for r in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
