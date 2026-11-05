"""
Unit tests for request intent classification (code/policy/intent.py).

Tests that deletion requests are distinguished from access requests, export
requests, rectification requests, marketing opt-outs, and informational queries
across multiple languages.
"""

import pytest
from code.policy.intent import classify_request_intent


def test_standard_english_deletion_requests():
    """Valid English deletion requests should be recognized."""
    cases = [
        "Please delete my account and remove my personal data.",
        "I want to permanently erase my profile and all associated data.",
        "Kindly close my account and wipe all records.",
        "Hi, I haven't used this account in years and would like it closed. Please remove the profile.",
        "Please purge all my records under the GDPR right to be forgotten.",
        "I request the deletion of the account associated with this email address.",
        "Please forget me and delete all my user data from your servers.",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is True, f"Failed for text: {text}"
        assert reason is None


def test_multilingual_deletion_requests():
    """Multilingual deletion requests (ES, FR, DE, JA, KO, PT) should be recognized."""
    cases = [
        ("Intenté eliminar mi cuenta ayer. ¿Pueden completar la eliminación?", True),
        ("Por favor borren mi cuenta y todos mis datos personales.", True),
        ("Je demande la suppression définitive du compte associé à cette adresse e-mail.", True),
        ("Veuillez effacer mon compte et toutes mes données personnelles.", True),
        ("Bitte löschen Sie mein Konto und alle damit verbundenen Daten.", True),
        ("Ich möchte mein Konto schließen und alle persönlichen Daten entfernen.", True),
        ("このメールアドレスに関連するアカウントの完全な削除を依頼します。", True),
        ("Por favor, exclua minha conta e remova todos os registros.", True),
        ("제 계정과 관련된 모든 개인 데이터를 영구적으로 삭제해 주세요.", True),
    ]
    for text, expected in cases:
        is_del, _ = classify_request_intent(text)
        assert is_del is expected, f"Failed for text: {text}"


def test_deletion_mentioning_exports_or_backups():
    """A deletion request that mentions exports, attachments, or backups is still a deletion request."""
    cases = [
        "Please delete this account, including the downloadable archive I requested earlier.",
        "I want to close this account permanently. You may retain backups if required, but they must not be able to restore my profile.",
        "Please delete my account and the identity document I sent to support while resolving a delivery issue.",
        "I closed my account, but an old 'download your data' link still works. Please delete that export file as well.",
        "Please remove my profile and clean my personal details out of earlier support conversations.",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is True, f"Failed for text: {text}"
        assert reason is None


def test_subject_access_requests():
    """Subject Access Requests (SAR) must be classified as NOT_APPLICABLE."""
    cases = [
        "This is a formal Subject Access Request (SAR). Please provide a copy of all my data.",
        "What data do you have on me? Please provide an overview.",
        "I would like to view my personal information stored in your systems.",
        "Solicitud de acceso a mis datos personales de acuerdo con la ley.",
        "Je souhaite avoir accès à mes données personnelles.",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is False, f"Expected non-deletion for: {text}"
        assert reason is not None
        assert "access" in reason.lower() or "authorize" in reason.lower()


def test_data_export_requests():
    """Standalone data export requests must be classified as NOT_APPLICABLE."""
    cases = [
        "Please send me a copy of my data for portability purposes.",
        "I would like to download a copy of my data.",
        "Please export all my account data into a JSON file.",
        "Quiero descargar mis datos para transferirlos a otro servicio.",
        "Veuillez exporter mes données personnelles.",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is False, f"Expected non-deletion for: {text}"
        assert reason is not None
        assert "export" in reason.lower() or "portability" in reason.lower()


def test_correction_requests():
    """Data rectification/correction requests must be classified as NOT_APPLICABLE."""
    cases = [
        "Please update my email address from old@example.com to new@example.com.",
        "There is a typo in my name. Please correct my name to Johnathan.",
        "Please change my phone number in my profile.",
        "Por favor actualicen mi dirección postal en el sistema.",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is False, f"Expected non-deletion for: {text}"
        assert reason is not None
        assert "rectification" in reason.lower() or "correction" in reason.lower()


def test_marketing_opt_out_requests():
    """Marketing opt-out requests must be classified as NOT_APPLICABLE."""
    cases = [
        "Please unsubscribe me from your promotional emails.",
        "I want to opt out of marketing communications.",
        "Stop sending me newsletters and marketing offers.",
        "Por favor darme de baja de la lista de publicidad.",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is False, f"Expected non-deletion for: {text}"
        assert reason is not None
        assert "marketing" in reason.lower() or "opt-out" in reason.lower()


def test_informational_inquiries():
    """Informational questions must be classified as NOT_APPLICABLE."""
    cases = [
        "How do I delete my account?",
        "How can I close this profile?",
        "What is your deletion policy for user data?",
    ]
    for text in cases:
        is_del, reason = classify_request_intent(text)
        assert is_del is False, f"Expected non-deletion for: {text}"
        assert reason is not None
        assert "inquiry" in reason.lower()


def test_empty_or_whitespace_requests():
    """Empty or None text must safely return False."""
    assert classify_request_intent("") == (False, "Empty or missing request text")
    assert classify_request_intent("   ") == (False, "Empty or missing request text")
    assert classify_request_intent(None) == (False, "Empty or missing request text")


def test_intent_confirm_profile_gone():
    """Verify that requests asking to confirm an account or profile is gone are recognized as deletion audits."""
    text = "Please check the latest state and confirm that the profile is gone and remaining records cannot identify me."
    is_del, reason = classify_request_intent(text)
    assert is_del is True
    assert reason is None
