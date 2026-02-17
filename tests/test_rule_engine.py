from __future__ import annotations

import re


def test_tokenize_consistency_same_value(client):
    engine = client.app.state.rule_engine

    text = "Contact mario.rossi@example.com and then again mario.rossi@example.com"
    result = engine.sanitize("session-1", text)

    tokens = re.findall(r"<TKN_[A-Z0-9_]+_[0-9]{3}>", result.sanitized_text)
    assert len(tokens) == 2
    assert tokens[0] == tokens[1]
    assert result.tokens_created == 1


def test_business_terms_reconcile_allowed(client):
    engine = client.app.state.rule_engine

    text = "Client Enel requests support"
    result = engine.sanitize("session-2", text)

    token_match = re.search(r"<TKN_[A-Z0-9_]+_[0-9]{3}>", result.sanitized_text)
    assert token_match is not None

    token = token_match.group(0)
    reconciled, replaced, missing = engine.reconcile("session-2", f"Result for {token}")

    assert "Enel" in reconciled
    assert replaced >= 1
    assert missing == []


def test_pii_reconcile_follows_policy(client):
    engine = client.app.state.rule_engine

    text = "Sensitive email: privacy@example.com"
    result = engine.sanitize("session-3", text)

    token_match = re.search(r"<TKN_[A-Z0-9_]+_[0-9]{3}>", result.sanitized_text)
    assert token_match is not None

    token = token_match.group(0)
    reconciled, replaced, _ = engine.reconcile("session-3", f"Echo {token}")

    if "PII" in engine.never_reconcile_categories:
        assert token in reconciled
        assert replaced == 0
    else:
        assert "privacy@example.com" in reconciled
        assert replaced >= 1


def test_names_list_supports_reversed_word_order(client):
    engine = client.app.state.rule_engine

    text = "Meeting with Rossi Marco and Emily Davis."
    result = engine.sanitize("session-4", text)

    tokens = re.findall(r"<TKN_[A-Z0-9_]+_[0-9]{3}>", result.sanitized_text)
    assert len(tokens) == 2
    assert result.transformations >= 2
