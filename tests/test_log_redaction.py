from __future__ import annotations

import logging

from upv_auto.adapters.log_redaction import RedactingFilter, configure_log_hygiene, mask_for_actions

MESSAGE = (
    "User alice123 with password s3cr3t-pw booked MUS021, contact alice@example.com, "
    "request 123e4567-e89b-12d3-a456-426614174000"
)


def test_redacting_filter_scrubs_registered_secrets_and_structural_patterns(caplog):
    filter_ = RedactingFilter()
    filter_.register("alice123", "s3cr3t-pw")
    logger = logging.getLogger("upv_auto.test_log_redaction")
    logger.addFilter(filter_)
    try:
        with caplog.at_level(logging.INFO, logger="upv_auto.test_log_redaction"):
            logger.info(MESSAGE)
    finally:
        logger.removeFilter(filter_)

    assert len(caplog.records) == 1
    text = caplog.records[0].getMessage()
    assert "alice123" not in text
    assert "s3cr3t-pw" not in text
    assert "MUS021" not in text
    assert "alice@example.com" not in text
    assert "123e4567-e89b-12d3-a456-426614174000" not in text
    assert "[group]" in text
    assert "[email]" in text
    assert "[id]" in text


def test_redacting_filter_leaves_unrelated_text_untouched():
    filter_ = RedactingFilter()
    filter_.register("alice123")
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "Booking finished after 3 attempts", (), None)

    filter_.filter(record)

    assert record.getMessage() == "Booking finished after 3 attempts"


def test_configure_log_hygiene_attaches_filter_and_quiets_httpx_logger():
    filter_ = RedactingFilter()
    root = logging.getLogger()
    try:
        configure_log_hygiene(filter_)
        assert filter_ in root.filters
        assert logging.getLogger("httpx").level == logging.WARNING
    finally:
        root.removeFilter(filter_)


def test_mask_for_actions_prints_add_mask_lines_for_each_non_empty_value(capsys):
    mask_for_actions("secret-one", "", None, "secret-two")

    out = capsys.readouterr().out
    assert "::add-mask::secret-one" in out
    assert "::add-mask::secret-two" in out
    assert out.count("::add-mask::") == 2
