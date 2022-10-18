# result_onedim.py
# Simon Hulse
# simon.hulse@chem.ox.ac.uk
# Last Edited: Tue 18 Oct 2022 16:46:36 BST

from matplotlib import backends

from nmrespy.app.result import Result1DType
from nmrespy.app import config as cf, custom_widgets as wd


class Result1D(Result1DType):
    table_titles = [
        "a",
        "ϕ (rad)",
        "f (ppm)",
        "η (s⁻¹)",
    ]

    def __init__(self, ctrl):
        super().__init__(ctrl)

    def new_region(self, idx, replace=False):
        def append(lst, obj):
            if replace:
                lst.pop(idx)
                lst.insert(idx, obj)
            else:
                lst.append(obj)

        fig, ax = self.estimator.plot_result(
            indices=[idx],
            axes_bottom=0.12,
            axes_left=0.02,
            axes_right=0.98,
            axes_top=0.98,
            region_unit="ppm",
            figsize=(6, 3.5),
            dpi=170,
        )
        ax = ax[0][0]
        fig.patch.set_facecolor(cf.NOTEBOOKCOLOR)
        ax.set_facecolor(cf.PLOTCOLOR)
        append(self.figs, fig)
        append(self.axs, ax)
        append(
            self.xlims,
            self.estimator.get_results(indices=[idx])[0].get_region(unit="ppm")[-1],
        )
        cf.Restrictor(self.axs[idx], self.xlims[idx])

        append(
            self.canvases,
            backends.backend_tkagg.FigureCanvasTkAgg(
                self.figs[idx],
                master=self.tabs[idx],
            ),
        )
        self.canvases[idx].get_tk_widget().grid(column=0, row=0, sticky="nsew")

        append(
            self.toolbars,
            wd.MyNavigationToolbar(
                self.canvases[idx],
                parent=self.tabs[idx],
                color=cf.NOTEBOOKCOLOR,
            ),
        )
        self.toolbars[idx].grid(row=1, column=0, padx=10, pady=5, sticky="w")
        super().new_region(idx, replace)