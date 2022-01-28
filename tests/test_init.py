# test_init.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Fri 28 Jan 2022 16:38:38 GMT

"""Test :py:mod:`nmrespy.__init__`."""

import pytest
from nmrespy import ExpInfo, RED, END


def check_expinfo_correct(expinfo, sw, offset, sfo, nuclei, dim, kwargs=None):
    """Ensure expinfo attributes match the function args."""
    checks = [
        expinfo.sw == sw,
        expinfo.offset == offset,
        expinfo.sfo == sfo,
        expinfo.nuclei == nuclei,
        expinfo.dim == dim,
    ]

    if kwargs is not None:
        for key, value in kwargs.items():
            checks.append(expinfo.__dict__[key] == value)

    return all(checks)


def test_expinfo():
    """Test :py:class:`nmrespy.ExpInfo`."""
    sw = 5000
    offset = [2000.0]
    sfo = 500
    nuclei = "13C"
    expinfo = ExpInfo(sw, offset, sfo=sfo, nuclei=nuclei)
    assert check_expinfo_correct(
        expinfo,
        (5000.0,),
        (2000.0,),
        (500.0,),
        ("13C",),
        1,
    )

    expinfo = ExpInfo(sw, offset, sfo=sfo, nuclei=nuclei, dim=2)
    assert check_expinfo_correct(
        expinfo,
        (5000.0, 5000.0),
        (2000.0, 2000.0),
        (500.0, 500.0),
        ("13C", "13C"),
        2,
    )

    expinfo = ExpInfo(
        sw,
        offset,
        sfo=sfo,
        nuclei=nuclei,
        dim=2,
        array=[1, 2, 3, 4],
        dic={"a": 10, "b": 20},
    )
    assert check_expinfo_correct(
        expinfo,
        (5000.0, 5000.0),
        (2000.0, 2000.0),
        (500.0, 500.0),
        ("13C", "13C"),
        2,
        {"array": [1, 2, 3, 4], "dic": {"a": 10, "b": 20}},
    )

    assert expinfo.unpack("sw") == (5000.0, 5000.0)
    assert expinfo.unpack("sw", "offset", "sfo") == (
        (5000.0, 5000.0),
        (2000.0, 2000.0),
        (500.0, 500.0),
    )

    expinfo.sw = [8000, 8000.0]
    assert expinfo.sw == (8000.0, 8000.0)

    for input_ in [1024, ["13C", 1024]]:
        with pytest.raises(ValueError) as exc_info:
            expinfo.nuclei = input_
        assert (
            str(exc_info.value) ==
            f"{RED}Invalid value supplied to nuclei: {repr(input_)}{END}"
        )
    expinfo.nuclei = "205Pb"
    assert expinfo.nuclei == ("205Pb", "205Pb")
