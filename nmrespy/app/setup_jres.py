# setup_jres.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Thu 20 Oct 2022 11:49:42 BST

import tkinter as tk
from tkinter import ttk

from matplotlib import backends, pyplot as plt, transforms
import numpy as np

import nmrespy as ne
from nmrespy.app import config as cf, custom_widgets as wd
from nmrespy.app.stup import Setup1DType


class Setup2DJ(Setup1DType):
    default_maxits = {
        "Exact Hessian": "20",
        "Gauss-Newton": "40",
        "L-BFGS": "100",
    }

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.construct_contour_objects()

    def conv_1d(self, value, conversion):
        return self.estimator.convert([None, value], conversion)[-1]

    def construct_gui_frames(self):
        super().construct_gui_frames()
        self.plot_notebook = ttk.Notebook(self.plot_frame)
        self.onedim_frame = wd.MyFrame(self.plot_notebook, bg=cf.NOTEBOOKCOLOR)
        self.jres_frame = wd.MyFrame(self.plot_notebook, bg=cf.NOTEBOOKCOLOR)
        self.contour_frame = wd.MyFrame(self.notebook, bg=cf.NOTEBOOKCOLOR)

    def place_gui_frames(self):
        super().place_gui_frames()
        self.plot_notebook.add(
            self.onedim_frame,
            text="1D",
            sticky="nsew",
        )
        self.plot_notebook.add(
            self.jres_frame,
            text="2DJ",
            sticky="nsew",
        )
        self.plot_notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.notebook.add(
            self.contour_frame,
            text="Contour levels",
            sticky="nsew",
            state="disabled",
        )

    def configure_gui_frames(self):
        super().configure_gui_frames()
        for frame in (self.onedim_frame, self.jres_frame):
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)

    def construct_1d_figure(self):
        super().construct_1d_figure(
            self.onedim_frame,
            self.estimator.spectrum_zero_t1.real,
            cf.NOTEBOOKCOLOR,
        )

    def construct_2d_figure(self):
        self.fig_2d, self.ax_2d = self.new_figure()
        self.ax_2d.set_xlim(self.lims[-1])
        self.ax_2d.set_ylim(self.lims[0])
        # self.lims generated by `construct_1d_figure`
        cf.Restrictor(self.ax_2d, x_bounds=self.lims[-1], y_bounds=self.lims[0])

        self.ax_2d.callbacks.connect("xlim_changed", lambda evt: self.update_ax_xlim(1))
        self.ax_1d.callbacks.connect("xlim_changed", lambda evt: self.update_ax_xlim(2))

        # Aesthetic tweaks
        self.fig_2d.patch.set_facecolor(cf.NOTEBOOKCOLOR)
        self.ax_2d.set_facecolor(cf.PLOTCOLOR)
        self.ax_2d.set_xlabel(
            f"{self.estimator.unicode_nuclei[-1]} (ppm)",
            fontsize=8,
        )
        self.ax_2d.set_ylabel("Hz", fontsize=8, labelpad=0)
        for axis in ("x", "y"):
            self.ax_2d.tick_params(axis=axis, which="major", labelsize=6)
        for direction in ("top", "bottom", "left", "right"):
            self.ax_2d.spines[direction].set_color("k")

        self.spec_contour = self.ax_2d.contour(
            self.shifts[-1],
            self.shifts[0],
            np.abs(self.estimator.spectrum).real,
            colors="k",
            linewidths=0.5,
        )

        self.canvas_2d = backends.backend_tkagg.FigureCanvasTkAgg(
            self.fig_2d,
            master=self.jres_frame,
        )
        self.canvas_2d.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self.toolbar_2d = wd.MyNavigationToolbar(
            self.canvas_2d,
            parent=self.jres_frame,
            color=cf.NOTEBOOKCOLOR,
        )
        self.toolbar_2d.grid(row=1, column=0, padx=(10, 0), pady=(0, 5), sticky="w")

    def construct_region_objects(self):
        self.region_patches_2d = []
        self.region_labels_2d = []
        super().construct_region_objects()

    def new_region(self, noise=False):
        super().new_region(noise)
        idx = len(self.regions) - 1
        color = self.region_colors[idx - 1] if not noise else "#808080"
        patch_2d = self.ax_2d.axvspan(
            *self.regions[idx]["ppm"],
            facecolor=color,
        )
        self.region_patches_2d.append(patch_2d)

        trans = transforms.blended_transform_factory(
            self.ax_2d.transData,
            self.ax_2d.transAxes,
        )
        label = self.ax_2d.text(
            self.regions[idx]["ppm"][0],
            0.995,
            str(idx - 1) if not noise else "N",
            verticalalignment="top",
            transform=trans,
            fontsize=7,
        )
        self.region_labels_2d.append(label)

    def configure_notebooks(self):
        super().configure_notebooks()
        self.plot_notebook.bind(
            "<<NotebookTabChanged>>",
            lambda event: self.switch_plot_tab(),
        )

    def construct_contour_objects(self):
        self.nlev = 10
        self.base = np.amax(np.abs(self.estimator.spectrum).real) / 10
        self.factor = 1.2

        self.nlev_label = wd.MyLabel(
            self.contour_frame,
            text="# levels:",
            bg=cf.NOTEBOOKCOLOR,
        )
        self.nlev_label.grid(row=0, column=0, padx=(10, 0), pady=(10, 0))

        self.nlev_entry = wd.MyEntry(
            self.contour_frame,
            return_command=self.update_nlev,
            width=12,
        )
        self.nlev_entry.insert(0, str(self.nlev))
        self.nlev_entry.grid(row=0, column=1, padx=10, pady=(10, 0))

        self.base_label = wd.MyLabel(
            self.contour_frame,
            text="base:",
            bg=cf.NOTEBOOKCOLOR,
        )
        self.base_label.grid(row=1, column=0, padx=(10, 0), pady=(10, 0))

        self.base_entry = wd.MyEntry(
            self.contour_frame,
            return_command=self.update_base,
            width=12,
        )
        self.base_entry.insert(0, f"{self.base:6g}".replace(" ", ""))
        self.base_entry.grid(row=1, column=1, padx=10, pady=(10, 0))

        self.factor_label = wd.MyLabel(
            self.contour_frame,
            text="factor:",
            bg=cf.NOTEBOOKCOLOR,
        )
        self.factor_label.grid(row=2, column=0, padx=(10, 0), pady=10)

        self.factor_entry = wd.MyEntry(
            self.contour_frame,
            return_command=self.update_factor,
            width=12,
        )
        self.factor_entry.insert(0, f"{self.factor:6g}".replace(" ", ""))
        self.factor_entry.grid(row=2, column=1, padx=10, pady=10)

    def update_spectrum(self):
        p0 = (0., self.p0["rad"])
        p1 = (0., self.p1["rad"])
        pivot = (0., self.pivot["idx"])
        data_1d = self.estimator.data[0]
        data_1d = ne.sig.exp_apodisation(data_1d, self.lb)
        data_1d[0] *= 0.5
        self.spec_line.set_ydata(
            ne.sig.phase(ne.sig.ft(data_1d), [p0[-1]], [p1[-1]], [pivot[-1]]).real
        )
        self.canvas_1d.draw_idle()

    def switch_main_tab(self):
        tab = super().switch_main_tab()
        plot_tab = self.plot_notebook.index(self.plot_notebook.select())

        if tab == 0:
            self.plot_notebook.tab(0, state="normal")
            self.plot_notebook.tab(1, state="disabled")
            if plot_tab == 1:
                self.plot_notebook.select(0)

        elif tab == 3:
            self.plot_notebook.tab(0, state="disabled")
            self.plot_notebook.tab(1, state="normal")
            if plot_tab == 0:
                self.notebook.select(1)

        else:
            for i in (0, 1):
                self.plot_notebook.tab(i, state="normal")

        patch_alpha = 1 if tab == 1 else 0
        for label, patch in zip(self.region_labels_2d, self.region_patches_2d):
            label.set(alpha=patch_alpha)
            patch.set(alpha=patch_alpha)

        self.canvas_2d.draw_idle()

    def switch_plot_tab(self):
        tab = self.plot_notebook.index(self.plot_notebook.select())
        state = "disabled" if tab == 0 else "normal"
        self.notebook.tab(3, state=state)

    def update_region_patch(self, idx, bound):
        i, coords = super().update_region_patch(idx, bound)
        patch_2d = self.region_patches_2d[idx]
        patch_2d.set_xy(coords)

        if i == 0:
            label = self.region_labels_2d[idx]
            label.set_x(self.regions[idx]["ppm"][0])

        self.canvas_2d.draw_idle()

    @property
    def clevels(self):
        return [self.base * self.factor ** i for i in range(self.nlev)]

    def update_contour(self):
        for coll in self.spec_contour.collections:
            coll.remove()
        self.spec_contour = self.ax_2d.contour(
            self.shifts[-1],
            self.shifts[0],
            np.abs(self.estimator.spectrum).real,
            colors="k",
            linewidths=0.5,
            levels=self.clevels,
        )
        self.canvas_2d.draw_idle()

    def update_nlev(self):
        inpt = self.nlev_entry.get()
        try:
            value = int(inpt)
            assert value > 0
            self.nlev = value
            self.update_contour()

        except Exception:
            pass

        self.nlev_entry.delete(0, tk.END)
        self.nlev_entry.insert(0, str(self.nlev))

    def update_base(self):
        inpt = self.base_entry.get()
        try:
            value = float(inpt)
            assert value >= 0.
            self.base = value
            self.update_contour()

        except Exception:
            pass

        self.base_entry.delete(0, tk.END)
        self.base_entry.insert(0, f"{self.base:6g}".replace(" ", ""))

    def update_factor(self):
        inpt = self.factor_entry.get()
        try:
            value = float(inpt)
            assert value > 1.
            self.factor = value
            self.update_contour()

        except Exception:
            pass

        self.factor_entry.delete(0, tk.END)
        self.factor_entry.insert(0, f"{self.factor:6g}".replace(" ", ""))

    def update_ax_xlim(self, i):
        if self.ax_1d.get_xlim() == self.ax_2d.get_xlim():
            return
        else:
            j = 3 - i
            getattr(self, f"ax_{i}d").set_xlim(getattr(self, f"ax_{j}d").get_xlim())
            getattr(self, f"canvas_{i}d").draw_idle()
