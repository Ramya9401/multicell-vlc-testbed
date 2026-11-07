#!/usr/bin/env python3
"""Generate the README figures as SVG, in matching light and dark variants.

No third-party dependencies: the plotting is a few hundred lines of SVG
emitted directly, so `python3 tools/make_figures.py` works on a clean
checkout with nothing installed.

The curves are the analytical model from the paper (Section II and III),
calibrated to the experimental geometry. Measured values live in
data/measured_spectral_efficiency.csv and are plotted separately.

Usage:
    python3 tools/make_figures.py [--out figures]
"""

from __future__ import annotations

import argparse
import math
import os
from typing import Callable, Iterable, Sequence

# --------------------------------------------------------------------------
# Experimental configuration (Section IV of the paper)
# --------------------------------------------------------------------------

SEPARATION_CM = 170.0   # distance between the two LEDs
HEIGHT_CM = 160.0       # mounting height above the detector plane
PHI_HALF_DEG = 17.0     # LED half-intensity angle
CSI_ERROR = 0.12        # residual cross-talk after imperfect channel estimation
BORESIGHT_SNR_DB = 42.0 # calibration point: SNR directly beneath a lamp

THEMES = {
    "light": dict(
        bg="#FFFFFF", ink="#111111", ink2="#444444", grid="#E2E2E2", axis="#111111",
        siso="#14647A", np="#555E6B", zf="#5B3FA8", jt="#8A4512",
        qpsk="#14647A", qam16="#8A4512", band_alpha="0.90",
    ),
    "dark": dict(
        bg="#15171C", ink="#E9EAEC", ink2="#A8AEB8", grid="#2B2F38", axis="#C2C5CB",
        siso="#56BCD2", np="#8B94A4", zf="#A990F2", jt="#E8975A",
        qpsk="#56BCD2", qam16="#E8975A", band_alpha="0.90",
    ),
}

# Each scheme keeps the same dash pattern across every figure, so the curves
# stay distinguishable without relying on colour alone.
DASH = {"siso": "6 4", "np": "2 3", "zf": "none", "jt": "10 4"}


# --------------------------------------------------------------------------
# Physical model
# --------------------------------------------------------------------------

def lambertian_order(phi_half_deg: float) -> float:
    """m = -ln2 / ln(cos(phi_half)), eq. (2)."""
    return -math.log(2.0) / math.log(math.cos(math.radians(phi_half_deg)))


def channel_gain(dx_cm: float, h_cm: float, phi_half_deg: float) -> float:
    """Lambertian channel gain, eq. (2), for a downward-facing LED and an
    upward-facing detector. Both angles collapse to the same one, leaving
    H proportional to cos^(m+1)(psi) / d^2."""
    m = lambertian_order(phi_half_deg)
    dx, h = dx_cm / 100.0, h_cm / 100.0
    d = math.hypot(dx, h)
    cos_psi = h / d
    return (cos_psi ** (m + 1)) / (d * d)


def schemes_at(x_cm: float,
               sep_cm: float = SEPARATION_CM,
               h_cm: float = HEIGHT_CM,
               phi_half_deg: float = PHI_HALF_DEG,
               csi_error: float = CSI_ERROR,
               boresight_snr_db: float = BORESIGHT_SNR_DB) -> dict:
    """Linear SINR for each transmission scheme at user position x.

    Two users are placed symmetrically (one at x, one at sep - x), which makes
    the channel matrix H = [[a, b], [b, a]] and keeps the zero-forcing algebra
    closed form.
    """
    a = channel_gain(x_cm, h_cm, phi_half_deg)              # serving lamp
    b = channel_gain(x_cm - sep_cm, h_cm, phi_half_deg)     # interfering lamp
    peak = channel_gain(0.0, h_cm, phi_half_deg)

    # Noise variance normalised to 1; K sets the boresight SNR calibration.
    k = math.sqrt(10.0 ** (boresight_snr_db / 10.0)) / peak
    amp_desired, amp_interf = k * a, k * b

    siso = amp_desired ** 2                                  # eq. (3)
    no_precoding = siso / (amp_interf ** 2 + 1.0)            # eq. (6)

    # Zero-forcing, eq. (7)-(8). The determinant vanishes at the midpoint where
    # a == b, so clamp it: that singularity is the noise-enhancement effect.
    det = a * a - b * b
    det = math.copysign(max(abs(det), 1e-15), det if det else 1.0)
    precoder_norm = math.hypot(a, b) / abs(det)
    zf_amplitude = k / precoder_norm
    residual = csi_error * k * b
    zero_forcing = zf_amplitude ** 2 / (residual ** 2 + 1.0)

    joint = (amp_desired + amp_interf) ** 2                  # eq. (9)

    return {"siso": siso, "np": no_precoding, "zf": zero_forcing, "jt": joint,
            "a": a, "b": b}


def erfc(x: float) -> float:
    return math.erfc(x)


def ber_qpsk(ebn0_linear: float) -> float:
    """eq. (4)."""
    return 0.5 * erfc(math.sqrt(ebn0_linear))


def ber_mqam(ebn0_linear: float, m: int = 16) -> float:
    """eq. (5)."""
    return (3.0 / (2.0 * (m - 1))) * erfc(math.sqrt(3.0 / (m - 1) * ebn0_linear))


def spectral_efficiency(sinr_linear: float) -> float:
    return math.log2(1.0 + sinr_linear)


def best_scheme(x_cm: float, reuse_margin_db: float = 0.5, **kw) -> str:
    """Best scheme at x, counting throughput per cell.

    Reuse and zero-forcing serve two users at once; joint transmission serves
    one and the other waits, so its rate is halved. Compared link by link JT
    would win everywhere by construction.
    """
    s = schemes_at(x_cm, **kw)
    margin = 10.0 ** (reuse_margin_db / 10.0)
    candidates = {
        "np": spectral_efficiency(s["np"]) * margin,
        "zf": spectral_efficiency(s["zf"]),
        "jt": spectral_efficiency(s["jt"]) * 0.5,
    }
    return max(candidates, key=candidates.get)


# --------------------------------------------------------------------------
# Minimal SVG plotting
# --------------------------------------------------------------------------

W, H = 760, 400
PAD = dict(l=74, r=22, t=22, b=56)


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class Plot:
    def __init__(self, theme: dict, xlim, ylim, xlabel, ylabel, ylog=False,
                 width=W, height=H):
        self.t, self.w, self.h = theme, width, height
        self.x0, self.x1 = xlim
        self.y0, self.y1 = ylim
        self.ylog = ylog
        self.under: list[str] = []    # grid and axes
        self.curves: list[str] = []   # data, clipped to the plot rectangle
        self.over: list[str] = []     # legend and annotations
        self.parts = self.under       # grid() and axis labels land here
        self.iw = width - PAD["l"] - PAD["r"]
        self.ih = height - PAD["t"] - PAD["b"]
        self.xlabel, self.ylabel = xlabel, ylabel

    def X(self, x: float) -> float:
        return PAD["l"] + (x - self.x0) / (self.x1 - self.x0) * self.iw

    def Y(self, y: float) -> float:
        if self.ylog:
            lo, hi = math.log10(self.y0), math.log10(self.y1)
            y = math.log10(max(y, self.y0 * 1e-3))
            return PAD["t"] + self.ih - (y - lo) / (hi - lo) * self.ih
        return PAD["t"] + self.ih - (y - self.y0) / (self.y1 - self.y0) * self.ih

    def grid(self, xticks: Sequence[float], yticks: Sequence[float],
             xfmt: Callable = str, yfmt: Callable = str):
        t = self.t
        for yv in yticks:
            y = round(self.Y(yv)) + 0.5
            self.parts.append(
                f'<line x1="{PAD["l"]}" y1="{y}" x2="{PAD["l"]+self.iw}" y2="{y}" '
                f'stroke="{t["grid"]}" stroke-width="1"/>')
            self.parts.append(
                f'<text x="{PAD["l"]-10}" y="{y+4}" fill="{t["ink2"]}" font-size="12" '
                f'text-anchor="end" font-family="Helvetica,Arial,sans-serif">{esc(yfmt(yv))}</text>')
        for xv in xticks:
            x = round(self.X(xv)) + 0.5
            self.parts.append(
                f'<line x1="{x}" y1="{PAD["t"]}" x2="{x}" y2="{PAD["t"]+self.ih}" '
                f'stroke="{t["grid"]}" stroke-width="1"/>')
            self.parts.append(
                f'<text x="{x}" y="{PAD["t"]+self.ih+20}" fill="{t["ink2"]}" font-size="12" '
                f'text-anchor="middle" font-family="Helvetica,Arial,sans-serif">{esc(xfmt(xv))}</text>')
        self.parts.append(
            f'<path d="M{PAD["l"]+0.5} {PAD["t"]} V{PAD["t"]+self.ih+0.5} '
            f'H{PAD["l"]+self.iw}" fill="none" stroke="{t["axis"]}" stroke-width="1.2"/>')
        self.parts.append(
            f'<text x="{PAD["l"]+self.iw/2}" y="{self.h-14}" fill="{t["ink"]}" font-size="13" '
            f'text-anchor="middle" font-family="Helvetica,Arial,sans-serif">{esc(self.xlabel)}</text>')
        self.parts.append(
            f'<text transform="translate(18,{PAD["t"]+self.ih/2}) rotate(-90)" fill="{t["ink"]}" '
            f'font-size="13" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif">{esc(self.ylabel)}</text>')

    def line(self, xs: Iterable[float], ys: Iterable[float], color: str,
             width: float = 2.2, dash: str = "none"):
        pts, started = [], False
        for x, y in zip(xs, ys):
            if not math.isfinite(y):
                started = False
                continue
            py = self.Y(y)
            if py < PAD["t"] - 240 or py > PAD["t"] + self.ih + 240:
                started = False
                continue
            pts.append(("M" if not started else "L") + f"{self.X(x):.2f} {py:.2f}")
            started = True
        if not pts:
            return
        d = "" if dash == "none" else f' stroke-dasharray="{dash}"'
        self.curves.append(
            f'<path d="{" ".join(pts)}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{d}/>')

    def band(self, segments, y_top: float, height: float):
        """segments: list of (x_start, x_end, colour) in data coordinates."""
        for xs, xe, col in segments:
            x, w = self.X(xs), self.X(xe) - self.X(xs)
            self.over.append(
                f'<rect x="{x:.2f}" y="{y_top}" width="{max(w,0.6):.2f}" height="{height}" '
                f'fill="{col}" opacity="{self.t["band_alpha"]}"/>')

    def text(self, x, y, s, color=None, size=12, anchor="start", weight="400", data=True):
        px, py = (self.X(x), self.Y(y)) if data else (x, y)
        c = color or self.t["ink"]
        self.over.append(
            f'<text x="{px:.1f}" y="{py:.1f}" fill="{c}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" font-family="Helvetica,Arial,sans-serif">{esc(s)}</text>')

    def legend(self, entries, x=None, y=None):
        """entries: list of (label, colour, dash)."""
        x = PAD["l"] + 12 if x is None else x
        y = PAD["t"] + 16 if y is None else y
        for i, (label, col, dash) in enumerate(entries):
            yy = y + i * 19
            d = "" if dash == "none" else f' stroke-dasharray="{dash}"'
            self.over.append(
                f'<line x1="{x}" y1="{yy}" x2="{x+26}" y2="{yy}" stroke="{col}" '
                f'stroke-width="2.4"{d}/>')
            self.over.append(
                f'<text x="{x+34}" y="{yy+4}" fill="{self.t["ink2"]}" font-size="12.5" '
                f'font-family="Helvetica,Arial,sans-serif">{esc(label)}</text>')

    def render(self) -> str:
        clip = (f'<defs><clipPath id="plot"><rect x="{PAD["l"]}" y="{PAD["t"]-6}" '
                f'width="{self.iw}" height="{self.ih+6}"/></clipPath></defs>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
                f'width="{self.w}" height="{self.h}" role="img">'
                f'<rect width="{self.w}" height="{self.h}" fill="{self.t["bg"]}"/>'
                + clip
                + "".join(self.under)
                + '<g clip-path="url(#plot)">' + "".join(self.curves) + "</g>"
                + "".join(self.over)
                + "</svg>\n")


def write(path: str, svg: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"  wrote {path}")


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def fig_channel_gain(theme: dict) -> str:
    p = Plot(theme, (-250, 250), (0, 1.05),
             "horizontal offset from LED (cm)", "normalised channel gain  H / H(0)")
    p.grid([-200, -100, 0, 100, 200], [0, 0.25, 0.5, 0.75, 1.0],
           yfmt=lambda v: f"{v:.2f}")
    palette = [("Phi_half = 12 deg", theme["zf"], "2 3"),
               ("Phi_half = 17 deg  (testbed)", theme["jt"], "none"),
               ("Phi_half = 30 deg", theme["siso"], "6 4"),
               ("Phi_half = 50 deg", theme["np"], "10 4")]
    for (label, col, dash), phi in zip(palette, (12, 17, 30, 50)):
        xs = [-250 + 500 * i / 400 for i in range(401)]
        peak = channel_gain(0, HEIGHT_CM, phi)
        ys = [channel_gain(x, HEIGHT_CM, phi) / peak for x in xs]
        p.line(xs, ys, col, 2.2, dash)
    p.legend([(f"{l}   (m = {lambertian_order(phi):.1f})", c, d)
              for (l, c, d), phi in zip(palette, (12, 17, 30, 50))],
             x=PAD["l"] + p.iw - 250, y=PAD["t"] + 18)
    return p.render()


def fig_ber(theme: dict) -> str:
    p = Plot(theme, (0, 22), (1e-7, 1), "Eb/N0 (dB)", "bit error rate", ylog=True)
    p.grid([0, 4, 8, 12, 16, 20], [1, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-7],
           xfmt=lambda v: f"{v:g}",
           yfmt=lambda v: "1" if v == 1 else f"1e{round(math.log10(v))}")
    xs = [i / 20 for i in range(0, 441)]
    p.line(xs, [ber_qpsk(10 ** (x / 10)) for x in xs], theme["qpsk"], 2.4, "none")
    p.line(xs, [ber_mqam(10 ** (x / 10)) for x in xs], theme["qam16"], 2.4, "10 4")

    # mark the Eb/N0 each modulation needs for BER = 1e-3
    target = 1e-3
    p.under.append(
        f'<line x1="{PAD["l"]}" y1="{p.Y(target):.1f}" x2="{PAD["l"]+p.iw}" "'
        f'y2="{p.Y(target):.1f}" stroke="{theme["ink2"]}" stroke-width="1" stroke-dasharray="4 4"/>')
    p.text(PAD["l"] + 6, p.Y(target) - 6, "target BER = 1e-3", theme["ink2"], 11.5, data=False)
    for fn, col, name in ((ber_qpsk, theme["qpsk"], "QPSK"),
                          (lambda g: ber_mqam(g), theme["qam16"], "16-QAM")):
        lo, hi = 0.0, 30.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if fn(10 ** (mid / 10)) > target:
                lo = mid
            else:
                hi = mid
        req = (lo + hi) / 2
        p.over.append(f'<circle cx="{p.X(req):.1f}" cy="{p.Y(target):.1f}" r="4.5" fill="{col}"/>')
        p.text(p.X(req), p.Y(target) + 22, f"{name}  {req:.1f} dB", col, 12, "middle",
               "600", data=False)
    p.legend([("QPSK, eq. (4)", theme["qpsk"], "none"),
              ("16-QAM, eq. (5)", theme["qam16"], "10 4")],
             x=PAD["l"] + p.iw - 170, y=PAD["t"] + 18)
    return p.render()


def fig_sinr_position(theme: dict) -> str:
    p = Plot(theme, (0, SEPARATION_CM), (-5, 50),
             "user position between the two LEDs (cm)", "received SINR (dB)")
    p.grid([0, 20, 40, 60, 80, 100, 120, 140, 160],
           [0, 10, 20, 30, 40, 50], xfmt=lambda v: f"{v:g}", yfmt=lambda v: f"{v:g}")
    xs = [SEPARATION_CM * i / 400 for i in range(401)]

    def db(v):
        return 10 * math.log10(max(v, 1e-30))

    series = [("siso", "SISO, single cell", DASH["siso"], 1.8),
              ("np", "Reuse, no precoding", DASH["np"], 2.2),
              ("zf", "Zero-forcing precoding", DASH["zf"], 2.6),
              ("jt", "Joint transmission", DASH["jt"], 2.6)]
    for key, _, dash, wdt in series:
        p.line(xs, [db(schemes_at(x)[key]) for x in xs], theme[key], wdt, dash)

    for pos, label in ((0, "LED 1"), (SEPARATION_CM, "LED 2")):
        p.over.append(
            f'<rect x="{p.X(pos)-13:.1f}" y="{PAD["t"]+2}" width="26" height="6" '
            f'fill="{theme["jt"] if pos == 0 else theme["siso"]}"/>')
        p.text(p.X(pos), PAD["t"] + 24, label, theme["ink2"], 11.5, "middle", data=False)
    p.text(p.X(SEPARATION_CM / 2), PAD["t"] + p.ih - 10, "cell edge",
           theme["ink2"], 11.5, "middle", data=False)
    p.legend([(lbl, theme[k], d) for k, lbl, d, _ in series],
             x=PAD["l"] + p.iw - 196, y=PAD["t"] + 18)
    return p.render()


def fig_spectral_efficiency(theme: dict) -> str:
    band_h = 18
    p = Plot(theme, (0, SEPARATION_CM), (0, 16),
             "user position between the two LEDs (cm)",
             "achievable spectral efficiency (bps/Hz)", height=H + band_h + 14)
    p.ih = p.h - PAD["t"] - PAD["b"] - band_h - 14
    p.grid([0, 20, 40, 60, 80, 100, 120, 140, 160], [0, 4, 8, 12, 16],
           xfmt=lambda v: f"{v:g}", yfmt=lambda v: f"{v:g}")
    xs = [SEPARATION_CM * i / 400 for i in range(401)]
    series = [("siso", "SISO, single cell", DASH["siso"], 1.8),
              ("np", "Reuse, no precoding", DASH["np"], 2.2),
              ("zf", "Zero-forcing precoding", DASH["zf"], 2.6),
              ("jt", "Joint transmission", DASH["jt"], 2.6)]
    for key, _, dash, wdt in series:
        p.line(xs, [spectral_efficiency(schemes_at(x)[key]) for x in xs],
               theme[key], wdt, dash)

    # best-scheme band underneath
    segs, counts = [], {"np": 0, "zf": 0, "jt": 0}
    n = 400
    for i in range(n):
        x = SEPARATION_CM * i / n
        k = best_scheme(x)
        counts[k] += 1
        segs.append((x, SEPARATION_CM * (i + 1) / n, theme[k]))
    band_y = PAD["t"] + p.ih + 34
    p.band(segs, band_y, band_h)
    p.text(PAD["l"], band_y - 6, "best scheme by position", theme["ink2"], 11.5, data=False)
    share = " / ".join(f"{k.upper()} {100*v/n:.0f}%" for k, v in counts.items())
    p.text(PAD["l"] + p.iw, band_y - 6, share, theme["ink2"], 11.5, "end", data=False)
    p.legend([(lbl, theme[k], d) for k, lbl, d, _ in series],
             x=PAD["l"] + 14, y=PAD["t"] + 18)
    return p.render()


def fig_measured_results(theme: dict) -> str:
    """Table I as grouped bars: peak, average and minimum per scheme."""
    rows = [("SU-SISO", 14.12, 8.55, 1.31, "siso"),
            ("SU-MISO (JT)", 14.48, 13.86, 13.04, "jt"),
            ("MU-MIMO-NP", 12.82, 7.85, 1.94, "np"),
            ("MU-MIMO-ZF", 14.08, 12.15, 8.78, "zf")]
    p = Plot(theme, (0, len(rows)), (0, 16), "", "spectral efficiency (bps/Hz)")
    p.grid([], [0, 4, 8, 12, 16], yfmt=lambda v: f"{v:g}")
    group_w = p.iw / len(rows)
    bar_w = group_w * 0.21
    for gi, (name, peak, avg, mn, key) in enumerate(rows):
        base = PAD["l"] + gi * group_w + group_w * 0.5
        for bi, (val, opacity) in enumerate(((peak, "0.32"), (avg, "0.62"), (mn, "1"))):
            x = base + (bi - 1) * (bar_w + 5) - bar_w / 2
            y = p.Y(val)
            p.over.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                f'height="{PAD["t"]+p.ih-y:.1f}" fill="{theme[key]}" opacity="{opacity}"/>')
            p.text(x + bar_w / 2, y - 6, f"{val:.2f}", theme["ink2"], 10.5, "middle",
                   data=False)
        p.text(base, PAD["t"] + p.ih + 22, name, theme["ink"], 12.5, "middle", "600",
               data=False)
    p.text(PAD["l"] + p.iw, PAD["t"] + 14,
           "bars, left to right:  peak  /  average  /  minimum",
           theme["ink2"], 12, "end", data=False)
    return p.render()


FIGURES = {
    "channel-gain": fig_channel_gain,
    "ber": fig_ber,
    "sinr-vs-position": fig_sinr_position,
    "spectral-efficiency": fig_spectral_efficiency,
    "measured-results": fig_measured_results,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="figures", help="output directory")
    args = ap.parse_args()

    print(f"Lambertian order m = {lambertian_order(PHI_HALF_DEG):.2f} "
          f"for Phi_half = {PHI_HALF_DEG:g} deg")
    counts = {"np": 0, "zf": 0, "jt": 0}
    for i in range(1000):
        counts[best_scheme(SEPARATION_CM * i / 1000)] += 1
    print("model region split:  "
          + ",  ".join(f"{k.upper()} {v/10:.0f}%" for k, v in counts.items()))
    print("measured region split:  reuse 22%,  ZF 46%,  JT 32%\n")

    for name, fn in FIGURES.items():
        for theme_name, theme in THEMES.items():
            write(os.path.join(args.out, f"{name}-{theme_name}.svg"), fn(theme))
    print("\nDone.")


if __name__ == "__main__":
    main()
