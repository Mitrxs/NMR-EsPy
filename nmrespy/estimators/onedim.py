# onedim.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Thu 04 Aug 2022 10:45:02 BST

from __future__ import annotations
import copy
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, List, Optional, Tuple, Union

import numpy as np
import matplotlib.pyplot as plt

from nmr_sims.experiments.pa import PulseAcquireSimulation
from nmr_sims.nuclei import Nucleus
from nmr_sims.spin_system import SpinSystem

from nmrespy import MATLAB_AVAILABLE, ExpInfo, sig
from nmrespy._colors import RED, END, USE_COLORAMA
from nmrespy._files import cd, check_existent_dir
from nmrespy._paths_and_links import NMRESPYPATH, SPINACHPATH
from nmrespy._sanity import (
    sanity_check,
    funcs as sfuncs,
)
from nmrespy.freqfilter import Filter
from nmrespy.load import load_bruker
from nmrespy.mpm import MatrixPencil
from nmrespy.nlp import NonlinearProgramming
from nmrespy.plot import ResultPlotter

from . import logger, Estimator, Result


if USE_COLORAMA:
    import colorama
    colorama.init()

if MATLAB_AVAILABLE:
    import matlab
    import matlab.engine


class Estimator1D(Estimator):
    """Estimator class for 1D data.

    .. note::

        To create an instance of ``Estimator1D``, you should use one of the following
        methods:

        * :py:meth:`new_bruker`
        * :py:meth:`new_synthetic_from_parameters`
        * :py:meth:`new_synthetic_from_simulation`
        * :py:meth:`from_pickle` (re-loads a previously saved estimator).
    """

    def __init__(
        self,
        data: np.ndarray,
        expinfo: ExpInfo,
        datapath: Optional[Path] = None,
    ) -> None:
        """
        Parameters
        ----------
        data
            Time-domain data to estimate.

        expinfo
            Experiment information.

        datapath
            If applicable, the path that the data was derived from.
        """
        super().__init__(data, expinfo, datapath)

    @classmethod
    def new_bruker(
        cls,
        directory: Union[str, Path],
        convdta: bool = True,
    ) -> Estimator1D:
        """Create a new instance from Bruker-formatted data.

        Parameters
        ----------
        directory
            Absolute path to data directory.

        convdta
            If ``True`` and the data is derived from an ``fid`` file, removal of
            the FID's digital filter will be carried out.

        Notes
        -----
        **Directory Requirements**

        There are certain file paths expected to be found relative to ``directory``
        which contain the data and parameter files. Here is an extensive list of
        the paths expected to exist, for different data types:

        * Raw FID

          + ``directory/fid``
          + ``directory/acqus``

        * Processed data

          + ``directory/1r``
          + ``directory/../../acqus``
          + ``directory/procs``
        """
        sanity_check(
            ("directory", directory, check_existent_dir),
            ("convdta", convdta, sfuncs.check_bool),
        )

        directory = Path(directory).expanduser()
        data, expinfo = load_bruker(directory)

        if data.ndim != 1:
            raise ValueError(f"{RED}Data dimension should be 1.{END}")

        if directory.parent.name == "pdata":
            slice_ = slice(0, data.shape[0] // 2)
            data = (2 * sig.ift(data))[slice_]

        elif convdta:
            grpdly = expinfo.parameters["acqus"]["GRPDLY"]
            data = sig.convdta(data, grpdly)

        return cls(data, expinfo, directory)

    @classmethod
    def new_spinach(
        cls,
        shifts: Iterable[float],
        pts: int,
        sw: float,
        offset: float,
        field: float = 11.74,
        field_unit: str = "tesla",
        couplings: Optional[Iterable[Tuple(int, int, float)]] = None,
        channel: str = "1H",
        nuclei: Optional[List[str]] = None,
        tau_c: float = 200e-12,
    ) -> None:
        if not MATLAB_AVAILABLE:
            raise NotImplementedError(
                f"{RED}MATLAB isn't accessible to Python. To get up and running, "
                "take at look here:\n"
                "https://www.mathworks.com/help/matlab/matlab_external/"
                f"install-the-matlab-engine-for-python.html{END}"
            )

        sanity_check(
            ("shifts", shifts, sfuncs.check_float_list),
            ("pts", pts, sfuncs.check_int, (), {"min_value": 1}),
            ("sw", sw, sfuncs.check_float, (), {"greater_than_zero": True}),
            ("offset", offset, sfuncs.check_float),
            ("channel", channel, sfuncs.check_nucleus),
            ("field", field, sfuncs.check_float, (), {"greater_than_zero": True}),
            ("field_unit", field_unit, sfuncs.check_one_of, ("tesla", "MHz")),
            ("tau_c", tau_c, sfuncs.check_float, (), {"greater_than_zero": True}),
        )

        nspins = len(shifts)
        sanity_check(
            ("nuclei", nuclei, sfuncs.check_nucleus_list, (), {"length": nspins}, True),
            (
                "couplings", couplings, sfuncs.check_spinach_couplings, (nspins,),
                {}, True,
            ),
        )

        if nuclei is None:
            nuclei = nspins * [channel]

        with cd(SPINACHPATH):
            eng = matlab.engine.start_matlab()
            fid, sfo = eng.onedim_sim(
                field, field_unit, nuclei, shifts, couplings, tau_c, offset,
                sw, pts, channel, nargout=2,
            )

        fid = np.array(fid).flatten()

        expinfo = ExpInfo(
            dim=1,
            sw=sw,
            offset=offset,
            sfo=sfo,
            nuclei=channel,
            default_pts=fid.shape,
        )

        return cls(fid, expinfo)

    @classmethod
    def new_synthetic_from_parameters(
        cls,
        params: np.ndarray,
        pts: int,
        sw: float,
        offset: float = 0.0,
        sfo: Optional[float] = None,
        snr: float = 30.0,
    ) -> Estimator1D:
        """Generate an estimator instance from an array of oscillator parameters.

        Parameters
        ----------
        params
            Parameter array with the following structure:

              .. code:: python

                 params = numpy.array([
                    [a_1, φ_1, f_1, η_1],
                    [a_2, φ_2, f_2, η_2],
                    ...,
                    [a_m, φ_m, f_m, η_m],
                 ])

        pts
            The number of points the signal comprises.

        sw
            The sweep width of the signal (Hz).

        offset
            The transmitter offset (Hz).

        sfo
            The transmitter frequency (MHz).

        snr
            The signal-to-noise ratio. If ``None`` then no noise will be added
            to the FID.
        """
        sanity_check(
            ("params", params, sfuncs.check_ndarray, (), {"dim": 2, "shape": [(1, 4)]}),
            ("pts", pts, sfuncs.check_int, (), {"min_value": 1}),
            ("sw", sw, sfuncs.check_float, (), {"greater_than_zero": True}),
            ("offset", offset, sfuncs.check_float, (), {}, True),
            ("sfo", sfo, sfuncs.check_float, (), {"greater_than_zero": True}, True),
            ("snr", snr, sfuncs.check_float, (), {"greater_than_zero": True}, True),
        )

        expinfo = ExpInfo(
            dim=1,
            sw=sw,
            offset=offset,
            sfo=sfo,
            default_pts=pts,
        )

        data = expinfo.make_fid(params, snr=snr)
        return cls(data, expinfo)

    @classmethod
    def new_synthetic_from_simulation(
        cls,
        spin_system: SpinSystem,
        sw: float,
        offset: float,
        pts: int,
        freq_unit: str = "hz",
        channel: Union[str, Nucleus] = "1H",
        snr: Optional[float] = 30.0,
    ) -> Estimator1D:
        """Generate an estimator with data derived from a pulse-aquire experiment
        simulation.

        Simulations are performed using the
        `nmr_sims.experiments.pa.PulseAcquireSimulation
        <https://foroozandehgroup.github.io/nmr_sims/content/references/experiments/
        pa.html#nmr_sims.experiments.pa.PulseAcquireSimulation>`_
        class.

        Parameters
        ----------
        spin_system
            Specification of the spin system to run simulations on.
            `See here <https://foroozandehgroup.github.io/nmr_sims/content/
            references/spin_system.html#nmr_sims.spin_system.SpinSystem.__init__>`_
            for more details. **N.B. the transmitter frequency (sfo) will
            be determined by** ``spin_system.field``.

        sw
            The sweep width in Hz.

        offset
            The transmitter offset frequency in Hz.

        pts
            The number of points sampled.

        freq_unit
            The unit that ``sw`` and ``offset`` are expressed in. Should
            be either ``"hz"`` or ``"ppm"``.

        channel
            Nucleus targeted in the experiment simulation. ¹H is set as the default.
            `See here <https://foroozandehgroup.github.io/nmr_sims/content/
            references/nuclei.html>`__ for more information.

        snr
            The signal-to-noise ratio of the resulting signal, in decibels. ``None``
            produces a noiseless signal.
        """
        sanity_check(
            ("spin_system", spin_system, sfuncs.check_spin_system),
            ("sw", sw, sfuncs.check_float, (), {"greater_than_zero": True}),
            ("offset", offset, sfuncs.check_float),
            ("pts", pts, sfuncs.check_positive_int),
            ("freq_unit", freq_unit, sfuncs.check_one_of, ("hz", "ppm")),
            ("channel", channel, sfuncs.check_nmrsims_nucleus),
            ("snr", snr, sfuncs.check_float, (), {}, True),
        )

        sw = f"{sw}{freq_unit}"
        offset = f"{offset}{freq_unit}"
        sim = PulseAcquireSimulation(
            spin_system, pts, sw, offset=offset, channel=channel,
        )
        sim.simulate()
        _, data, _ = sim.fid()
        if snr is not None:
            data += sig._make_noise(data, snr)

        expinfo = ExpInfo(
            dim=1,
            sw=sim.sweep_widths[0],
            offset=sim.offsets[0],
            sfo=sim.sfo[0],
            nuclei=channel,
            default_pts=data.shape,
        )

        return cls(data, expinfo)

    @property
    def spectrum(self) -> np.ndarray:
        """Return the spectrum corresponding to ``self.data``"""
        data = copy.deepcopy(self.data)
        data[0] /= 2
        return sig.ft(data)

    def phase_data(
        self,
        p0: float = 0.0,
        p1: float = 0.0,
        pivot: int = 0,
    ) -> None:
        """Apply first-order phae correction to the estimator's data.

        Parameters
        ----------
        p0
            Zero-order phase correction, in radians.

        p1
            First-order phase correction, in radians.

        pivot
            Index of the pivot.
        """
        sanity_check(
            ("p0", p0, sfuncs.check_float),
            ("p1", p1, sfuncs.check_float),
            ("pivot", pivot, sfuncs.check_index, (self._data.size,)),
        )
        self._data = sig.phase(self._data, [p0], [p1], [pivot])

    def view_data(
        self,
        domain: str = "freq",
        components: str = "real",
        freq_unit: str = "hz",
    ) -> None:
        """View the data.

        Parameters
        ----------
        domain
            Must be ``"freq"`` or ``"time"``.

        components
            Must be ``"real"``, ``"imag"``, or ``"both"``.

        freq_unit
            Must be ``"hz"`` or ``"ppm"``.
        """
        sanity_check(
            ("domain", domain, sfuncs.check_one_of, ("freq", "time")),
            ("components", components, sfuncs.check_one_of, ("real", "imag", "both")),
            ("freq_unit", freq_unit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
        )

        fig = plt.figure()
        ax = fig.add_subplot()
        y = copy.deepcopy(self._data)

        if domain == "freq":
            x = self.get_shifts(unit=freq_unit)[0]
            y[0] /= 2
            y = sig.ft(y)
            label = f"$\\omega$ ({freq_unit.replace('h', 'H')})"
        elif domain == "time":
            x = self.get_timepoints()[0]
            label = "$t$ (s)"

        if components in ["real", "both"]:
            ax.plot(x, y.real, color="k")
        if components in ["imag", "both"]:
            ax.plot(x, y.imag, color="#808080")

        ax.set_xlabel(label)
        ax.set_xlim((x[0], x[-1]))

        plt.show()

    @logger
    def estimate(
        self,
        region: Optional[Tuple[float, float]] = None,
        noise_region: Optional[Tuple[float, float]] = None,
        region_unit: str = "hz",
        initial_guess: Optional[Union[np.ndarray, int]] = None,
        method: str = "gauss-newton",
        mode: str = "apfd",
        phase_variance: bool = True,
        max_iterations: Optional[int] = None,
        cut_ratio: Optional[float] = 1.1,
        mpm_trim: Optional[int] = 4096,
        nlp_trim: Optional[int] = None,
        fprint: bool = True,
        _log: bool = True,
    ) -> None:
        r"""Estimate a specified region of the signal.

        The basic steps that this method carries out are:

        * (Optional, but highly advised) Generate a frequency-filtered signal
          corresponding to the specified region.
        * (Optional) Generate an inital guess using the Matrix Pencil Method (MPM).
        * Apply numerical optimisation to determine a final estimate of the signal
          parameters

        Parameters
        ----------
        region
            The frequency range of interest. Should be of the form ``[left, right]``
            where ``left`` and ``right`` are the left and right bounds of the region
            of interest. If ``None``, the full signal will be considered, though
            for sufficently large and complex signals it is probable that poor and
            slow performance will be achieved.

        noise_region
            If ``region`` is not ``None``, this must be of the form ``[left, right]``
            too. This should specify a frequency range where no noticeable signals
            reside, i.e. only noise exists.

        region_unit
            One of ``"hz"`` or ``"ppm"`` Specifies the units that ``region``
            and ``noise_region`` have been given as.

        initial_guess
            If ``None``, an initial guess will be generated using the MPM,
            with the Minimum Descritpion Length being used to estimate the
            number of oscilltors present. If and int, the MPM will be used to
            compute the initial guess with the value given being the number of
            oscillators. If a NumPy array, this array will be used as the initial
            guess.

        method
            Specifies the optimisation method.

            * ``"exact"`` Uses SciPy's
              `trust-constr routine <https://docs.scipy.org/doc/scipy/reference/
              optimize.minimize-trustconstr.html\#optimize-minimize-trustconstr>`_
              The Hessian will be exact.
            * ``"gauss-newton"`` Uses SciPy's
              `trust-constr routine <https://docs.scipy.org/doc/scipy/reference/
              optimize.minimize-trustconstr.html\#optimize-minimize-trustconstr>`_
              The Hessian will be approximated based on the
              `Gauss-Newton method <https://en.wikipedia.org/wiki/
              Gauss%E2%80%93Newton_algorithm>`_
            * ``"lbfgs"`` Uses SciPy's
              `L-BFGS-B routine <https://docs.scipy.org/doc/scipy/reference/
              optimize.minimize-lbfgsb.html#optimize-minimize-lbfgsb>`_.

        mode
            A string containing a subset of the characters ``"a"`` (amplitudes),
            ``"p"`` (phases), ``"f"`` (frequencies), and ``"d"`` (damping factors).
            Specifies which types of parameters should be considered for optimisation.

        phase_variance
            Whether or not to include the variance of oscillator phases in the cost
            function. This should be set to ``True`` in cases where the signal being
            considered is derived from well-phased data.

        max_iterations
            A value specifiying the number of iterations the routine may run
            through before it is terminated. If ``None``, the default number
            of maximum iterations is set (``100`` if ``method`` is
            ``"exact"`` or ``"gauss-newton"``, and ``500`` if ``"method"`` is
            ``"lbfgs"``).

        mpm_trim
            Specifies the maximal size allowed for the filtered signal when
            undergoing the Matrix Pencil. If ``None``, no trimming is applied
            to the signal. If an int, and the filtered signal has a size
            greater than ``mpm_trim``, this signal will be set as
            ``signal[:mpm_trim]``.

        nlp_trim
            Specifies the maximal size allowed for the filtered signal when undergoing
            nonlinear programming. By default (``None``), no trimming is applied to
            the signal. If an int, and the filtered signal has a size greater than
            ``nlp_trim``, this signal will be set as ``signal[:nlp_trim]``.

        fprint
            Whether of not to output information to the terminal.

        _log
            Ignore this!
        """
        sanity_check(
            (
                "region_unit", region_unit, sfuncs.check_frequency_unit,
                (self.hz_ppm_valid,),
            ),
            (
                "initial_guess", initial_guess, sfuncs.check_initial_guess,
                (self.dim,), {}, True
            ),
            ("method", method, sfuncs.check_one_of, ("lbfgs", "gauss-newton", "exact")),
            ("phase_variance", phase_variance, sfuncs.check_bool),
            ("mode", mode, sfuncs.check_optimiser_mode),
            (
                "max_iterations", max_iterations, sfuncs.check_int, (),
                {"min_value": 1}, True,
            ),
            ("fprint", fprint, sfuncs.check_bool),
            ("mpm_trim", mpm_trim, sfuncs.check_int, (), {"min_value": 1}, True),
            ("nlp_trim", nlp_trim, sfuncs.check_int, (), {"min_value": 1}, True),
            (
                "cut_ratio", cut_ratio, sfuncs.check_float, (),
                {"greater_than_one": True}, True,
            ),
        )

        sanity_check(
            (
                "region", region, sfuncs.check_region,
                (self.sw(region_unit), self.offset(region_unit)), {}, True,
            ),
            (
                "noise_region", noise_region, sfuncs.check_region,
                (self.sw(region_unit), self.offset(region_unit)), {}, True,
            ),
        )

        if region is None:
            region = self.convert(((0, self._data.size - 1),), "idx->hz")
            noise_region = None
            mpm_signal = nlp_signal = self._data
            mpm_expinfo = nlp_expinfo = self.expinfo

        else:
            filt = Filter(
                self._data,
                self.expinfo,
                region,
                noise_region,
                region_unit=region_unit,
            )

            mpm_signal, mpm_expinfo = filt.get_filtered_fid(cut_ratio=cut_ratio)
            nlp_signal, nlp_expinfo = filt.get_filtered_fid(cut_ratio=None)
            region = filt.get_region()
            noise_region = filt.get_noise_region()

        if (mpm_trim is None) or (mpm_trim > mpm_signal.size):
            mpm_trim = mpm_signal.size
        if (nlp_trim is None) or (nlp_trim > nlp_signal.size):
            nlp_trim = nlp_signal.size

        if isinstance(initial_guess, np.ndarray):
            x0 = initial_guess
        else:
            oscillators = initial_guess if isinstance(initial_guess, int) else 0

            x0 = MatrixPencil(
                mpm_expinfo,
                mpm_signal[:mpm_trim],
                oscillators=oscillators,
                fprint=fprint,
            ).get_params()

            if x0 is None:
                return self._results.append(
                    Result(
                        np.array([[]]),
                        np.array([[]]),
                        region,
                        noise_region,
                        self.sfo,
                    )
                )

        result = NonlinearProgramming(
            nlp_expinfo,
            nlp_signal[:nlp_trim],
            x0,
            phase_variance=phase_variance,
            method=method,
            mode=mode,
            max_iterations=max_iterations,
            fprint=fprint,
        )

        self._results.append(
            Result(
                result.get_params(),
                result.get_errors(),
                region,
                noise_region,
                self.sfo,
            )
        )

    @logger
    def subband_estimate(
        self,
        noise_region: Tuple[float, float],
        noise_region_unit: str = "hz",
        nsubbands: Optional[int] = None,
        method: str = "gauss-newton",
        phase_variance: bool = True,
        max_iterations: Optional[int] = None,
        cut_ratio: Optional[float] = 1.1,
        mpm_trim: Optional[int] = 4096,
        nlp_trim: Optional[int] = None,
        fprint: bool = True,
        _log: bool = True,
    ) -> None:
        r"""Perform estiamtion on the entire signal via estimation of frequency-filtered
        sub-bands.

        This method splits the signal up into ``nsubbands`` equally-sized region
        and extracts parameters from each region before finally concatenating all
        the results together.

        Parameters
        ----------
        noise_region
            Specifies a frequency range where no noticeable signals reside, i.e. only
            noise exists.

        noise_region_unit
            One of ``"hz"`` or ``"ppm"``. Specifies the units that ``noise_region``
            have been given in.

        nsubbands
            The number of sub-bands to break the signal into. If ``None``, the number
            will be set as the nearest integer to the data size divided by 500.

        method
            Specifies the optimisation method.

            * ``"exact"`` Uses SciPy's
              `trust-constr routine <https://docs.scipy.org/doc/scipy/reference/
              optimize.minimize-trustconstr.html\#optimize-minimize-trustconstr>`_
              The Hessian will be exact.
            * ``"gauss-newton"`` Uses SciPy's
              `trust-constr routine <https://docs.scipy.org/doc/scipy/reference/
              optimize.minimize-trustconstr.html\#optimize-minimize-trustconstr>`_
              The Hessian will be approximated based on the
              `Gauss-Newton method <https://en.wikipedia.org/wiki/
              Gauss%E2%80%93Newton_algorithm>`_
            * ``"lbfgs"`` Uses SciPy's
              `L-BFGS-B routine <https://docs.scipy.org/doc/scipy/reference/
              optimize.minimize-lbfgsb.html#optimize-minimize-lbfgsb>`_.

        phase_variance
            Whether or not to include the variance of oscillator phases in the cost
            function. This should be set to ``True`` in cases where the signal being
            considered is derived from well-phased data.

        max_iterations
            A value specifiying the number of iterations the routine may run
            through before it is terminated. If ``None``, the default number
            of maximum iterations is set (``100`` if ``method`` is
            ``"exact"`` or ``"gauss-newton"``, and ``500`` if ``"method"`` is
            ``"lbfgs"``).

        mpm_trim
            Specifies the maximal size allowed for the filtered signal when
            undergoing the Matrix Pencil. If ``None``, no trimming is applied
            to the signal. If an int, and the filtered signal has a size
            greater than ``mpm_trim``, this signal will be set as
            ``signal[:mpm_trim]``.

        nlp_trim
            Specifies the maximal size allowed for the filtered signal when undergoing
            nonlinear programming. By default (``None``), no trimming is applied to
            the signal. If an int, and the filtered signal has a size greater than
            ``nlp_trim``, this signal will be set as ``signal[:nlp_trim]``.

        fprint
            Whether of not to output information to the terminal.

        _log
            Ignore this!
        """
        sanity_check(
            (
                "noise_region_unit", noise_region_unit, sfuncs.check_frequency_unit,
                (self.hz_ppm_valid,),
            ),
            ("nsubbands", nsubbands, sfuncs.check_int, (), {"min_value": 1}, True),
            ("method", method, sfuncs.check_one_of, ("lbfgs", "gauss-newton", "exact")),
            ("phase_variance", phase_variance, sfuncs.check_bool),
            (
                "max_iterations", max_iterations, sfuncs.check_int, (),
                {"min_value": 1}, True,
            ),
            ("fprint", fprint, sfuncs.check_bool),
            ("mpm_trim", mpm_trim, sfuncs.check_int, (), {"min_value": 1}, True),
            ("nlp_trim", nlp_trim, sfuncs.check_int, (), {"min_value": 1}, True),
            (
                "cut_ratio", cut_ratio, sfuncs.check_float, (),
                {"greater_than_one": True}, True,
            ),
        )

        sanity_check(
            (
                "noise_region", noise_region, sfuncs.check_region,
                (self.sw(noise_region_unit), self.offset(noise_region_unit)), {}, True,
            ),
        )

        kwargs = {
            "method": method,
            "phase_variance": phase_variance,
            "max_iterations": max_iterations,
            "cut_ratio": cut_ratio,
            "mpm_trim": mpm_trim,
            "nlp_trim": nlp_trim,
            "fprint": fprint,
        }

        self._subband_estimate(nsubbands, noise_region, noise_region_unit, **kwargs)

    def make_fid(
        self,
        indices: Optional[Iterable[int]] = None,
        pts: Optional[Iterable[int]] = None,
    ) -> np.ndarray:
        r"""Construct a noiseless FID from estimation result parameters.

        Parameters
        ----------
        indices
            The indices of results to extract errors from. Index ``0`` corresponds to
            the first result obtained using the estimator, ``1`` corresponds to
            the next, etc.  If ``None``, all results will be used.

        pts
            The number of points to construct the time-points with in each dimesnion.
            If ``None``, and ``self.default_pts`` is a tuple of ints, it will be
            used.
        """
        sanity_check(
            (
                "indices", indices, sfuncs.check_int_list, (),
                {"max_value": len(self._results) - 1}, True,
            ),
            (
                "pts", pts, sfuncs.check_int_list, (),
                {
                    "length": self.dim,
                    "len_one_can_be_listless": True,
                    "min_value": 1,
                },
                True,
            ),
        )

        return super().make_fid(indices, pts=pts)

    def write_to_topspin(
        self,
        path: Union[str, Path],
        expno: int,
        force_overwrite: bool = False,
        indices: Optional[Iterable[int]] = None,
        pts: Optional[Iterable[int]] = None,
    ) -> None:
        res_len = len(self._results)
        sanity_check(
            ("expno", expno, sfuncs.check_int, (), {"min_value": 1}),
            ("force_overwrite", force_overwrite, sfuncs.check_bool),
            (
                "indices", indices, sfuncs.check_int_list, (),
                {"min_value": -res_len, "max_value": res_len - 1}, True,
            ),
            (
                "pts", pts, sfuncs.check_int_list, (),
                {
                    "length": self.dim,
                    "len_one_can_be_listless": True,
                    "min_value": 1,
                },
                True,
            ),
        )

        fid = self.make_fid(indices, pts)
        fid_uncomplex = np.zeros((2 * fid.size,), dtype="float64")
        fid_uncomplex[::2] = fid.real
        fid_uncomplex[1::2] = fid.imag

        with open(NMRESPYPATH / "ts_templates/acqus", "r") as fh:
            text = fh.read()

        int_regex = r"-?\d+"
        float_regex = r"-?\d+(\.\d+)?"
        text = re.sub(
            r"\$BF1= " + float_regex,
            "$BF1= " +
            str(self.bf[0] if self.bf is not None else 500. - 1e-6 * self.offset()[0]),
            text,
        )
        text = re.sub(r"\$BYTORDA= " + int_regex, "$BYTORDA= 0", text)
        text = re.sub(r"\$DTYPA= " + int_regex, "$DTYPA= 2", text)
        text = re.sub(r"\$GRPDLY= " + float_regex, "$GRPDLY= 0", text)
        text = re.sub(
            r"\$NUC1= <\d+[a-zA-Z]+>",
            "$NUC1= <" +
            (self.nuclei[0] if self.nuclei is not None else "1H") +
            ">",
            text,
        )
        text = re.sub(r"\$O1= " + float_regex, f"$O1= {self.offset()[0]}", text)
        text = re.sub(
            r"\$SFO1= " + float_regex,
            "$SFO1= " +
            str(self.sfo[0] if self.sfo is not None else 500.0),
            text,
        )
        text = re.sub(
            r"\$SW= " + float_regex,
            "$SW= " +
            str(self.sw(unit="ppm")[0] if self.hz_ppm_valid else self.sw()[0] / 500.0),
            text,
        )
        text = re.sub(r"\$SW_h= " + float_regex, f"$SW_h= {self.sw()[0]}", text)
        text = re.sub(r"\$TD= " + int_regex, f"$TD= {fid.size}", text)

        path = Path(path).expanduser()
        if not path.is_dir():
            path.mkdir()
        if (expdir := path / str(expno)).is_dir():
            shutil.rmtree(expdir)
        expdir.mkdir()

        with open(expdir / "acqus", "w") as fh:
            fh.write(text)
        with open(expdir / "acqu", "w") as fh:
            fh.write(text)

        with open(expdir / "fid", "wb") as fh:
            fh.write(fid_uncomplex.astype("<f8").tobytes())

    @logger
    def plot_result(
        self,
        indices: Optional[Iterable[int]] = None,
        *,
        plot_residual: bool = True,
        plot_model: bool = False,
        residual_shift: Optional[Iterable[float]] = None,
        model_shift: Optional[float] = None,
        shifts_unit: str = "ppm",
        data_color: Any = "#000000",
        residual_color: Any = "#808080",
        model_color: Any = "#808080",
        oscillator_colors: Optional[Any] = None,
        show_labels: bool = False,
        stylesheet: Optional[Union[str, Path]] = None,
    ) -> Iterable[ResultPlotter]:
        """Write estimation results to text and PDF files.

        Parameters
        ----------
        indices
            The indices of results to include. Index ``0`` corresponds to the first
            result obtained using the estimator, ``1`` corresponds to the next, etc.
            If ``None``, all results will be included.

        plot_model
            If ``True``, plot the model generated using ``result``. This model is
            a summation of all oscillator present in the result.

        plot_residual
            If ``True``, plot the difference between the data and the model
            generated using ``result``.

        residual_shift
            Specifies a translation of the residual plot along the y-axis. If
            ``None``, a default shift will be applied.

        model_shift
            Specifies a translation of the residual plot along the y-axis. If
            ``None``, a default shift will be applied.

        shifts_unit
            Units to display chemical shifts in. Must be either ``'ppm'`` or
            ``'hz'``.

        data_color
            The colour used to plot the data. Any value that is recognised by
            matplotlib as a color is permitted. See `here
            <https://matplotlib.org/stable/tutorials/colors/colors.html>`_ for
            a full description of valid values.

        residual_color
            # The colour used to plot the residual. See ``data_color`` for a
            # description of valid colors.

        model_color
            The colour used to plot the model. See ``data_color`` for a
            description of valid colors.

        oscillator_colors
            Describes how to color individual oscillators. The following
            is a complete list of options:

            * If a valid matplotlib color is given, all oscillators will
              be given this color.
            * If a string corresponding to a matplotlib colormap is given,
              the oscillators will be consecutively shaded by linear increments
              of this colormap. For all valid colormaps, see
              `here <https://matplotlib.org/stable/tutorials/colors/\
              colormaps.html>`__
            * If an iterable object containing valid matplotlib colors is
              given, these colors will be cycled.
              For example, if ``oscillator_colors = ['r', 'g', 'b']``:

              + Oscillators 1, 4, 7, ... would be :red:`red (#FF0000)`
              + Oscillators 2, 5, 8, ... would be :green:`green (#008000)`
              + Oscillators 3, 6, 9, ... would be :blue:`blue (#0000FF)`

            * If ``None``, the default colouring method will be applied, which
              involves cycling through the following colors:

                - :oscblue:`#1063E0`
                - :oscorange:`#EB9310`
                - :oscgreen:`#2BB539`
                - :oscred:`#D4200C`

        show_labels
            If ``True``, each oscillator will be given a numerical label
            in the plot, if ``False``, the labels will be hidden.

        stylesheet
            The name of/path to a matplotlib stylesheet for further
            customaisation of the plot. See `here <https://matplotlib.org/\
            stable/tutorials/introductory/customizing.html>`__ for more
            information on stylesheets.
        """
        self._check_results_exist()
        sanity_check(
            (
                "indices", indices, sfuncs.check_int_list, (),
                {
                    "must_be_positive": True,
                    "max_value": len(self._results) - 1,
                },
                True,
            ),
            ("plot_residual", plot_residual, sfuncs.check_bool),
            ("plot_model", plot_model, sfuncs.check_bool),
            ("residual_shift", residual_shift, sfuncs.check_float, (), {}, True),
            ("model_shift", model_shift, sfuncs.check_float, (), {}, True),
            (
                "shifts_unit", shifts_unit, sfuncs.check_frequency_unit,
                (self.hz_ppm_valid,),
            ),
            ("data_color", data_color, sfuncs.check_mpl_color),
            ("residual_color", residual_color, sfuncs.check_mpl_color),
            ("model_color", model_color, sfuncs.check_mpl_color),
            (
                "oscillator_colors", oscillator_colors, sfuncs.check_oscillator_colors,
                (), {}, True,
            ),
            ("show_labels", show_labels, sfuncs.check_bool),
            ("stylesheet", stylesheet, sfuncs.check_str, (), {}, True),
        )
        results = self.get_results(indices)

        expinfo = ExpInfo(
            1,
            sw=self.sw(),
            offset=self.offset(),
            sfo=self.sfo,
            nuclei=self.nuclei,
            default_pts=self.default_pts,
        )

        return [
            ResultPlotter(
                self._data,
                result.get_params(funit="hz"),
                expinfo,
                region=result.get_region(unit=shifts_unit),
                shifts_unit=shifts_unit,
                plot_residual=plot_residual,
                plot_model=plot_model,
                residual_shift=residual_shift,
                model_shift=model_shift,
                data_color=data_color,
                residual_color=residual_color,
                model_color=model_color,
                oscillator_colors=oscillator_colors,
                show_labels=show_labels,
                stylesheet=stylesheet,
            )
            for result in results
        ]
