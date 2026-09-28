# tests/test_email_alerts_listener.py
# EmailAlertsListener.update(): looks up the REACHED USER's own SMTP
# config (never a shared account), sends through Red Mail using it, and
# degrades silently (like travel_logic/checkpoints.py's generate_description()
# AI-call fallback) instead of ever raising back into
# TravelFacade._notify_progress()'s steps/workout sync path.
#
# Red Mail's EmailSender and notifications/email_config.get_config are
# both monkeypatched - this file proves the listener's own wiring, not
# Red Mail's SMTP handling or email_config's DB logic (tests/test_email_config.py
# already covers that for real).

import uuid

from core.observer_decorator import email_alerts_listener as listener_module
from core.observer_decorator.email_alerts_listener import EmailAlertsListener
from core.observer_decorator.events import CheckpointReachedEvent
from notifications import email_config


class _FakeSession:
    pass


class _FakeSessionLocal:
    def __enter__(self):
        return _FakeSession()

    def __exit__(self, *args):
        return False


class _FakeConfig:
    def __init__(self, smtp_host="smtp.gmail.com", smtp_port=587, smtp_username="walker@example.com", smtp_password="app-password"):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password


class _FakeEmailSender:
    """Records how it was constructed and what it was asked to send -
    never touches a real socket."""
    instances = []

    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sent = []
        _FakeEmailSender.instances.append(self)

    def send(self, subject, receivers, text):
        self.sent.append({"subject": subject, "receivers": receivers, "text": text})


class _RaisingEmailSender:
    def __init__(self, *a, **k):
        pass

    def send(self, **kwargs):
        raise ConnectionRefusedError("smtp server unreachable")


def _event(**overrides) -> CheckpointReachedEvent:
    defaults = dict(
        user_id=uuid.uuid4(),
        user_name="walker@example.com",
        checkpoint_name="Springfield",
        checkpoint_number=3,
        description="Home of a very yellow family.",
    )
    defaults.update(overrides)
    return CheckpointReachedEvent(**defaults)


def _patch(monkeypatch, config, sender_cls=_FakeEmailSender):
    monkeypatch.setattr(listener_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(listener_module, "EmailSender", sender_cls)
    monkeypatch.setattr(email_config, "get_config", lambda session, user_id: config)


def test_sends_through_the_reached_users_own_smtp_account(monkeypatch):
    _FakeEmailSender.instances.clear()
    config = _FakeConfig(smtp_host="smtp.gmail.com", smtp_port=587, smtp_username="walker@example.com", smtp_password="app-password")
    _patch(monkeypatch, config)

    EmailAlertsListener().update(_event())

    assert len(_FakeEmailSender.instances) == 1
    sender = _FakeEmailSender.instances[0]
    assert sender.host == "smtp.gmail.com"
    assert sender.port == 587
    assert sender.username == "walker@example.com"
    assert sender.password == "app-password"
    assert sender.sent[0]["receivers"] == ["walker@example.com"]


def test_email_text_includes_user_checkpoint_number_and_description(monkeypatch):
    _FakeEmailSender.instances.clear()
    _patch(monkeypatch, _FakeConfig())

    EmailAlertsListener().update(_event(
        user_name="Alex", checkpoint_name="Springfield", checkpoint_number=3,
        description="Home of a very yellow family.",
    ))

    sent_text = _FakeEmailSender.instances[0].sent[0]["text"]
    assert "Alex has reached Springfield!" in sent_text
    assert "checkpoint #3" in sent_text
    assert "Home of a very yellow family." in sent_text


def test_does_nothing_when_the_user_has_no_email_config(monkeypatch):
    _FakeEmailSender.instances.clear()
    _patch(monkeypatch, config=None)

    EmailAlertsListener().update(_event())  # must not raise

    assert _FakeEmailSender.instances == []


def test_a_send_failure_is_swallowed_not_raised(monkeypatch):
    _patch(monkeypatch, _FakeConfig(), sender_cls=_RaisingEmailSender)

    EmailAlertsListener().update(_event())  # must not raise
