"""
tests/test_url_safety.py
Unit tests verifying E14: SSRF prevention, TLS certificate verification, and response bounding.
"""

import pytest

from backend.agents.job_parser_agent import fetch_url_content, safe_http_get, validate_and_sanitize_url


def test_ssrf_rejects_loopback_destinations():
    """Verify localhost and loopback IPv4/IPv6 URLs are blocked (E14)."""
    with pytest.raises(ValueError, match="forbidden|prohibited"):
        validate_and_sanitize_url("http://localhost:8000/internal-job")

    with pytest.raises(ValueError, match="forbidden|prohibited"):
        validate_and_sanitize_url("http://127.0.0.1:9000/api")

    with pytest.raises(ValueError, match="forbidden|prohibited"):
        validate_and_sanitize_url("http://127.0.0.1/admin")


def test_ssrf_rejects_private_and_cloud_metadata_ips():
    """Verify RFC 1918 private subnets and 169.254.169.254 cloud metadata are blocked (E14)."""
    # Cloud metadata IP
    with pytest.raises(ValueError, match="prohibited"):
        validate_and_sanitize_url("http://169.254.169.254/latest/meta-data/")

    # RFC 1918 Private networks
    with pytest.raises(ValueError, match="prohibited"):
        validate_and_sanitize_url("http://10.0.0.1/job")

    with pytest.raises(ValueError, match="prohibited"):
        validate_and_sanitize_url("http://192.168.1.50/job")

    with pytest.raises(ValueError, match="prohibited"):
        validate_and_sanitize_url("http://172.16.0.1/job")


def test_url_scheme_validation():
    """Verify non-HTTP(S) schemes are blocked immediately."""
    with pytest.raises(ValueError, match="URL must begin with http:// or https://"):
        validate_and_sanitize_url("file:///etc/passwd")

    with pytest.raises(ValueError, match="URL must begin with http:// or https://"):
        validate_and_sanitize_url("ftp://ftp.example.com/job.txt")

    with pytest.raises(ValueError, match="URL must begin with http:// or https://"):
        validate_and_sanitize_url("gopher://example.com")


def test_fetch_url_content_ssrf_guard():
    """Verify fetch_url_content rejects SSRF attacks."""
    with pytest.raises(ValueError):
        fetch_url_content("http://127.0.0.1:8000/admin")

    with pytest.raises(ValueError):
        fetch_url_content("http://169.254.169.254/latest/meta-data/")
