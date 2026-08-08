import json
import logging

from src.core.logging import JsonLogFormatter, bind_correlation_id, reset_correlation_id


def test_json_log_formatter_emits_allowlisted_context():
    token = bind_correlation_id("correlation-123")
    try:
        record = logging.LogRecord(
            name="src.api.main",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="http_request_completed",
            args=(),
            exc_info=None,
        )
        record.method = "POST"
        record.path = "/score"
        record.status_code = 200
        record.duration_ms = 12.5
        record.features = {"AMT_INCOME_TOTAL": 180_000}
        record.requested_amount = 250_000
        record.existing_monthly_payments = 30_000
        record.partner_secret = "must-not-leak"

        event = json.loads(JsonLogFormatter().format(record))
    finally:
        reset_correlation_id(token)

    assert event["message"] == "http_request_completed"
    assert event["correlation_id"] == "correlation-123"
    assert event["method"] == "POST"
    assert event["path"] == "/score"
    assert event["status_code"] == 200
    assert event["duration_ms"] == 12.5
    assert "features" not in event
    assert "requested_amount" not in event
    assert "existing_monthly_payments" not in event
    assert "partner_secret" not in event
