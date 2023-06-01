# __init__.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Thu 01 Jun 2023 17:52:51 BST

"""NMR-EsPy: Nuclear Magnetic Resonance Estimation in Python."""

import importlib
from pathlib import Path

MATLAB_AVAILABLE = importlib.util.find_spec("matlab") is not None
directory = Path(__file__).parent.resolve()
TOPSPINPATHS = [
    directory / "app/topspin_scripts" / x
    for x in (directory / "app/topspin_scripts").iterdir() if x.is_file()
]

from nmrespy.expinfo import ExpInfo
from nmrespy.estimators import Estimator
from nmrespy.estimators.onedim import Estimator1D
from nmrespy.estimators.bbqchili import BBQChili
from nmrespy.estimators.jres import Estimator2DJ
