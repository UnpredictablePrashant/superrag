from types import SimpleNamespace

from app.services.telegram import _command_body, _message_mode, _start_text


def test_telegram_command_body_accepts_group_bot_suffix() -> None:
    message = {"text": "/ask@CompanyRagBot what is the PTO policy?"}

    assert _message_mode(message) == "ask"
    assert _command_body(message, "/ask") == "what is the PTO policy?"


def test_telegram_add_command_body_accepts_caption() -> None:
    message = {"caption": "/add@CompanyRagBot customer call notes"}

    assert _command_body(message, "/add") == "customer call notes"


def test_telegram_start_has_own_mode() -> None:
    assert _message_mode({"text": "/start"}) == "start"
    assert _message_mode({"text": "/start@UnitusCapitalBot setup"}) == "start"


def test_telegram_start_guides_unmatched_user() -> None:
    text = _start_text(None)

    assert "Welcome to the Unitus Capital knowledge bot." in text
    assert "could not match this Telegram account" in text
    assert "/start again" in text


def test_telegram_start_lists_enabled_actions() -> None:
    text = _start_text(SimpleNamespace(can_query=True, can_ingest=True))

    assert "/ask your question" in text
    assert "/add your note" in text
    assert "Send /help" in text
