# __init__.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Wed 11 May 2022 16:43:02 BST

from __future__ import annotations
import abc
import datetime
import functools
from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import numpy as np

from nmrespy import ExpInfo
from nmrespy._colors import RED, END, USE_COLORAMA
from nmrespy._files import (
    check_saveable_path,
    check_existent_path,
    configure_path,
    open_file,
    save_file,
)
from nmrespy._result_fetcher import ResultFetcher
from nmrespy._sanity import sanity_check, funcs as sfuncs

if USE_COLORAMA:
    import colorama
    colorama.init()


def logger(f: callable):
    @functools.wraps(f)
    def inner(*args, **kwargs):
        class_instance = args[0]
        if "_log" in kwargs:
            if not kwargs["_log"]:
                return f(*args, **kwargs)
            else:
                del kwargs["_log"]
        class_instance._log += f"--> `{f.__name__}` {args[1:]} {kwargs}\n"
        return f(*args, **kwargs)
    return inner


class Estimator(ExpInfo, metaclass=abc.ABCMeta):
    """Base estimation class."""

    def __init__(
        self,
        data: np.ndarray,
        expinfo: ExpInfo,
        datapath: Optional[Path] = None,
    ) -> None:
        """Initialise a class instance.

        Parameters
        ----------
        data
            The data associated with the binary file in `path`.

        datapath
            The path to the directory containing the NMR data.

        expinfo
            Experiment information.
        """
        self._data = data
        self._datapath = datapath

        super().__init__(
            dim=self._data.ndim,
            sw=expinfo.sw(),
            offset=expinfo.offset(),
            sfo=expinfo.sfo,
            nuclei=expinfo.nuclei,
            default_pts=self._data.shape,
            fn_mode=expinfo.fn_mode,
        )

        self._results = []
        now = datetime.datetime.now().strftime('%d-%m-%y %H:%M:%S')
        self._log = (
            "=====================\n"
            "Logfile for Estimator\n"
            "=====================\n"
            f"--> Created @ {now}\n"
        )

    @property
    def data(self) -> np.ndarray:
        """Return the data assocaited with the estimator."""
        return self._data

    @abc.abstractmethod
    def phase_data(*args, **kwargs):
        pass

    def get_log(self) -> str:
        """Get the log for the estimator instance."""
        return self._log

    def save_log(
        self,
        path: Union[str, Path] = "./espy_logfile",
        force_overwrite: bool = False,
        fprint: bool = True,
    ) -> None:
        """Save the estimator's log.

        Parameters
        ----------
        path
            The path to save the log to.

        force_overwrite
            If ``path`` already exists, ``force_overwrite`` set to ``True`` will get
            the user to confirm whether they are happy to overwrite the file.
            If ``False``, the file will be overwritten without prompt.

        fprint
            Specifies whether or not to print infomation to the terminal.
        """
        sanity_check(
            ("force_overwrite", force_overwrite, sfuncs.check_bool),
            ("fprint", fprint, sfuncs.check_bool),
        )
        sanity_check(
            ("path", path, check_saveable_path, ("log", force_overwrite)),
        )

        path = configure_path(path, "log")
        save_file(self._log, path, fprint=fprint)

    @classmethod
    @abc.abstractmethod
    def new_bruker(*args, **kwargs):
        pass

    @classmethod
    @abc.abstractmethod
    def new_synthetic_from_simulation(*args, **kwargs):
        pass

    @abc.abstractmethod
    def view_data(*args, **kwargs):
        pass

    @logger
    def to_pickle(
        self,
        path: Optional[Union[Path, str]] = None,
        force_overwrite: bool = False,
        fprint: bool = True,
    ) -> None:
        """Save the estimator to a byte stream using Python's pickling protocol.

        Parameters
        ----------
        path
            Path of file to save the byte stream to. `'.pkl'` is added to the end of
            the path if this is not given by the user. If ``None``,
            ``./estimator_<x>.pkl`` will be used, where ``<x>`` is the first number
            that doesn't cause a clash with an already existent file.

        force_overwrite
            Defines behaviour if the specified path already exists:

            * If ``force_overwrite`` is set to ``False``, the user will be prompted
              if they are happy overwriting the current file.
            * If ``force_overwrite`` is set to ``True``, the current file will be
              overwritten without prompt.

        fprint
            Specifies whether or not to print infomation to the terminal.

        See Also
        --------

        :py:meth:`Estimator.from_pickle`
        """
        sanity_check(
            ("force_overwrite", force_overwrite, sfuncs.check_bool),
            ("fprint", fprint, sfuncs.check_bool),
        )
        sanity_check(
            ("path", path, check_saveable_path, ("pkl", force_overwrite), {}, True),
        )

        if path is None:
            x = 1
            while True:
                path = Path(f"estimator_{x}.pkl").resolve()
                if path.is_file():
                    x += 1
                else:
                    break

        path = configure_path(path, "pkl")
        save_file(self, path, binary=True, fprint=fprint)

    @classmethod
    def from_pickle(
        cls,
        path: Union[str, Path],
    ) -> Estimator:
        """Load a pickled estimator instance.

        Parameters
        ----------
        path
            The path to the pickle file.

        Returns
        -------
        estimator : :py:class:`Estimator`

        Notes
        -----
        .. warning::
           `From the Python docs:`

           *"The pickle module is not secure. Only unpickle data you trust.
           It is possible to construct malicious pickle data which will
           execute arbitrary code during unpickling. Never unpickle data
           that could have come from an untrusted source, or that could have
           been tampered with."*

           You should only use :py:meth:`from_pickle` on files that
           you are 100% certain were generated using
           :py:meth:`to_pickle`. If you load pickled data from a .pkl file,
           and the resulting output is not an instance of
           :py:class:`Estimator`, an error will be raised.

        See Also
        --------

        :py:meth:`Estimator.to_pickle`
        """
        sanity_check(("path", path, check_existent_path, ("pkl",)))
        path = configure_path(path, "pkl")
        obj = open_file(path, binary=True)

        if isinstance(obj, __class__):
            return obj
        else:
            raise TypeError(
                f"{RED}It is expected that the object loaded by"
                " `from_pickle` is an instance of"
                f" {__class__.__module__}.{__class__.__qualname__}."
                f" What was loaded didn't satisfy this!{END}"
            )

    @abc.abstractmethod
    def estimate(*args, **kwargs):
        pass

    def get_results(self, indices: Optional[Iterable[int]] = None) -> Iterable[Result]:
        """Obtain a subset of the estimation results obtained.

        By default, all results are returned, in the order in which they are obtained.

        Parameters
        ----------
        indices
            The indices of results to return. Index ``0`` corresponds to the first
            result obtained using the estimator, ``1`` corresponds to the next, etc.
            If ``None``, all results will be returned.
        """
        if not self._results:
            return None

        length = len(self._results)
        sanity_check(
            (
                "indices", indices, sfuncs.check_int_list, (),
                {"max_value": length - 1}, True,
            ),
        )

        if indices is None:
            return self._results
        else:
            indices = [i % length for i in indices]
            return [self._results[i] for i in indices]

    def get_params(
        self,
        indices: Optional[Iterable[int]] = None,
        merge: bool = True,
        funit: str = "hz",
        sort_by: str = "f-1",
    ) -> Union[Iterable[np.ndarray], np.ndarray]:
        """Return estimation result parameters.

        Parameters
        ----------
        indices
            The indices of results to extract parameters from. Index ``0``
            corresponds to the first result obtained using the estimator, ``1``
            corresponds to the next, etc.  If ``None``, all results will be
            used.

        merge
            If ``True``, a single array of all parameters from each specified
            estiamtion result specified will be returned. If ``False``, an iterable
            of each individual estimation result's parameters will be returned.

        funit
            The unit to express frequencies in. Must be one of ``"hz"`` and ``"ppm"``.

        sort_by
            Specifies the parameter by which the oscillators are ordered by.
            Should be one of ``"a"`` for amplitudes ``"p"`` for phase, ``"f<n>"``
            for frequency in the ``<n>``-th dimension, ``"d<n>"`` for the damping
            factor in the ``<n>``-th dimension. By setting ``<n>`` to ``-1``, the
            final (direct) dimension will be used. For 1D data, ``"f"`` and ``"d"``
            can be used to specify the frequency or damping factor.
        """
        sanity_check(
            (
                "indices", indices, sfuncs.check_int_list, (),
                {"max_value": len(self._results) - 1}, True,
            ),
            ("merge", merge, sfuncs.check_bool),
            ("funit", funit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
            ("sort_by", sort_by, sfuncs.check_sort_by, (self.dim,)),
        )

        return self._get_arrays("params", indices, funit, sort_by, merge)

    def get_errors(
        self,
        indices: Optional[Iterable[int]] = None,
        merge: bool = True,
        funit: str = "hz",
        sort_by: str = "f-1",
    ) -> Union[Iterable[np.ndarray], np.ndarray]:
        """Return estimation result errors.

        Parameters
        ----------
        indices
            The indices of results to extract errors from. Index ``0`` corresponds to
            the first result obtained using the estimator, ``1`` corresponds to
            the next, etc.  If ``None``, all results will be used.

        merge
            If ``True``, a single array of all parameters from each specified
            estiamtion result specified will be returned. If ``False``, an iterable
            of each individual estimation result's parameters will be returned.

        funit
            The unit to express frequencies in. Must be one of ``"hz"`` and ``"ppm"``.

        sort_by
            Specifies the parameter by which the oscillators are ordered by.
            Should be one of ``"a"`` for amplitudes ``"p"`` for phase, ``"f<n>"``
            for frequency in the ``<n>``-th dimension, ``"d<n>"`` for the damping
            factor in the ``<n>``-th dimension. By setting ``<n>`` to ``-1``, the
            final (direct) dimension will be used. For 1D data, ``"f"`` and ``"d"``
            can be used to specify the frequency or damping factor.
        """
        sanity_check(
            (
                "indices", indices, sfuncs.check_int_list, (),
                {"max_value": len(self._results) - 1}, True,
            ),
            ("merge", merge, sfuncs.check_bool),
            ("funit", funit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
            ("sort_by", sort_by, sfuncs.check_sort_by, (self.dim,)),
        )

        return self._get_arrays("errors", indices, funit, sort_by, merge)

    def _get_arrays(
        self,
        name: str,
        indices: Iterable[int],
        funit: str,
        sort_by: str,
        merge: bool,
    ) -> np.ndarray:
        results = self.get_results(indices)
        arrays = [result._get_array(name, funit, sort_by) for result in results]

        if merge:
            array = np.vstack(arrays)
            sort_idx = results[0]._process_sort_by(sort_by, self.dim)

            param_array = np.vstack(
                [
                    result._get_array("params", funit, sort_by)
                    for result in results
                ]
            )

            array = array[np.argsort(param_array[:, sort_idx])]
            return array

        else:
            return arrays

    def make_fid(
        self,
        indices: Optional[Iterable[int]] = None,
        pts: Optional[Iterable[int]] = None,
        fn_mode: Optional[str] = None,
    ) -> np.ndarray:
        """Construct a noiseless FID from estimation result parameters.

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

        fn_mode
            Acquisition mode in indirect dimensions of mulit-dimensional experiments.
            If the data is not 1-dimensional, this should be one of ``None``,
            ``"QF"``, ``"QSED"``, ``"TPPI"``, ``"States"``, ``"States-TPPI"``,
            ``"Echo-Anitecho"``. If ``None``, ``self.fn_mode`` will be used.
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
            ("fn_mode", fn_mode, sfuncs.check_fn_mode, (), {}, True),
        )

        params = self.get_params(indices)
        return super().make_fid(params, pts=pts, fn_mode=fn_mode)

    @abc.abstractmethod
    def write_result(*args, **kwargs):
        pass

    @abc.abstractmethod
    def plot_result(*args, **kwargs):
        pass

    @logger
    def merge_oscillators(
        self,
        oscillators: Iterable[int],
        index: int = -1,
        **estimate_kwargs,
    ) -> None:
        """Merge oscillators in an estimation result.

        Removes the osccilators specified, and constructs a single new
        oscillator with a cumulative amplitude, and averaged phase,
        frequency and damping. Then runs optimisation on the updated set of
        oscillators.

        Parameters
        ----------
        oscillators
            A list of indices corresponding to the oscillators to be merged.

        index
            The index of the result to edit. Index ``0`` corresponds to the
            first result obtained using the estimator, ``1`` corresponds to the
            next, etc. By default, the most recently obtained result will be
            edited.

        estimate_kwargs
            Keyword arguments to provide to the call to :py:meth:`estimate`. Note
            that ``"initial_guess"`` and ``"region_unit"`` are set internally and
            will be ignored if given.

        Notes
        -----
        Assuming that an estimation result contains a subset of oscillators
        denoted by indices :math:`\\{m_1, m_2, \\cdots, m_J\\}`, where :math:`J
        \\leq M`, the new oscillator formed by the merging of the oscillator
        subset will possess the following parameters prior to re-running estimation:

            * :math:`a_{\\mathrm{new}} = \\sum_{i=1}^J a_{m_i}`
            * :math:`\\phi_{\\mathrm{new}} = \\frac{1}{J} \\sum_{i=1}^J
              \\phi_{m_i}`
            * :math:`f_{\\mathrm{new}} = \\frac{1}{J} \\sum_{i=1}^J f_{m_i}`
            * :math:`\\eta_{\\mathrm{new}} = \\frac{1}{J} \\sum_{i=1}^J
              \\eta_{m_i}`
        """
        sanity_check(
            ("index", index, sfuncs.check_index, (len(self._results),)),
        )
        index = self._positive_index(index)
        result = self._results[index]
        x0 = result.get_params()
        sanity_check(
            (
                "oscillators", oscillators, sfuncs.check_int_list,
                (), {"min_value": 0, "max_value": x0.shape[0] - 1},
            )
        )

        to_merge = x0[oscillators]
        # Sum amps, phases, freqs and damping over the oscillators
        # to be merged.
        # keepdims ensures that the final array is [[a, φ, f, η]]
        # rather than [a, φ, f, η]
        new_osc = np.sum(to_merge, axis=0, keepdims=True)

        # Get mean for phase, frequency and damping
        new_osc[:, 1:] = new_osc[:, 1:] / float(len(oscillators))
        # wrap phase
        new_osc[:, 1] = (new_osc[:, 1] + np.pi) % (2 * np.pi) - np.pi

        x0 = np.delete(x0, oscillators, axis=0)
        x0 = np.vstack((x0, new_osc))

        self._optimise_after_edit(x0, result, index)

    @logger
    def split_oscillator(
        self,
        oscillator: int,
        index: int = -1,
        separation_frequency: Optional[Iterable[float]] = None,
        unit: str = "hz",
        split_number: int = 2,
        amp_ratio: Optional[Iterable[float]] = None,
        **estimate_kwargs,
    ) -> None:
        """Splits an oscillator in an estimation result into multiple oscillators.

        Removes an oscillator, and incorporates two or more oscillators whose
        cumulative amplitudes match that of the removed oscillator. Then runs
        optimisation on the updated set of oscillators.

        Parameters
        ----------
        oscillator
            The index of the oscillator to be split.

        index
            The index of the result to edit. Index ``0`` corresponds to the
            first result obtained using the estimator, ``1`` corresponds to the
            next, etc. By default, the most recently obtained result will be
            edited.

        separation_frequency
            The frequency separation given to adjacent oscillators formed
            from the splitting. If ``None``, the splitting will be set to
            ``sw / n`` in each dimension where ``sw`` is the sweep width and
            ``n`` is the number of points in the data.

        unit
            The unit that ``separation_frequency`` is expressed in.

        split_number
            The number of peaks to split the oscillator into.

        amp_ratio
            The ratio of amplitudes to be fulfilled by the newly formed
            peaks. If a list, ``len(amp_ratio) == split_number`` must be
            satisfied. The first element will relate to the highest
            frequency oscillator constructed, and the last element will
            relate to the lowest frequency oscillator constructed. If `None`,
            all oscillators will be given equal amplitudes.

        estimate_kwargs
            Keyword arguments to provide to the call to :py:meth:`estimate`. Note
            that ``"initial_guess"`` and ``"region_unit"`` are set internally and
            will be ignored if given.
        """
        sanity_check(
            ("index", index, sfuncs.check_index, (len(self._results),)),
            (
                "separation_frequency", separation_frequency, sfuncs.check_float_list,
                (), {"length": self.dim, "len_one_can_be_listless": True}, True,
            ),
            ("unit", unit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
            ("split_number", split_number, sfuncs.check_int, (), {"min_value": 2}),
        )
        index = self._positive_index(index)
        result = self._results[index]
        x0 = result.get_params()
        sanity_check(
            (
                "amp_ratio", amp_ratio, sfuncs.check_float_list, (),
                {
                    "length": split_number,
                    "must_be_positive": True,
                },
                True,
            ),
            (
                "oscillator", oscillator, sfuncs.check_int, (),
                {"min_value": 0, "max_value": x0.shape[0] - 1},
            ),
        )

        if separation_frequency is None:
            separation_frequency = [
                sw / pts for sw, pts in zip(self.sw(unit), self.default_pts)
            ]
        else:
            if isinstance(separation_frequency, int):
                separation_frequency = [separation_frequency]
            separation_frequency = (
                self.convert(separation_frequency, f"{unit}->hz")
            )

        if amp_ratio is None:
            amp_ratio = np.ones((split_number,))
        else:
            amp_ratio = np.array(amp_ratio)

        osc = x0[oscillator]
        amps = osc[0] * amp_ratio / amp_ratio.sum()
        # Highest frequency of all the new oscillators
        max_freqs = [
            osc[i] + ((split_number - 1) * separation_frequency[i - 2] / 2)
            for i in range(2, 2 + self.dim)
        ]
        # Array of all frequencies (lowest to highest)
        freqs = np.array(
            [
                [max_freq - i * sep_freq for i in range(split_number)]
                for max_freq, sep_freq in zip(max_freqs, separation_frequency)
            ],
            dtype="float64",
        ).T

        new_oscs = np.zeros((split_number, 2 * (1 + self.dim)), dtype="float64")
        new_oscs[:, 0] = amps
        new_oscs[:, 1] = osc[1]
        new_oscs[:, 2 : 2 + self.dim] = freqs
        new_oscs[:, 2 + self.dim :] = osc[2 + self.dim :]
        print(new_oscs)

        x0 = np.delete(x0, oscillator, axis=0)
        x0 = np.vstack((x0, new_oscs))

        self._optimise_after_edit(x0, result, index, **estimate_kwargs)

    @logger
    def add_oscillators(
        self,
        params: np.ndarray,
        index: int = -1,
        **estimate_kwargs,
    ) -> None:
        """Add oscillators to an estimation result.

        Optimisation is carried out afterwards, on the updated set of oscillators.

        Parameters
        ----------
        params
            The parameters of new oscillators to be added. Should be of shape
            ``(n, 2 * (1 + self.dim))``, where ``n`` is the number of new
            oscillators to add. Even when one oscillator is being added this
            should be a 2D array, i.e.:

            .. code:: python3

                params = oscillators = np.array([[a, φ, f, η]])

        index
            The index of the result to edit. Index ``0`` corresponds to the
            first result obtained using the estimator, ``1`` corresponds to the
            next, etc. By default, the most recently obtained result will be
            edited.

        estimate_kwargs
            Keyword arguments to provide to the call to :py:meth:`estimate`. Note
            that ``"region"``, ``noise_region"``, ``"initial_guess"`` and
            ``"region_unit"`` are set internally and will be ignored if given.
        """
        sanity_check(
            (
                "params", params, sfuncs.check_ndarray, (),
                {"dim": 2, "shape": ((1, 2 * (self.dim + 1)),)},
            ),
            ("index", index, sfuncs.check_index, (len(self._results),)),
        )
        index = self._positive_index(index)
        result = self._results[index]
        x0 = np.vstack((result.get_params(), params))
        self._optimise_after_edit(x0, result, index, **estimate_kwargs)

    @logger
    def remove_oscillators(
        self,
        oscillators: Iterable[int],
        index: int = -1,
        **estimate_kwargs,
    ) -> None:
        """Remove oscillators from an estimation result.

        Optimisation is carried out afterwards, on the updated set of oscillators.

        Parameters
        ----------
        oscillators
            A list of indices corresponding to the oscillators to be removed.

        index
            The index of the result to edit. Index ``0`` corresponds to the
            first result obtained using the estimator, ``1`` corresponds to the
            next, etc. By default, the most recently obtained result will be
            edited.

        estimate_kwargs
            Keyword arguments to provide to the call to :py:meth:`estimate`. Note
            that ``"initial_guess"`` and ``"region_unit"`` are set internally and
            will be ignored if given.
        """
        sanity_check(("index", index, sfuncs.check_index, (len(self._results),)))
        index = self._positive_index(index)
        result = self._results[index]
        x0 = result.get_params()
        sanity_check(
            (
                "oscillators", oscillators, sfuncs.check_int_list, (),
                {"min_value": 0, "max_value": x0.shape[0] - 1},
            ),
        )
        x0 = np.delete(x0, oscillators, axis=0)
        self._optimise_after_edit(x0, result, index, **estimate_kwargs)

    def _optimise_after_edit(
        self,
        x0: np.ndarray,
        result: Result,
        index: int,
        **estimate_kwargs,
    ) -> None:
        for key in estimate_kwargs.keys():
            if key in ("region", "noise_region", "region_unit", "initial_guess"):
                del estimate_kwargs[key]

        self.estimate(
            result.get_region()[1],
            result.get_noise_region()[1],
            region_unit="hz",
            initial_guess=x0,
            fprint=False,
            _log=False,
            **estimate_kwargs,
        )

        del self._results[index]
        self._results.insert(index, self._results.pop(-1))

    def _positive_index(self, index: int) -> int:
        return index % len(self._results)


class Result(ResultFetcher):

    def __init__(
        self,
        params: np.ndarray,
        errors: np.ndarray,
        region: Iterable[Tuple[float, float]],
        noise_region: Iterable[Tuple[float, float]],
        sfo: Iterable[float],
    ) -> None:
        self.params = params
        self.errors = errors
        self.region = region
        self.noise_region = noise_region
        super().__init__(sfo)

    def get_region(self, unit: str = "hz"):
        sanity_check(
            ("unit", unit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
        )
        return self.convert(self.region, f"hz->{unit}")

    def get_noise_region(self, unit: str = "hz"):
        sanity_check(
            ("unit", unit, sfuncs.check_frequency_unit, (self.hz_ppm_valid,)),
        )
        return self.convert(self.noise_region, f"hz->{unit}")
