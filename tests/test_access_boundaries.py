from src.api.access import ENDPOINT_ACCESS_MATRIX, AccessClass


def test_endpoint_access_matrix_covers_required_boundaries():
    classified = {(item.method, item.path): item.access for item in ENDPOINT_ACCESS_MATRIX}
    assert classified[("POST", "/v1/offers/match")] == AccessClass.PUBLIC
    assert classified[("POST", "/v1/offers/{offer_id}/click")] == AccessClass.PUBLIC
    assert classified[("POST", "/score")] == AccessClass.OPERATOR_ONLY
    assert classified[("POST", "/v1/analytics/public-event")] == AccessClass.PUBLIC
    assert (
        classified[("GET", "/v1/analytics/commercial-summary")]
        == AccessClass.OPERATOR_ONLY
    )
    assert classified[("POST", "/v1/partner/postback")] == AccessClass.PARTNER_ONLY
    assert classified[("GET", "/v1/runtime/status")] == AccessClass.LOCAL_DEMO_ONLY
    assert classified[("GET", "/v1/operator/offers")] == AccessClass.BFF_ONLY
    assert classified[("POST", "/v1/operator/offers")] == AccessClass.BFF_ONLY
    assert classified[("PATCH", "/v1/operator/offers/{offer_id}")] == AccessClass.BFF_ONLY
