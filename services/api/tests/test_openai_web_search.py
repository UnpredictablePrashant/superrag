from app.services import openai_web_search


def test_openai_web_search_builds_candidate_from_response(monkeypatch) -> None:
    monkeypatch.setattr(
        openai_web_search,
        "get_openai_connection",
        lambda db, organization_id: ("sk-test", None),
    )
    monkeypatch.setattr(
        openai_web_search,
        "_call_openai_web_search",
        lambda **kwargs: {
            "output_text": "Fresh result from the web.",
            "output": [
                {
                    "content": [
                        {
                            "annotations": [
                                {
                                    "url": "https://example.com/source",
                                    "title": "Example source",
                                }
                            ]
                        }
                    ]
                }
            ],
        },
    )

    candidates = openai_web_search.openai_web_search_candidates(
        None,
        organization_id="00000000-0000-0000-0000-000000000001",
        query="latest policy",
    )

    assert candidates[0].document_name == "Example source"
    assert candidates[0].text == "Fresh result from the web."
    assert candidates[0].metadata["source_type"] == "OpenAI Web"
    assert candidates[0].metadata["source_url"] == "https://example.com/source"
