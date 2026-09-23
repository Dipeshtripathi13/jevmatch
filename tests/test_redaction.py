from core.redaction import redact_pii


def test_redacts_header_name_and_contact_details():
    source = """Jane Q Public
jane.public@example.com | +1 (212) 555-0198
https://linkedin.com/in/janepublic
123 Main Street, New York, NY 10001

EXPERIENCE
Built reliable APIs for Public Media.
"""
    result = redact_pii(source)
    assert "Jane Q Public" not in result
    assert "jane.public@example.com" not in result
    assert "555-0198" not in result
    assert "linkedin.com" not in result
    assert "123 Main Street" not in result
    assert "Built reliable APIs" in result
    assert "[NAME REDACTED]" in result


def test_does_not_remove_ordinary_title_as_name():
    source = "Senior Software Engineer\nPython and FastAPI"
    assert redact_pii(source).startswith("Senior Software Engineer")
