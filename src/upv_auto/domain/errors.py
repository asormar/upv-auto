"""Domain errors raised by the authentication flow."""


class AuthenticationFailed(Exception):
    """CAS login was rejected for an ordinary reason (bad credentials, locked account, ...).

    Never carries the password.
    """


class AuthenticationBlocked(Exception):
    """Login cannot proceed safely: captcha, 2FA/OTP, or another unexpected page.

    The authenticator must never attempt to bypass this; it should stop and report it.
    """
