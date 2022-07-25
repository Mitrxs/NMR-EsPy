# jres.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Thu 21 Jul 2022 11:44:45 BST

from __future__ import annotations
import copy
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import numpy as np
import matplotlib.pyplot as plt

from nmr_sims.experiments.jres import JresSimulation
from nmr_sims.nuclei import Nucleus
from nmr_sims.spin_system import SpinSystem

from nmrespy import ExpInfo, sig
from nmrespy._sanity import (
    sanity_check,
    funcs as sfuncs,
)
from nmrespy.estimators import logger, Estimator, Result
from nmrespy.freqfilter import Filter
from nmrespy.mpm import MatrixPencil
from nmrespy.nlp import NonlinearProgramming


class Estimator2DJ(Estimator):
    def __init__(
        self, data: np.ndarray, expinfo: ExpInfo, datapath: Optional[Path] = None,
    ) -> None:
        super().__init__(data, expinfo, datapath)

    @classmethod
    def new_bruker(cls):
        pass

    @classmethod
    def new_synthetic_from_simulation(
        cls,
        spin_system: SpinSystem,
        sweep_widths: Tuple[float, float],
        offset: float,
        pts: Tuple[int, int],
        channel: Union[str, Nucleus] = "1H",
        f2_unit: str = "ppm",
        snr: Optional[float] = 30.0,
        lb: Optional[Tuple[float, float]] = None,
    ) -> Estimator2DJ:
        """Generate an estimator with data derived from a J-resolved experiment
        simulation.

        Simulations are performed using
        `nmr_sims.experiments.jres.JresEstimator
        <https://foroozandehgroup.github.io/nmr_sims/content/references/experiments/
        pa.html#nmr_sims.experiments.jres.JresEstimator>`_.

        Parameters
        ----------
        spin_system
            Specification of the spin system to run simulations on. `See here
            <https://foroozandehgroup.github.io/nmr_sims/content/references/
            spin_system.html#nmr_sims.spin_system.SpinSystem.__init__>`_
            for more details.

        sweep_widths
            The sweep width in each dimension. The first element, corresponding
            to F1, should be in Hz. The second element, corresponding to F2,
            should be expressed in the unit which corresponds to ``f2_unit``.

        offset
            The transmitter offset. The value's unit should correspond with
            ``f2_unit``.

        pts
            The number of points sampled in each dimension.

        channel
            Nucleus targeted in the experiment simulation. ¹H is set as the default.
            `See here <https://foroozandehgroup.github.io/nmr_sims/content/
            references/nuclei.html>`__ for more information.

        f2_unit
            The unit that the sweep width and transmitter offset in F2 are given in.
            Should be either ``"ppm"`` (default) or ``"hz"``.

        snr
            The signal-to-noise ratio of the resulting signal, in decibels. ``None``
            produces a noiseless signal.

        lb
            The damping (line-broadening) factor applied to the simulated FID.
            By default, this will be set to ensure that the final point in each
            dimension in scaled to be 1/1000 of it's un-damped value.
        """
        sanity_check(
            ("spin_system", spin_system, sfuncs.check_spin_system),
            (
                "sweep_widths", sweep_widths, sfuncs.check_float_list, (),
                {"length": 2, "must_be_positive": True},
            ),
            ("offset", offset, sfuncs.check_float),
            (
                "pts", pts, sfuncs.check_int_list, (),
                {"length": 2, "must_be_positive": True},
            ),
            ("channel", channel, sfuncs.check_nmrsims_nucleus),
            ("f2_unit", f2_unit, sfuncs.check_frequency_unit, (True,)),
            ("snr", snr, sfuncs.check_float, (), {}, True),
            (
                "lb", lb, sfuncs.check_float_list, (),
                {"length": 2, "must_be_positive": True}, True,
            ),
        )

        sweep_widths = [f"{sweep_widths[0]}hz", f"{sweep_widths[1]}{f2_unit}"]
        offset = f"{offset}{f2_unit}"

        sim = JresSimulation(spin_system, pts, sweep_widths, offset, channel)
        sim.simulate()
        _, data, _ = sim.fid(lb=lb)

        if snr is not None:
            data += sig._make_noise(data, snr)

        expinfo = ExpInfo(
            dim=2,
            sw=sim.sweep_widths,
            offset=[0.0, sim.offsets[0]],
            sfo=[None, sim.sfo[0]],
            nuclei=[None, sim.channels[0].name],
            default_pts=data.shape,
            fn_mode="QF",
        )
        return cls(data, expinfo, None)

    def view_data(
        self,
        domain: str = "freq",
        components: str = "real",
        freq_unit: str = "hz",
        abs_: bool = False,
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

        abs_
            Whether or not to display frequency-domain data in absolute-value mode.
        """
        sanity_check(
            ("domain", domain, sfuncs.check_one_of, ("freq", "time")),
            ("components", components, sfuncs.check_one_of, ("real", "imag", "both")),
            ("freq_unit", freq_unit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
            ("abs_", abs_, sfuncs.check_bool),
        )

        fig = plt.figure()
        ax = fig.add_subplot(projection="3d")
        z = copy.deepcopy(self._data)

        if domain == "freq":
            x, y = self.get_shifts(unit=freq_unit)
            z[0, 0] /= 2
            z = sig.ft(z)

            if abs_:
                z = np.abs(z)

            if self.nuclei is None:
                pass
            else:
                freq_units = ("Hz", freq_unit.replace("h", "H"))
                nuclei = [
                    nuc if nuc is not None else "$\\omega$"
                    for nuc in self.latex_nuclei
                ]
                xlabel, ylabel = [
                    f"{nuc} ({fu})" for nuc, fu in zip(nuclei, freq_units)

                ]
        elif domain == "time":
            x, y = self.get_timepoints()
            xlabel, ylabel = [f"$t_{i}$ (s)" for i in range(1, 3)]

        if components in ("real", "both"):
            ax.plot_wireframe(
                x, y, z.real, color="k", lw=0.2, rstride=1, cstride=1,
            )
        if components in ("imag", "both"):
            ax.plot_wireframe(
                x, y, z.imag, color="#808080", lw=0.2, rstride=1, cstride=1,
            )

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_xlim(reversed(ax.get_xlim()))
        ax.set_ylim(reversed(ax.get_ylim()))
        ax.set_zticks([])

        plt.show()

    @logger
    def estimate(
        self,
        region: Optional[Tuple[Union[int, float], Union[int, float]]] = None,
        noise_region: Optional[Tuple[Union[int, float], Union[int, float]]] = None,
        region_unit: str = "ppm",
        initial_guess: Optional[Union[np.ndarray, int]] = None,
        method: str = "gauss-newton",
        phase_variance: bool = True,
        max_iterations: Optional[int] = None,
        cut_ratio: Optional[float] = 1.1,
        mpm_trim: Optional[int] = 256,
        nlp_trim: Optional[int] = 1024,
        fprint: bool = True,
        _log: bool = True,
    ):
        r"""Estimate a specified region in F2.

        The basic steps that this method carries out are:

        * (Optional, but highly advised) Generate a frequency-filtered signal
          corresponding to the specified region.
        * (Optional) Generate an inital guess using the Matrix Pencil Method (MPM).
        * Apply numerical optimisation to determine a final estimate of the signal
          parameters

        Parameters
        ----------
        region
            The frequency range of interest in F2. Should be of the form
            ``(left, right)`` where ``left`` and ``right`` are the left and right
            bounds of the region of interest. If ``None``, the full signal will be
            considered, though for sufficently large and complex signals it is
            probable that poor and slow performance will be realised.

        noise_region
            If ``region`` is not ``None``, this must be of the form ``(left, right)``
            too. This should specify a frequency range in F2 where no noticeable
            signals reside, i.e. only noise exists.

        region_unit
            One of ``"hz"`` or ``"ppm"``. Specifies the units that ``region`` and
            ``noise_region`` have been given as.

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
            Specifies the maximal size in the direct dimension allowed for the
            filtered signal when undergoing the Matrix Pencil. If ``None``, no
            trimming is applied to the signal. If an int, and the direct
            dimension filtered signal has a size greater than ``mpm_trim``,
            this signal will be set as ``signal[:, :mpm_trim]``.

        nlp_trim
            Specifies the maximal size allowed in the direct dimension for the
            filtered signal when undergoing nonlinear programming. By default
            (``None``), no trimming is applied to the signal. If an int, and
            the direct dimension filtered signal has a size greater than
            ``nlp_trim``, this signal will be set as ``signal[:, :nlp_trim]``.

        fprint
            Whether of not to output information to the terminal.

        _log
            Ignore this!
        """
        sanity_check(
            (
                "region_unit", region_unit, sfuncs.check_frequency_unit,
                (self.hz_ppm_valid,)
            ),
            (
                "initial_guess", initial_guess, sfuncs.check_initial_guess,
                (self.dim,), {}, True
            ),
            ("method", method, sfuncs.check_one_of, ("gauss-newton", "exact", "lbfgs")),
            ("phase_variance", phase_variance, sfuncs.check_bool),
            (
                "max_iterations", max_iterations, sfuncs.check_int, (),
                {"min_value": 1}, True,
            ),
            (
                "cut_ratio", cut_ratio, sfuncs.check_float, (),
                {"greater_than_one": True}, True,
            ),
            ("mpm_trim", mpm_trim, sfuncs.check_int, (), {"min_value": 1}, True),
            ("nlp_trim", nlp_trim, sfuncs.check_int, (), {"min_value": 1}, True),
            ("fprint", fprint, sfuncs.check_bool),
        )

        sanity_check(
            (
                "region", region, sfuncs.check_region,
                (
                    (self.sw(region_unit)[1],),
                    (self.offset(region_unit)[1],),
                ), {}, True,
            ),
            (
                "noise_region", noise_region, sfuncs.check_region,
                (
                    (self.sw(region_unit)[1],),
                    (self.offset(region_unit)[1],),
                ), {}, True,
            ),
        )

        if region is None:
            region = self.convert(
                ((0, self._data.shape[0] - 1), (0, self._data.shape[1] - 1)),
                "idx->hz",
            )
            noise_region = None
            mpm_signal = nlp_signal = self._data
            mpm_expinfo = nlp_expinfo = self.expinfo

        else:
            region = (None, region)
            noise_region = (None, noise_region)

            filt = Filter(
                self._data,
                self.expinfo,
                region,
                noise_region,
                region_unit=region_unit,
                twodim_dtype="jres",
            )

            mpm_signal, mpm_expinfo = filt.get_filtered_fid(cut_ratio=cut_ratio)
            nlp_signal, nlp_expinfo = filt.get_filtered_fid(cut_ratio=None)
            region = filt.get_region()
            noise_region = filt.get_noise_region()

        if (mpm_trim is None) or (mpm_trim > mpm_signal.shape[1]):
            mpm_trim = mpm_signal.shape[1]
        if (nlp_trim is None) or (nlp_trim > nlp_signal.shape[1]):
            nlp_trim = nlp_signal.shape[1]

        if isinstance(initial_guess, np.ndarray):
            x0 = initial_guess
        else:
            oscillators = initial_guess if isinstance(initial_guess, int) else 0
            x0 = MatrixPencil(
                mpm_expinfo,
                mpm_signal[:, :mpm_trim],
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
            nlp_signal[:, :nlp_trim],
            x0,
            phase_variance=phase_variance,
            method=method,
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

    def subband_estimate(
        self,
        noise_region: Tuple[float, float],
        noise_region_unit: str = "hz",
        nsubbands: Optional[int] = None,
        method: str = "gauss-newton",
        phase_variance: bool = True,
        max_iterations: Optional[int] = None,
        cut_ratio: Optional[float] = 1.1,
        mpm_trim: Optional[int] = 128,
        nlp_trim: Optional[int] = 256,
        fprint: bool = True,
        _log: bool = True,
    ) -> None:
        r"""Perform estiamtion on the entire signal via estimation of
        frequency-filtered sub-bands.

        This method splits the signal up into ``nsubbands`` equally-sized regions
        in the direct dimension and extracts parameters from each region before
        finally concatenating all the results together.

        Parameters
        ----------
        noise_region
            Specifies a direct dimension frequency range where no noticeable
            signals reside, i.e. only noise exists.

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
            Specifies the maximal size in the direct dimension allowed for the
            filtered signal when undergoing the Matrix Pencil. If ``None``, no
            trimming is applied to the signal. If an int, and the filtered
            signal has a direct dimension size greater than ``mpm_trim``, this
            signal will be set as ``signal[:, :mpm_trim]``.

        nlp_trim
            Specifies the maximal size allowed in the direct dimension for the
            filtered signal when undergoing nonlinear programming. If ``None``,
            no trimming is applied to the signal. If an int, and the filtered
            signal has a direct dimension size greater than ``nlp_trim``, this
            signal will be set as ``signal[:, :nlp_trim]``.

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
                (
                    (self.sw(noise_region_unit)[1],),
                    (self.offset(noise_region_unit)[1],),
                ), {}, True,
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

    def negative_45_signal(
        self,
        indices: Optional[Iterable[int]] = None,
        pts: Optional[int] = None,
    ) -> np.ndarray:
        r"""Generate the synthetic signal :math:`y_{-45^{\circ}}(t)`, where
        :math:`t \geq 0`:

        .. math::

            y_{-45^{\circ}}(t) = \sum_{m=1}^M a_m \exp\left( \mathrm{i} \phi_m \right)
            \exp\left( 2 \mathrm{i} \pi f_{1,m} t \right)
            \exp\left( -t \left[2 \mathrm{i} \pi f_{2,m} + \eta_{2,m} \right] \right)

        .. image:: https://raw.githubusercontent.com/foroozandehgroup/NMR-EsPy/2dj/nmrespy/images/neg_45.png  # noqa: E501

        Producing this signal from parameters derived from estimation of a 2DJ dataset
        should generate a 1D homodecoupled spectrum.

        Parameters
        ----------
        indices
            The indices of results to include. Index ``0`` corresponds to the first
            result obtained using the estimator, ``1`` corresponds to the next, etc.
            If ``None``, all results will be included.

        pts
            The number of points to construct the signal from. If ``None``,
            ``self.default_pts`` will be used.
        """
        sanity_check(
            (
                "indices", indices, sfuncs.check_int_list, (),
                {
                    "len_one_can_be_listless": True,
                    "min_value": -len(self._results),
                    "max_value": len(self._results) - 1,
                },
                True,

            ),
            ("pts", pts, sfuncs.check_int, (), {"min_value": 1}, True),
        )

        params = self.get_params(indices)
        offset = self.offset()[1]

        if pts is None:
            pts = self.default_pts[1]
        tp = self.get_timepoints(pts=(1, pts), meshgrid=False)[1]

        signal = np.einsum(
            "ij,j->i",
            np.exp(
                np.outer(
                    tp,
                    2j * np.pi * (params[:, 3] - params[:, 2] - offset) - params[:, 5],
                )
            ),
            params[:, 0] * np.exp(1j * params[:, 1])
        )

        return signal

    def sheared_signal(
        self,
        indices: Optional[Iterable[int]] = None,
        pts: Optional[Tuple[int, int]] = None,
        indirect_modulation: Optional[str] = None,
    ) -> np.ndarray:
        r"""Return an FID where direct dimension frequencies are perturbed such that:

        .. math::

            f_{2, m} = f_{2, m} - f_{1, m}\ \forall\ m \in \{1, \cdots, M\}

        This should yeild a signal where all components in a multiplet are centered
        at the spin's chemical shift in the direct dimenion, akin to "shearing" 2DJ
        data.

        Parameters
        ----------
        indices
            The indices of results to include. Index ``0`` corresponds to the first
            result obtained using the estimator, ``1`` corresponds to the next, etc.
            If ``None``, all results will be included.

        pts
            The number of points to construct the signal from. If ``None``,
            ``self.default_pts`` will be used.

        indirect_modulation
            Acquisition mode in indirect dimension of a 2D experiment. If the
            data is not 1-dimensional, this should be one of:

            * ``None`` - :math:`y \left(t_1, t_2\right) = \sum_{m} a_m
              e^{\mathrm{i} \phi_m}
              e^{\left(2 \pi \mathrm{i} f_{1, m} - \eta_{1, m}\right) t_1}
              e^{\left(2 \pi \mathrm{i} f_{2, m} - \eta_{2, m}\right) t_2}`
            * ``"amp"`` - amplitude modulated pair:
              :math:`y_{\mathrm{cos}} \left(t_1, t_2\right) = \sum_{m} a_m
              e^{\mathrm{i} \phi_m}
              \cos\left(\left(2 \pi \mathrm{i} f_{1, m} - \eta_{1, m}\right) t_1\right)
              e^{\left(2 \pi \mathrm{i} f_{2, m} - \eta_{2, m}\right) t_2}`
              :math:`y_{\mathrm{sin}} \left(t_1, t_2\right) = \sum_{m} a_m
              e^{\mathrm{i} \phi_m}
              \sin\left(\left(2 \pi \mathrm{i} f_{1, m} - \eta_{1, m}\right) t_1\right)
              e^{\left(2 \pi \mathrm{i} f_{2, m} - \eta_{2, m}\right) t_2}`
            * ``"phase"`` - phase-modulated pair:
              :math:`y_{\mathrm{P}} \left(t_1, t_2\right) = \sum_{m} a_m
              e^{\mathrm{i} \phi_m}
              e^{\left(2 \pi \mathrm{i} f_{1, m} - \eta_{1, m}\right) t_1}
              e^{\left(2 \pi \mathrm{i} f_{2, m} - \eta_{2, m}\right) t_2}`
              :math:`y_{\mathrm{N}} \left(t_1, t_2\right) = \sum_{m} a_m
              e^{\mathrm{i} \phi_m}
              e^{\left(-2 \pi \mathrm{i} f_{1, m} - \eta_{1, m}\right) t_1}
              e^{\left(2 \pi \mathrm{i} f_{2, m} - \eta_{2, m}\right) t_2}`

            ``None`` will lead to an array of shape ``(*pts)``. ``amp`` and ``phase``
            will lead to an array of shape ``(2, *pts)``.
        """
        sanity_check(
            (
                "indices", indices, sfuncs.check_index,
                (len(self._results),), {}, True,
            ),
            ("pts", pts, sfuncs.check_int, (), {"min_value": 1}, True),
        )

        edited_params = copy.deepcopy(self.get_params(indices))
        edited_params[:, 3] -= edited_params[:, 2]

        return super(Estimator, self).make_fid(
            edited_params, pts=pts, indirect_modulation=indirect_modulation,
        )

    def phase_data(self):
        pass

    def plot_result(self):
        pass
