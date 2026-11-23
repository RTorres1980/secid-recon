import pytest

from secid import (
    IdType,
    InvalidIdentifier,
    cusip_check_digit,
    cusip_to_isin,
    detect,
    is_valid_cusip,
    is_valid_isin,
    is_valid_sedol,
    isin_to_cusip,
    isin_to_sedol,
    sedol_to_isin,
)

# Published identifiers for well-known securities.
APPLE_CUSIP, APPLE_ISIN = "037833100", "US0378331005"
MSFT_CUSIP, MSFT_ISIN = "594918104", "US5949181045"
BAE_SEDOL, BAE_ISIN = "0263494", "GB0002634946"


@pytest.mark.parametrize("cusip", [APPLE_CUSIP, MSFT_CUSIP, "38259P508"])
def test_valid_cusips(cusip):
    assert is_valid_cusip(cusip)


@pytest.mark.parametrize("cusip", ["037833101", "03783310", "0378331000", "", "03783310A"])
def test_invalid_cusips(cusip):
    assert not is_valid_cusip(cusip)


def test_cusip_check_digit():
    assert cusip_check_digit("03783310") == "0"
    assert cusip_check_digit("38259P50") == "8"


@pytest.mark.parametrize("isin", [APPLE_ISIN, MSFT_ISIN, BAE_ISIN, "DE0007164600", "AU0000XVGZA3"])
def test_valid_isins(isin):
    assert is_valid_isin(isin)


@pytest.mark.parametrize("isin", ["US0378331006", "US037833100", "1S0378331005", "US03783310O5"])
def test_invalid_isins(isin):
    assert not is_valid_isin(isin)


@pytest.mark.parametrize("sedol", [BAE_SEDOL, "B0YBKJ7", "2046251"])
def test_valid_sedols(sedol):
    assert is_valid_sedol(sedol)


@pytest.mark.parametrize("sedol", ["0263495", "A263494", "026349", "B0YBKJ8"])
def test_invalid_sedols(sedol):
    assert not is_valid_sedol(sedol)


def test_detect_and_normalize():
    assert detect(" us0378331005 ") is IdType.ISIN
    assert detect(APPLE_CUSIP) is IdType.CUSIP
    assert detect(BAE_SEDOL) is IdType.SEDOL
    assert detect("not-an-id") is None


def test_round_trips():
    assert cusip_to_isin(APPLE_CUSIP) == APPLE_ISIN
    assert isin_to_cusip(APPLE_ISIN) == APPLE_CUSIP
    assert sedol_to_isin(BAE_SEDOL) == BAE_ISIN
    assert isin_to_sedol(BAE_ISIN) == BAE_SEDOL


def test_conversion_guards():
    with pytest.raises(InvalidIdentifier):
        cusip_to_isin(APPLE_CUSIP, "GB")
    with pytest.raises(InvalidIdentifier):
        isin_to_cusip(BAE_ISIN)
    with pytest.raises(InvalidIdentifier):
        isin_to_sedol(APPLE_ISIN)
    with pytest.raises(InvalidIdentifier):
        cusip_to_isin("037833101")
