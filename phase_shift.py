# -*- coding: utf-8 -*-
"""
Moduł obliczeniowy przesunięcia fazowego phi(i) oraz phi_min zgodnie ze
specyfikacją EGEA SPECSUS2018 (rozdziały 3.7-3.22 oraz ANEKS 1).

Procedura "MinPhaseShift":
  (1) Z sygnałów (t, F, S) wyznaczamy znaczniki ST_i (pierwsza '1' z S
      w każdym cyklu) - rozdz. 3.8.
  (2) Tworzymy macierz kalibracji dla pustej płyty: dla każdego okresu i
      zapisujemy maxFp(i), Δ_Period(i), gdzie Δ_Period(i) = CalcTOP(i) - ST(i)
      - rozdz. 3.9-3.10.
  (3) Korzystając z macierzy kalibracji, dla pomiaru z pojazdem wyznaczamy
      TOPp(i) = ST(i) + Δ_Period(i) - rozdz. 3.11.
  (4) Z TOPp(i) odtwarzamy syntetyczne F_p(t) (siła płyty) - rozdz. 3.4.
  (5) Wyznaczamy F_ref(i) jako punkt środka między przecięciami X_Fup i X_Fdn
      sygnału F(t) z F_st - rozdz. 3.7 i rys. w rozdz. 3.21.
  (6) Dla każdego okresu obliczamy phi(i) = 2*pi * (F_ref(i) - TOPp(i)) /
      Period(i), a następnie szukamy phi_min w zakresie 18-6 Hz - rozdz. 3.22.

Implementacja jest uproszczoną wersją normy (bez filtru NER z [10]), ale
zachowuje wszystkie kroki logiczne.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.signal import butter, filtfilt


# =============================================================================
#  Parametry przetwarzania
# =============================================================================

@dataclass
class ParametryPrzetwarzania:
    """Parametry algorytmu detekcji phi(i) wg SPECSUS2018."""
    MaxCalcFreq: float = 18.0   # Hz, górna granica zakresu pomiarowego
    MinCalcFreq: float = 6.0    # Hz, dolna granica zakresu pomiarowego
    RFstFMax: float = 25.0      # %, margines górny dla detekcji Fref
    RFstFMin: float = 25.0      # %, margines dolny dla detekcji Fref
    DeltaF: float = 5.0         # Hz, zakres detekcji phi_min poniżej f_res
    f_filt_low: float = 50.0    # Hz, częstotliwość odcięcia filtru
    filt_order: int = 4         # rząd filtru Butterwortha
    FUnderLimPerc: float = 1.0  # %, próg detekcji underflow F(t)


# =============================================================================
#  Funkcje pomocnicze
# =============================================================================

def filtruj_signal(F: np.ndarray, fs: float,
                   f_low: float = 50.0, order: int = 4) -> np.ndarray:
    """Filtr Butterwortha dolnoprzepustowy - usuwa szum, zachowuje fazę
    (filtfilt nie wprowadza opóźnienia)."""
    if fs <= 2 * f_low:
        return F.copy()
    b, a = butter(order, f_low / (fs / 2.0), btype='low')
    return filtfilt(b, a, F)


def wykryj_ST(t: np.ndarray, S: np.ndarray) -> np.ndarray:
    """Detekcja momentów wyzwalania ST_i: indeks pierwszej '1' w każdej grupie
    sąsiadujących jedynek (rozdz. 3.8 normy).

    Zwraca: tablica indeksów (int) w macierzy t.
    """
    S = np.asarray(S).astype(int)
    if S.size == 0:
        return np.array([], dtype=int)
    diff = np.diff(np.concatenate(([0], S)))
    rising = np.where(diff == 1)[0]
    return rising.astype(int)


def wyznacz_okresy(st_indices: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dla każdego ST_i wyznacza początek/koniec okresu i jego częstotliwość.

    Zwraca:
        period_pairs - tablica (N-1, 2): [(idx_start, idx_end), ...]
        f_period     - tablica częstotliwości każdego okresu [Hz]
    """
    if st_indices.size < 2:
        return np.empty((0, 2), dtype=int), np.empty(0)
    pairs = np.column_stack((st_indices[:-1], st_indices[1:]))
    dt_period = t[pairs[:, 1]] - t[pairs[:, 0]]
    f_period = np.where(dt_period > 0, 1.0 / dt_period, 0.0)
    return pairs, f_period


# =============================================================================
#  Kalibracja dynamiczna pustej płyty (rozdz. 3.10)
# =============================================================================

def kalibracja_dynamiczna(t: np.ndarray, Fp: np.ndarray,
                          st_indices: np.ndarray) -> dict:
    """Wyznacza macierz kalibracji dla pustej płyty.

    Dla każdego okresu:
      - maxFp(i)      - maksimum bezwzględnej wartości Fp w okresie,
      - DeltaPeriod(i)- przesunięcie (w sekundach) między ST(i) a momentem
                        wystąpienia maxFp(i) w okresie.

    Zwraca słownik {st_indices, pairs, max_Fp, delta_period, f_period}.
    """
    pairs, f_period = wyznacz_okresy(st_indices, t)
    if pairs.size == 0:
        return {
            'st_indices': st_indices,
            'pairs': pairs,
            'max_Fp': np.empty(0),
            'delta_period': np.empty(0),
            'f_period': f_period,
        }

    max_Fp = np.empty(len(pairs))
    delta_period = np.empty(len(pairs))
    for i, (a, b) in enumerate(pairs):
        seg = Fp[a:b+1]
        if seg.size == 0:
            max_Fp[i] = 0.0
            delta_period[i] = 0.0
            continue
        # CalcTOPp(i): chwila, w której płyta jest najwyżej (rozdz. 3.9 normy).
        # Fp = m_p * z'' - przy z = +d*cos(theta) (konwencja TOP=ST) Fp jest
        # najbardziej ujemne właśnie w TOP, więc używamy argmin.
        k_top = int(np.argmin(seg))
        max_Fp[i] = abs(seg[k_top])
        delta_period[i] = t[a + k_top] - t[a]

    return {
        'st_indices': st_indices,
        'pairs': pairs,
        'max_Fp': max_Fp,
        'delta_period': delta_period,
        'f_period': f_period,
    }


# =============================================================================
#  Wyznaczanie F_ref(i) (rozdz. 3.7)
# =============================================================================

def wyznacz_F_ref(t: np.ndarray, F: np.ndarray, F_st: float,
                  pairs: np.ndarray,
                  params: ParametryPrzetwarzania) -> tuple[np.ndarray, np.ndarray]:
    """Dla każdego okresu wyznacza F_ref(i) - środek między dwoma przecięciami
    F(t) z poziomem F_st (rozdz. 3.7, rys. w 3.21).

    Zwraca:
        F_ref_t   - czas wystąpienia F_ref(i) [s] (NaN dla nieoznaczonych)
        valid     - tablica bool z informacją czy phi(i) dla tego okresu
                    może być policzony.
    """
    F_ref_t = np.full(len(pairs), np.nan)
    valid = np.zeros(len(pairs), dtype=bool)

    for i, (a, b) in enumerate(pairs):
        seg_F = F[a:b+1]
        seg_t = t[a:b+1]
        if seg_F.size < 4:
            continue
        delta_F = seg_F.max() - seg_F.min()
        if delta_F <= 0:
            continue

        # Wymagamy F_st leżącego między minF a maxF z marginesami:
        # Fst_lo = minF + dF*RFstFMin/100 < F_up < maxF - dF*RFstFMax/100 = Fst_hi
        Fst_lo = seg_F.min() + delta_F * params.RFstFMin / 100.0
        Fst_hi = seg_F.max() - delta_F * params.RFstFMax / 100.0
        if not (Fst_lo < F_st < Fst_hi):
            continue

        # Znalezienie przecięć F(t) z F_st (interpolacja liniowa)
        signs = np.sign(seg_F - F_st)
        crossings = np.where(np.diff(signs) != 0)[0]
        if crossings.size < 2:
            continue

        # x_up: przecięcie rosnące, x_dn: przecięcie opadające
        x_up = x_dn = None
        for k in crossings:
            f1, f2 = seg_F[k], seg_F[k+1]
            if f2 == f1:
                continue
            frac = (F_st - f1) / (f2 - f1)
            t_cross = seg_t[k] + frac * (seg_t[k+1] - seg_t[k])
            if f1 < F_st <= f2 and x_up is None:
                x_up = t_cross
            elif f1 >= F_st > f2 and x_dn is None:
                x_dn = t_cross

        if x_up is None or x_dn is None:
            continue

        F_ref_t[i] = 0.5 * (x_up + x_dn)
        valid[i] = True

    return F_ref_t, valid


# =============================================================================
#  Główna funkcja: phi(i) i phi_min
# =============================================================================

def oblicz_phi(t: np.ndarray, F: np.ndarray, S: np.ndarray,
               F_st: float,
               Fp: Optional[np.ndarray] = None,
               params: Optional[ParametryPrzetwarzania] = None) -> dict:
    """Wyznacza phi(i), phi_min i pochodne wskaźniki EGEA.

    Argumenty:
        t   - wektor czasu [s]
        F   - sygnał siły kontaktu opony F(t) = Fr(t) - Fp(t) [N]
        S   - sygnał wyzwalania czujnika płyty (0/1)
        F_st - statyczne obciążenie koła [N]
        Fp  - opcjonalny sygnał siły dynamicznej pustej płyty; jeśli None,
              przyjmujemy uproszczone TOPp(i) = ST(i) + Period(i)/4
              (założenie sinusoidalne).
        params - parametry przetwarzania.

    Zwraca słownik z polami:
        st_indices, pairs, f_period, TOPp, F_ref_t, phi_deg, valid,
        phi_min, f_phi_min, phi_max, F_min, F_max, F_amax, RFA_max, H25, fres.
    """
    if params is None:
        params = ParametryPrzetwarzania()

    t = np.asarray(t, dtype=float)
    F = np.asarray(F, dtype=float)
    S = np.asarray(S).astype(int)

    fs = 1.0 / np.mean(np.diff(t))

    # 1) Filtracja sygnału F(t) (zachowanie fazy dzięki filtfilt)
    F_filt = filtruj_signal(F, fs, params.f_filt_low, params.filt_order)

    # 2) Detekcja ST_i
    st_indices = wykryj_ST(t, S)
    pairs, f_period = wyznacz_okresy(st_indices, t)

    # 3) Macierz kalibracji dynamicznej (jeśli mamy Fp)
    if Fp is not None:
        Fp = np.asarray(Fp, dtype=float)
        kal = kalibracja_dynamiczna(t, Fp, st_indices)
        delta_period = kal['delta_period']
    else:
        # Założenie domyślne (brak Fp): ST_i zgrany z TOP płyty -> delta = 0.
        # Konwencja zgodna ze sprzętem EGEA (rozdz. 3.8 normy).
        delta_period = np.zeros(len(pairs)) if pairs.size else np.empty(0)

    # 4) TOPp(i) = ST(i) + DeltaPeriod(i)
    if pairs.size:
        TOPp = t[pairs[:, 0]] + delta_period
    else:
        TOPp = np.empty(0)

    # 5) F_ref(i)
    F_ref_t, valid = wyznacz_F_ref(t, F_filt, F_st, pairs, params)

    # 6) phi(i) = 2*pi * (F_ref(i) - TOPp(i)) / Period(i)
    phi_deg = np.full(len(pairs), np.nan)
    for i, ((a, b), v) in enumerate(zip(pairs, valid)):
        if not v:
            continue
        period = t[b] - t[a]
        if period <= 0:
            continue
        dt_phase = F_ref_t[i] - TOPp[i]
        phi_rad = 2 * np.pi * dt_phase / period
        # Sprowadzamy do zakresu (0, 360)
        phi_deg_val = np.degrees(phi_rad) % 360.0
        if phi_deg_val > 180:
            phi_deg_val = 360 - phi_deg_val
        phi_deg[i] = phi_deg_val

    # 7) phi_min w zakresie pomiarowym (Min..MaxCalcFreq)
    mask = (f_period >= params.MinCalcFreq) & \
           (f_period <= params.MaxCalcFreq) & valid & ~np.isnan(phi_deg)
    if mask.any():
        idx_min = int(np.argmin(np.where(mask, phi_deg, np.inf)))
        phi_min_val = float(phi_deg[idx_min])
        f_phi_min = float(f_period[idx_min])
    else:
        phi_min_val = float('nan')
        f_phi_min = float('nan')

    # 8) phi_max (przy 18 Hz)
    mask_18 = (f_period >= params.MaxCalcFreq - 1.0) & \
              (f_period <= params.MaxCalcFreq + 1.0) & valid & ~np.isnan(phi_deg)
    phi_max_val = float(np.nanmax(phi_deg[mask_18])) if mask_18.any() else float('nan')

    # 9) Wartości amplitudowe F(t) - rozdz. 3.15-3.18
    idx_meas = np.where(
        (f_period >= params.MinCalcFreq) & (f_period <= params.MaxCalcFreq)
    )[0]
    if idx_meas.size:
        seg_starts = pairs[idx_meas, 0]
        seg_ends = pairs[idx_meas, 1]
        i_lo = int(seg_starts.min())
        i_hi = int(seg_ends.max())
        F_in_range = F_filt[i_lo:i_hi+1]
        F_min = float(F_in_range.min())
        F_max = float(F_in_range.max())
        F_under_lim = F_st * params.FUnderLimPerc / 100.0
        if F_min >= F_under_lim:
            F_amax = F_st - F_min
            idx_fres = i_lo + int(np.argmin(F_in_range))
        else:
            F_amax = F_max - F_st
            idx_fres = i_lo + int(np.argmax(F_in_range))
        # f_res - częstotliwość w punkcie F_amax
        fres = float(_freq_in_idx(idx_fres, pairs, f_period))
        RFA_max = F_amax / F_st * 100.0
    else:
        F_min = F_max = F_amax = RFA_max = fres = float('nan')

    # 10) H25 - amplituda przy stabilizacji 25 Hz (rozdz. 3.19)
    idx_25 = np.where((f_period >= 24.0) & (f_period <= 26.0))[0]
    if idx_25.size:
        dF_25 = np.array([
            F_filt[pairs[i, 0]:pairs[i, 1]+1].max() -
            F_filt[pairs[i, 0]:pairs[i, 1]+1].min()
            for i in idx_25
        ])
        H25 = float(np.mean(dF_25) / 2.0)
    else:
        H25 = float('nan')

    return {
        'F_filt': F_filt,
        'st_indices': st_indices,
        'pairs': pairs,
        'f_period': f_period,
        'TOPp': TOPp,
        'F_ref_t': F_ref_t,
        'phi_deg': phi_deg,
        'valid': valid,
        'phi_min': phi_min_val,
        'f_phi_min': f_phi_min,
        'phi_max': phi_max_val,
        'F_min': F_min,
        'F_max': F_max,
        'F_amax': F_amax,
        'RFA_max': RFA_max,
        'H25': H25,
        'fres': fres,
        'delta_period': delta_period,
    }


def _freq_in_idx(idx: int, pairs: np.ndarray, f_period: np.ndarray) -> float:
    """Zwraca częstotliwość okresu, do którego należy podany indeks próbki."""
    for k, (a, b) in enumerate(pairs):
        if a <= idx <= b:
            return float(f_period[k])
    return float('nan')


# =============================================================================
#  Sztywność opony rig (rozdz. 3.20)
# =============================================================================

def oblicz_rig(H25_N: float, ep_mm: float = 3.0,
               a_rig: float = 0.571, b_rig: float = 46.0) -> float:
    """Sztywność opony rig = a_rig * H25/ep + b_rig [N/mm]."""
    if not np.isfinite(H25_N) or ep_mm <= 0:
        return float('nan')
    return a_rig * H25_N / ep_mm + b_rig


# =============================================================================
#  Test modułu
# =============================================================================

if __name__ == "__main__":
    from egea_suspension_model import ModelCwiartkowy

    print("Generuję syntetyczny pomiar (model 2DOF)...")
    model = ModelCwiartkowy()
    dane = model.symuluj(fs=2000.0)
    print(f"  F_st = {dane['F_st']:.1f} N, próbek = {len(dane['t'])}")

    print("\nLiczę phi_min wg procedury EGEA...")
    wynik = oblicz_phi(
        t=dane['t'],
        F=dane['F_t'],
        S=dane['S'],
        F_st=dane['F_st'],
        Fp=dane['F_p'],
    )
    print(f"  liczba okresów = {len(wynik['phi_deg'])}")
    print(f"  liczba poprawnych phi(i) = {int(wynik['valid'].sum())}")
    print(f"  phi_min  = {wynik['phi_min']:.2f}° przy f = {wynik['f_phi_min']:.2f} Hz")
    print(f"  phi_max  = {wynik['phi_max']:.2f}° (przy ~18 Hz)")
    print(f"  RFA_max  = {wynik['RFA_max']:.2f} %")
    print(f"  F_amax   = {wynik['F_amax']:.1f} N (przy f_res = {wynik['fres']:.2f} Hz)")
    print(f"  H25      = {wynik['H25']:.1f} N -> rig = {oblicz_rig(wynik['H25']):.1f} N/mm")
