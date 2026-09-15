"""Domain errors raised by the authentication flow."""


class AuthenticationFailed(Exception):
    """CAS login was rejected for an ordinary reason (bad credentials, locked account, ...).

    Never carries the password.
    """


class AuthenticationUnavailable(Exception):
    """The UPV servers could not complete the login right now (5xx, timeout, network error).

    Transient by nature, so it is safe to retry. Bad credentials never raise this.
    """


class AuthenticationBlocked(Exception):
    """Login cannot proceed safely: captcha, 2FA/OTP, or another unexpected page.

    The authenticator must never attempt to bypass this; it should stop and report it.
    """
