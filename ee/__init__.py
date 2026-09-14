"""Enterprise Edition. Production use needs a valid license key. See LICENSE.

Feature modules that land here should call ``enabled("sso")`` (or audit, isolation, …).
The check lives in the worker so a missing key leaves the free core running.
"""


def enabled(feature: str) -> bool:
    from marvin.license import allows
    return allows(feature)
