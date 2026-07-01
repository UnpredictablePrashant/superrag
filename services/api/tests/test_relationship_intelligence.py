from app.services.relationship_intelligence import extract_relationship_signals


def test_relationship_extraction_finds_banking_entities_deal_and_actions() -> None:
    signals = extract_relationship_signals(
        """
        Meeting: 2026-06-20
        Client: Acme Technologies Pvt Ltd
        Investors: Northstar Capital, Horizon Ventures
        Attendees: Priya Sharma, Arjun Mehta
        Acme is preparing a USD 25m Series B fundraise.
        Action item: Send updated financial model by 2026-07-05.
        - Follow up with Northstar Capital on diligence questions.
        """,
        title="Acme investor meeting",
        source_type="granola",
    )

    names = {signal.name for signal in signals.entities}
    assert "Acme Technologies Pvt Ltd" in names
    assert "Northstar Capital" in names
    assert "Horizon Ventures" in names
    assert any(signal.entity_type == "person" and signal.name == "Priya Sharma" for signal in signals.entities)
    assert signals.interactions[0].interaction_type == "meeting"
    assert signals.deals[0].deal_type == "capital_raise"
    assert signals.deals[0].currency == "USD"
    assert len(signals.actions) == 2


def test_relationship_extraction_keeps_evidence_excerpts() -> None:
    signals = extract_relationship_signals(
        "Investor: Example Capital\nNext step: Schedule partner call tomorrow.",
        title="Example Capital call notes",
        source_type="document",
    )

    assert signals.entities[0].excerpt
    assert signals.actions[0].excerpt.startswith("Next step")
