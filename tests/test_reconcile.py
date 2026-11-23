from decimal import Decimal

from secid import reconcile


def by_key(rows):
    return {r.key: r for r in rows}


def test_matches_across_identifier_types():
    custodian = [("037833100", 100), ("0263494", 50)]  # CUSIP, SEDOL
    admin = [("US0378331005", 100), ("GB0002634946", 50)]  # ISINs
    rows = by_key(reconcile(custodian, admin))
    assert rows["US0378331005"].status == "matched"
    assert rows["GB0002634946"].status == "matched"
    assert rows["US0378331005"].left_ids == ("037833100",)


def test_breaks_missing_and_invalid():
    left = {"037833100": "100", "594918104": "10", "BADID": "5"}
    right = {"US0378331005": "90", "DE0007164600": "7"}
    rows = reconcile(left, right)
    statuses = {r.key: r.status for r in rows}
    assert statuses == {
        "BADID": "invalid_identifier",
        "US0378331005": "quantity_break",
        "US5949181045": "missing_right",
        "DE0007164600": "missing_left",
    }
    assert rows[0].status == "invalid_identifier"
    assert by_key(rows)["US0378331005"].difference == Decimal(10)


def test_duplicates_are_summed_and_tolerance_applies():
    left = [("037833100", "60.5"), ("US0378331005", "39.5")]
    right = [("US0378331005", "100.004")]
    rows = reconcile(left, right, tolerance="0.01")
    assert rows[0].status == "matched"
    assert rows[0].left_qty == Decimal("100.0")
    assert set(rows[0].left_ids) == {"037833100", "US0378331005"}
