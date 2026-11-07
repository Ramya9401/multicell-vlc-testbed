# Analysis and precoding source

Drop the scripts that are not GNU Radio flowgraphs here. Likely candidates:

```
src/
├── channel_model.py       Lambertian gain, link budget
├── precoding.py           zero-forcing precoder, column normalisation
├── estimate_csi.py        channel estimation from pilot subcarriers
├── analyse_measurements.py  SINR / BER / spectral efficiency from capture files
└── plot_results.py        figures for the paper
```

The analytical model used for the README figures already lives in
[`../tools/make_figures.py`](../tools/make_figures.py) and is importable:

```python
from tools.make_figures import schemes_at, best_scheme, channel_gain
```

If the measurement scripts duplicate any of that, prefer importing it so the
model has one definition.
