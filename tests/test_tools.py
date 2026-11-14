import pytest

from uk_postcode_intel.tools import _norm


def test_norm():
    assert _norm("sw1a1aa") == "SW1A 1AA"
    assert _norm(" M20 2rn ") == "M20 2RN"


def test_bad():
    with pytest.raises(ValueError):
        _norm("hello")
