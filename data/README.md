# Data

| File | Contents |
|---|---|
| `measured_spectral_efficiency.csv` | Table I of the paper: peak / average / minimum spectral efficiency per transmission scheme |

## What is missing

The per-position measurement series behind Figs. 6–11 of the paper are not
here — only the summary in Table I. If you still have the capture files or the
processed traces, adding them makes the repository genuinely reproducible.
A useful shape:

```
data/
├── measured_spectral_efficiency.csv      (present)
├── channel_gain_vertical.csv             position_cm, measured_gain, model_gain
├── channel_gain_horizontal.csv           position_cm, measured_gain, model_gain
├── ber_singlecell.csv                    ebn0_db, ber_qpsk, ber_16qam
├── sinr_twocell_qpsk.csv                 position_cm, sinr_np_db, sinr_zf_db
├── sinr_twocell_16qam.csv                position_cm, sinr_np_db, sinr_zf_db
└── snr_jt_vs_siso.csv                    position_cm, snr_siso_db, snr_jt_db
```

Raw IQ captures are large: keep them out of git (`.gitignore` already excludes
`data/raw/` and `*.iq`) and either use Git LFS or deposit them in Zenodo and
link the DOI here.
