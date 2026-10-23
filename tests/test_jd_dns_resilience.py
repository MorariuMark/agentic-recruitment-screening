"""Transient DNS recovery must retain validation on retries and redirects."""
import socket
from unittest.mock import MagicMock

import httpx
import pytest

from backend.agents import job_parser_agent as parser
from backend.services.url_errors import URLResolutionError

URL = "https://jobs.atos.net/job/example/123/"


def address(ip="130.214.193.81"):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.fixture
def dns(monkeypatch):
    resolve = MagicMock(return_value=address())
    monkeypatch.setattr(parser.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(parser.time, "sleep", MagicMock())
    return resolve


def test_transient_windows_dns_error_recovers(dns):
    dns.side_effect = [socket.gaierror(11001, "getaddrinfo failed"), address()]
    assert parser.validate_and_sanitize_url(URL) == URL
    assert dns.call_count == 2


def test_persistent_dns_error_is_bounded_and_actionable(dns):
    dns.side_effect = socket.gaierror(11001, "getaddrinfo failed")
    with pytest.raises(URLResolutionError) as failure:
        parser.validate_and_sanitize_url(URL)
    assert dns.call_count == 3
    assert isinstance(failure.value.__cause__, socket.gaierror)
    assert failure.value.hostname == "jobs.atos.net"
    assert "paste" in str(failure.value)


def test_dns_failure_never_fabricates_a_public_address_for_reserved_hosts(dns):
    dns.side_effect = socket.gaierror("NXDOMAIN")
    with pytest.raises(URLResolutionError):
        parser.validate_and_sanitize_url("https://nonexistent.invalid/job")


def test_private_address_after_dns_retry_is_still_blocked(dns):
    dns.side_effect = [socket.gaierror("temporary"), address("10.0.0.1")]
    with pytest.raises(ValueError, match="prohibited"):
        parser.validate_and_sanitize_url(URL)
    assert dns.call_count == 2


def fake_client(monkeypatch, outcomes):
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.side_effect = outcomes
    monkeypatch.setattr(parser.httpx, "Client", MagicMock(return_value=client))
    return client


def transport_dns_failure():
    error = httpx.ConnectError("DNS temporarily unavailable")
    error.__cause__ = socket.gaierror(11001, "getaddrinfo failed")
    return error


def test_dns_failure_inside_http_transport_is_retried_with_validation(monkeypatch, dns):
    response = httpx.Response(200, text="A complete job description", request=httpx.Request("GET", URL))
    client = fake_client(monkeypatch, [transport_dns_failure(), response])
    assert parser.safe_http_get(URL).status_code == 200
    assert client.get.call_count == 2 and dns.call_count == 2


def test_http_retry_cannot_bypass_private_destination_check(monkeypatch, dns):
    dns.side_effect = [address(), address("169.254.169.254")]
    client = fake_client(monkeypatch, [transport_dns_failure()])
    with pytest.raises(ValueError, match="prohibited"):
        parser.safe_http_get(URL)
    assert client.get.call_count == 1


def test_http_dns_failures_stop_after_three_requests(monkeypatch, dns):
    client = fake_client(monkeypatch, [transport_dns_failure() for _ in range(3)])
    with pytest.raises(URLResolutionError):
        parser.safe_http_get(URL)
    assert client.get.call_count == 3


def test_unrelated_connection_error_is_not_retried_as_dns(monkeypatch, dns):
    client = fake_client(monkeypatch, [httpx.ConnectError("Connection refused")])
    with pytest.raises(httpx.ConnectError):
        parser.safe_http_get(URL)
    assert client.get.call_count == 1


def test_redirect_dns_failure_is_validated_and_reported(monkeypatch, dns):
    redirect = httpx.Response(302, headers={"Location": "https://new-job-host.invalid/job"}, request=httpx.Request("GET", URL))
    client = fake_client(monkeypatch, [redirect])
    dns.side_effect = [address(), *[socket.gaierror("NXDOMAIN") for _ in range(3)]]
    with pytest.raises(URLResolutionError) as failure:
        parser.safe_http_get(URL)
    assert failure.value.hostname == "new-job-host.invalid"
    assert client.get.call_count == 1
