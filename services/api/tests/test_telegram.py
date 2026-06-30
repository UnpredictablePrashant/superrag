from app.services.telegram import _command_body, _message_mode


def test_telegram_command_body_accepts_group_bot_suffix() -> None:
    message = {"text": "/ask@CompanyRagBot what is the PTO policy?"}

    assert _message_mode(message) == "ask"
    assert _command_body(message, "/ask") == "what is the PTO policy?"


def test_telegram_add_command_body_accepts_caption() -> None:
    message = {"caption": "/add@CompanyRagBot customer call notes"}

    assert _command_body(message, "/add") == "customer call notes"
