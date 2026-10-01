"""Credential-safe HTTP boundaries for the review repair branch."""
from urllib.parse import urlsplit
import requests
import repair_flags


class SafeHTTPError(RuntimeError):
    """Contains only an allowlisted endpoint and status, never a URL/body."""


_ENDPOINTS = {'account', 'fixtures', 'historical-odds', 'odds-by-tournaments'}


def public_error(error):
    if not repair_flags.enabled():
        return str(error)
    return str(error) if isinstance(error, SafeHTTPError) else 'Request failed; details withheld.'


class _Response:
    def __init__(self, response, endpoint):
        self._response = response
        self._endpoint = endpoint

    @property
    def status_code(self):
        return self._response.status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise SafeHTTPError(f'{self._endpoint}: HTTP {self.status_code}') from None

    def json(self):
        try:
            return self._response.json()
        except ValueError:
            raise SafeHTTPError(f'{self._endpoint}: invalid JSON response') from None


def get(url, **kwargs):
    if not repair_flags.enabled():
        return requests.get(url, **kwargs)
    endpoint = urlsplit(url).path.rsplit('/', 1)[-1]
    endpoint = endpoint if endpoint in _ENDPOINTS else 'provider'
    try:
        response = requests.get(url, **kwargs)
    except requests.RequestException:
        raise SafeHTTPError(f'{endpoint}: network request failed') from None
    return _Response(response, endpoint)
