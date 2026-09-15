import smtplib

from upv_auto.adapters import email as email_module
from upv_auto.adapters.email import EmailNotifier


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.logged_in_with = None
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, username, password):
        self.logged_in_with = (username, password)

    def send_message(self, message):
        self.sent.append(message)


def test_notify_sends_email_with_subject_from_first_line(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSMTP)
    notifier = EmailNotifier("me@gmail.com", "abcd efgh ijkl mnop", "me@gmail.com")

    notifier.notify("Booked: pista 1 at 18:00\nAttempts: 3")

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 465)
    assert smtp.logged_in_with == ("me@gmail.com", "abcdefghijklmnop")
    message = smtp.sent[0]
    assert message["Subject"] == "[upv-auto] Booked: pista 1 at 18:00"
    assert message["To"] == "me@gmail.com"
    assert "Attempts: 3" in message.get_content()


def test_notify_swallows_smtp_errors_without_leaking_password(monkeypatch, caplog):
    class FailingSMTP(FakeSMTP):
        def login(self, username, password):
            raise smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FailingSMTP)
    notifier = EmailNotifier("me@gmail.com", "supersecret", "me@gmail.com")

    notifier.notify("Login check OK")

    assert "Failed to send email notification" in caplog.text
    assert "supersecret" not in caplog.text
