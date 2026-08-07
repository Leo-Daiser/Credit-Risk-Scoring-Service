import numpy as np
import pandas as pd
import pytest

from src.features.advanced_history_features import (
    aggregate_credit_card,
    aggregate_installments,
    aggregate_pos_cash,
    aggregate_previous_applications,
    merge_advanced_history_features,
)


def test_previous_application_features_include_status_and_credit_ratios():
    frame = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2],
            "SK_ID_PREV": [10, 11, 20],
            "NAME_CONTRACT_STATUS": ["Approved", "Refused", "Approved"],
            "AMT_ANNUITY": [10.0, 20.0, 15.0],
            "AMT_APPLICATION": [100.0, 200.0, 100.0],
            "AMT_CREDIT": [90.0, 220.0, 100.0],
            "AMT_DOWN_PAYMENT": [10.0, 0.0, 5.0],
            "AMT_GOODS_PRICE": [100.0, 200.0, 100.0],
            "HOUR_APPR_PROCESS_START": [10, 11, 12],
            "RATE_DOWN_PAYMENT": [0.1, 0.0, 0.05],
            "CNT_PAYMENT": [12, 24, 10],
            "DAYS_DECISION": [-20, -10, -5],
            "DAYS_FIRST_DRAWING": [365243, -5, -2],
            "DAYS_FIRST_DUE": [-10, -5, -2],
            "DAYS_LAST_DUE": [-1, -1, -1],
            "DAYS_TERMINATION": [-1, -1, -1],
            "NFLAG_INSURED_ON_APPROVAL": [1, 0, 1],
        }
    )

    result = aggregate_previous_applications(frame).set_index("SK_ID_CURR")

    assert result.loc[1, "PREV_RECORD_COUNT"] == 2
    assert result.loc[1, "PREV_APPROVED_RATIO"] == pytest.approx(0.5)
    assert result.loc[1, "PREV_REFUSED_RATIO"] == pytest.approx(0.5)
    assert result.loc[1, "PREV_CREDIT_APPLICATION_RATIO_MEAN"] == pytest.approx((0.9 + 1.1) / 2)


def test_pos_features_capture_delinquency_and_latest_state():
    frame = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2],
            "SK_ID_PREV": [10, 10, 20],
            "MONTHS_BALANCE": [-2, -1, -1],
            "CNT_INSTALMENT": [12.0, 12.0, 6.0],
            "CNT_INSTALMENT_FUTURE": [5.0, 4.0, 1.0],
            "NAME_CONTRACT_STATUS": ["Active", "Active", "Completed"],
            "SK_DPD": [0, 3, 0],
            "SK_DPD_DEF": [0, 1, 0],
        }
    )

    result = aggregate_pos_cash(frame).set_index("SK_ID_CURR")

    assert result.loc[1, "POS_DPD_FLAG_MEAN"] == pytest.approx(0.5)
    assert result.loc[1, "POS_LATEST_SK_DPD"] == 3
    assert result.loc[2, "POS_COMPLETED_RATIO"] == pytest.approx(1.0)


def test_installment_features_capture_late_and_underpaid_behavior():
    frame = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1, 2],
            "SK_ID_PREV": [10, 10, 20],
            "NUM_INSTALMENT_VERSION": [1, 1, 1],
            "NUM_INSTALMENT_NUMBER": [1, 2, 1],
            "DAYS_INSTALMENT": [-10, -5, -3],
            "DAYS_ENTRY_PAYMENT": [-8, -6, -3],
            "AMT_INSTALMENT": [100.0, 100.0, 50.0],
            "AMT_PAYMENT": [80.0, 100.0, 50.0],
        }
    )

    result = aggregate_installments(frame).set_index("SK_ID_CURR")

    assert result.loc[1, "INSTALLMENT_DAYS_LATE_MAX"] == 2
    assert result.loc[1, "INSTALLMENT_LATE_FLAG_MEAN"] == pytest.approx(0.5)
    assert result.loc[1, "INSTALLMENT_UNDERPAID_FLAG_MEAN"] == pytest.approx(0.5)


def test_credit_card_features_capture_utilization_and_dpd():
    frame = pd.DataFrame(
        {
            "SK_ID_CURR": [1, 1],
            "SK_ID_PREV": [10, 10],
            "MONTHS_BALANCE": [-2, -1],
            "NAME_CONTRACT_STATUS": ["Active", "Active"],
            "AMT_BALANCE": [50.0, 80.0],
            "AMT_CREDIT_LIMIT_ACTUAL": [100.0, 100.0],
            "AMT_PAYMENT_TOTAL_CURRENT": [10.0, 20.0],
            "SK_DPD": [0, 2],
            "SK_DPD_DEF": [0, 0],
        }
    )
    for column in (
        "AMT_DRAWINGS_ATM_CURRENT",
        "AMT_DRAWINGS_CURRENT",
        "AMT_DRAWINGS_OTHER_CURRENT",
        "AMT_DRAWINGS_POS_CURRENT",
        "AMT_INST_MIN_REGULARITY",
        "AMT_PAYMENT_CURRENT",
        "AMT_RECEIVABLE_PRINCIPAL",
        "AMT_RECIVABLE",
        "AMT_TOTAL_RECEIVABLE",
        "CNT_DRAWINGS_ATM_CURRENT",
        "CNT_DRAWINGS_CURRENT",
        "CNT_DRAWINGS_OTHER_CURRENT",
        "CNT_DRAWINGS_POS_CURRENT",
        "CNT_INSTALMENT_MATURE_CUM",
    ):
        frame[column] = 0.0

    result = aggregate_credit_card(frame).set_index("SK_ID_CURR")

    assert result.loc[1, "CC_UTILIZATION_RATIO_MEAN"] == pytest.approx(0.65)
    assert result.loc[1, "CC_DPD_FLAG_MEAN"] == pytest.approx(0.5)
    assert result.loc[1, "CC_LATEST_CC_UTILIZATION_RATIO"] == pytest.approx(0.8)


def test_merge_advanced_features_is_unique_and_rejects_duplicate_keys():
    first = pd.DataFrame({"SK_ID_CURR": [1, 2], "A": [1.0, 2.0]})
    second = pd.DataFrame({"SK_ID_CURR": [2, 3], "B": [3.0, 4.0]})
    merged = merge_advanced_history_features([first, second])
    assert list(merged["SK_ID_CURR"]) == [1, 2, 3]
    assert not np.isinf(merged.select_dtypes(include="number")).any().any()

    duplicate = pd.DataFrame({"SK_ID_CURR": [1, 1], "C": [1, 2]})
    with pytest.raises(ValueError, match="duplicate"):
        merge_advanced_history_features([first, duplicate])
