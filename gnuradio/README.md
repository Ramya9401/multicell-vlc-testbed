# GNU Radio flowgraphs

Drop the testbed flowgraphs here. Suggested layout:

```
gnuradio/
├── tx_ofdm_singlecell.grc      single LED, QPSK / 16-QAM passband OFDM
├── rx_ofdm_singlecell.grc      sync, FFT demod, channel estimation, equalisation
├── tx_twocell_zf.grc           two LEDs, zero-forcing precoded streams
├── tx_twocell_jt.grc           two LEDs, same stream (joint transmission)
└── blocks/                     any out-of-tree Python blocks the flowgraphs import
```

Commit the **`.grc` files**, not the generated `top_block.py` — `.gitignore`
already excludes the generated sources. The `.grc` is the source of truth and
regenerates cleanly on any machine.

## Worth recording in this file once the flowgraphs land

- GNU Radio version and UHD version the flowgraphs were built against
- USRP sample rate, intermediate frequency, and OFDM parameters
  (FFT size, cyclic prefix length, occupied subcarriers, pilot pattern)
- DC bias and drive amplitude used at the bias tee
- Any hardware-specific gain settings that a different USRP would need changed

Without those, a reader cannot reproduce the measurement even with the
flowgraphs in hand.
