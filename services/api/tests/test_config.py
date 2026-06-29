from app.core.config import Settings


def test_cors_origins_accepts_single_origin_string() -> None:
    settings = Settings(_env_file=None, cors_origins="https://rag.atharvaai.com")

    assert settings.cors_origin_list == ["https://rag.atharvaai.com"]


def test_cors_origins_accepts_comma_separated_string() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins="http://localhost:3000, http://127.0.0.1:3000",
    )

    assert settings.cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_cors_origins_accepts_json_array_string() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins='["https://rag.atharvaai.com", "https://admin.atharvaai.com"]',
    )

    assert settings.cors_origin_list == [
        "https://rag.atharvaai.com",
        "https://admin.atharvaai.com",
    ]
