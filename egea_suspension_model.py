# -*- coding: utf-8 -*-
"""
Model symulacyjny stanowiska EGEA do badania zawieszenia pojazdu.

Implementacja zgodna ze specyfikacją EGEA SPECSUS2018:
- Model ćwiartkowy (Quarter-Car, 2 stopnie swobody) - pełna symulacja stanowiska.
- Model jednomasowy (1 stopień swobody) - do analizy zależności phi_min(c).
- Funkcja zmienności częstotliwości wg rozdziału 5.4 normy.

Wektor stanu modelu 2DOF: X = [x_m, x_M, v_m, v_M]^T, gdzie:
    x_m, v_m - położenie/prędkość masy nieresorowanej (koło),
    x_M, v_M - położenie/prędkość masy resorowanej (nadwozie).

Wymuszenie kinematyczne płyty:  z(t) = -d * cos(theta(t)),
   gdzie theta(t) jest fazą cykli o zmiennej częstotliwości f(t).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.integrate import odeint


G = 9.81  # przyspieszenie ziemskie [m/s^2]


# =============================================================================
#  Parametry domyślne wg normy EGEA (rozdz. 5.4, ANEKS 1)
# =============================================================================

@dataclass
class ParametryEGEA:
    """Parametry funkcji zmienności częstotliwości i pomiaru wg SPECSUS2018."""
    MaxCalcFreq: float = 18.0      # górna granica zakresu pomiarowego [Hz]
    MinCalcFreq: float = 6.0       # dolna granica zakresu pomiarowego [Hz]
    dTmeas: float = 7.5            # minimalny czas zjazdu 18 -> 6 Hz [s]
    dTfMaxSlope: float = 3.0       # maksymalne nachylenie zjazdu [Hz/s]
    f_start_max: float = 25.0      # częstotliwość stabilizacji [Hz]
    AC_phi_min: float = 35.0       # absolutne kryterium phi_min [deg]
    RFstFMax: float = 25.0         # margines górny przy detekcji Fref [%]
    RFstFMin: float = 25.0         # margines dolny przy detekcji Fref [%]
    DeltaF: float = 5.0            # zakres detekcji phi_min poniżej f_res [Hz]
    h_PS_mm: float = 6.0           # amplituda peak-to-peak płyty [mm]


# =============================================================================
#  Model ćwiartkowy (2 stopnie swobody) - SPRAWNY AMORTYZATOR PRZEDNI
# =============================================================================

@dataclass
class ModelCwiartkowy:
    """Model 2DOF zgodny z normą EGEA, użyty do generowania syntetycznych
    przebiegów F(t) i sygnału wyzwalania S(t) (ST_i)."""

    # Parametry mechaniczne (przykład: oś przednia samochodu osobowego)
    M: float = 346.0       # masa resorowana [kg]
    m: float = 36.0        # masa nieresorowana [kg]
    kM: float = 25570.0    # sztywność zawieszenia [N/m]
    km: float = 253161.0   # sztywność opony [N/m]
    cM: float = 1474.0     # tłumienie amortyzatora [N*s/m]
    cm: float = 150.0      # tłumienie opony [N*s/m]

    # Parametry stanowiska
    d: float = 0.003       # amplituda wymuszenia (3 mm, p-p = 6 mm)
    m_p: float = 20.0      # masa płyty wzbudnika [kg] (do korekcji dynamicznej)

    # Parametry EGEA
    egea: ParametryEGEA = field(default_factory=ParametryEGEA)

    def __post_init__(self) -> None:
        # Masy występują w mianowniku macierzy A oraz wektora wymuszenia B(t),
        # więc muszą być dodatnie. Tłumienia i sztywności mogą być zerowe,
        # ale ujemne wartości fizycznie nie mają sensu.
        if self.M <= 0 or self.m <= 0:
            raise ValueError(
                f"Masy muszą być dodatnie (otrzymano M={self.M}, m={self.m})."
            )
        if self.kM < 0 or self.km < 0:
            raise ValueError(
                f"Sztywności nie mogą być ujemne (kM={self.kM}, km={self.km})."
            )
        if self.cM < 0 or self.cm < 0:
            raise ValueError(
                f"Tłumienia nie mogą być ujemne (cM={self.cM}, cm={self.cm})."
            )

        self.F_st = (self.M + self.m) * G
        # Macierz stanu modelu liniowego 2DOF
        self.A = np.array([
            [0.0,                       0.0,             1.0,                  0.0           ],
            [0.0,                       0.0,             0.0,                  1.0           ],
            [-(self.km + self.kM)/self.m, self.kM/self.m, -(self.cm + self.cM)/self.m, self.cM/self.m],
            [ self.kM/self.M,           -self.kM/self.M,  self.cM/self.M,      -self.cM/self.M ],
        ])

    # ---------- Funkcja zmienności częstotliwości (rozdz. 5.4 normy) ---------
    def dT25(self) -> float:
        """Minimalny czas stabilizacji 25 Hz: dT25 = Fst*0.16 + 1200 [ms]."""
        return (self.F_st * 0.16 + 1200.0) / 1000.0

    def czestotliwosc_docelowa(self, t_val: float) -> float:
        """Docelowy profil częstotliwości f(t) wg rozdziału 5.4 normy.

        Fazy:
          1) rozruch 0 -> 25 Hz przez 2 s,
          2) stabilizacja 25 Hz przez dT25,
          3) przejście 25 -> 18 Hz w 2 s,
          4) rampa pomiarowa 18 -> 6 Hz w dTmeas,
          5) wygaszenie 6 -> 0 Hz w 3 s.
        """
        T1 = 2.0
        T2_end = T1 + self.dT25()
        T_prep = 2.0
        T3_start = T2_end + T_prep
        T_meas = self.egea.dTmeas
        T3_end = T3_start + T_meas
        T_ext = 3.0
        T4_end = T3_end + T_ext

        if t_val < T1:
            # Faza rozruchu: liniowo 2 -> 25 Hz (start od 2 Hz aby uniknąć
            # nieskończonego okresu na początku)
            return 2.0 + ((self.egea.f_start_max - 2.0) / T1) * t_val
        if t_val < T2_end:
            return self.egea.f_start_max
        if t_val < T3_start:
            return self.egea.f_start_max - ((t_val - T2_end) / T_prep) * \
                   (self.egea.f_start_max - self.egea.MaxCalcFreq)
        if t_val < T3_end:
            return self.egea.MaxCalcFreq - ((t_val - T3_start) / T_meas) * \
                   (self.egea.MaxCalcFreq - self.egea.MinCalcFreq)
        if t_val < T4_end:
            return self.egea.MinCalcFreq - ((t_val - T3_end) / T_ext) * \
                   self.egea.MinCalcFreq
        return 0.0

    def czas_calkowity(self) -> float:
        """Sumaryczny czas trwania symulacji [s]."""
        return 2.0 + self.dT25() + 2.0 + self.egea.dTmeas + 3.0

    # ---------- Generacja wymuszenia kinematycznego płyty z(t) ---------------
    def _generuj_wymuszenie(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
        """Tworzy próbki z(t), z'(t), f_step(t) oraz indeksy ST_i.

        Konwencja: w obrębie cyklu z(t) = +d * cos(theta), gdzie theta ∈ [0, 2π].
        Oznacza to, że ST_i (początek cyklu) odpowiada **najwyższemu**
        położeniu płyty (TOP), zgodnie z konwencją sprzętową EGEA
        (rozdz. 3.8: ST = "for instance highest position").

        Częstotliwość pozostaje stała w obrębie cyklu (cykliczność wg EGEA).
        """
        z = np.zeros_like(t)
        z_dot = np.zeros_like(t)
        f_step = np.zeros_like(t)
        st_indices: list[int] = []

        N = len(t)
        i = 0
        t_cycle_start = t[0]
        f_cycle = self.czestotliwosc_docelowa(t_cycle_start)
        if f_cycle <= 0:
            f_cycle = 1e-6

        while i < N:
            period = 1.0 / f_cycle if f_cycle > 0 else float('inf')
            t_cycle_end = t_cycle_start + period

            if not st_indices or st_indices[-1] != i:
                st_indices.append(i)

            while i < N and t[i] < t_cycle_end:
                theta = 2 * np.pi * (t[i] - t_cycle_start) / period
                theta_dot = 2 * np.pi / period
                # z = +d*cos(theta): TOP w theta=0, BOTTOM w theta=pi
                z[i] = self.d * np.cos(theta)
                z_dot[i] = -self.d * np.sin(theta) * theta_dot
                f_step[i] = f_cycle
                i += 1

            if i >= N:
                break

            t_cycle_start = t[i]
            f_target = self.czestotliwosc_docelowa(t_cycle_start)
            if f_target <= 0:
                z[i:] = 0.0
                z_dot[i:] = 0.0
                f_step[i:] = 0.0
                break
            f_cycle = f_target

        return z, z_dot, f_step, st_indices

    # ---------- Pełna symulacja stanowiska -----------------------------------
    def symuluj(self, fs: float = 10000.0) -> dict:
        """Wykonuje pełną symulację 2DOF.

        Zwraca słownik z polami: t, z, z_dot, x_m, x_M, v_m, v_M,
        F_t (siła kontaktu opony z płytą), F_p (siła płyty pustej),
        f_step, S (sygnał ST 0/1), st_indices, F_st, dt, eusama.
        """
        dt = 1.0 / fs
        T_total = self.czas_calkowity()
        t = np.arange(0, T_total, dt)

        z, z_dot, f_step, st_indices = self._generuj_wymuszenie(t)

        # Sygnał ST(i) jako szereg impulsów 0/1 (jedynka na pierwszej próbce cyklu)
        S = np.zeros_like(t, dtype=np.int8)
        for k in st_indices:
            if 0 <= k < len(S):
                S[k] = 1

        # Całkowanie równań ruchu modelu 2DOF
        def f_rhs(X, t_val):
            idx = int(round(t_val * fs))
            if idx < 0:
                idx = 0
            elif idx >= len(z):
                idx = len(z) - 1
            z_val = z[idx]
            z_dot_val = z_dot[idx]
            B = np.array([
                0.0,
                0.0,
                (self.km * z_val + self.cm * z_dot_val) / self.m,
                0.0,
            ])
            return self.A @ X + B

        X0 = np.zeros(4)
        X_sol = odeint(f_rhs, X0, t, mxstep=5000)

        x_m = X_sol[:, 0]
        x_M = X_sol[:, 1]
        v_m = X_sol[:, 2]
        v_M = X_sol[:, 3]

        # Dynamiczna część siły kontaktu opony (norma 3.6): F(t) = Fst + Fdyn
        F_dyn = self.km * (x_m - z) + self.cm * (v_m - z_dot)
        F_t = self.F_st + F_dyn

        # Siła bezwładności płyty (norma 3.4): Fp(t) = m_p * d2z/dt2
        d2z = np.gradient(z_dot, dt)
        F_p = self.m_p * d2z

        # Wskaźnik EUSAMA: min F_t / F_st * 100 % w zakresie pomiarowym
        idx_meas = np.where(
            (f_step <= self.egea.MaxCalcFreq) & (f_step >= self.egea.MinCalcFreq)
        )[0]
        if idx_meas.size:
            eusama = (np.min(F_t[idx_meas]) / self.F_st) * 100.0
        else:
            eusama = 0.0

        return {
            't': t,
            'z': z,
            'z_dot': z_dot,
            'x_m': x_m,
            'x_M': x_M,
            'v_m': v_m,
            'v_M': v_M,
            'F_t': F_t,
            'F_p': F_p,
            'f_step': f_step,
            'S': S,
            'st_indices': np.array(st_indices, dtype=int),
            'F_st': self.F_st,
            'dT25': self.dT25(),
            'dt': dt,
            'eusama': eusama,
        }


# =============================================================================
#  Model 1DOF do analizy zależności phi_min(c)
# =============================================================================

@dataclass
class ModelJednomasowy:
    """Model 1 stopnia swobody (m, c, k) na wymuszeniu z(t) = -d*cos(omega*t).

    Równanie ruchu: m*x'' + c*(x' - z') + k*(x - z) = 0  =>
                    m*x'' + c*x' + k*x = c*z' + k*z.

    W trybie EGEA częstotliwość zmienia się w zakresie 18 -> 6 Hz.
    Wykorzystywane do analizy zależności phi_min(c).
    """
    m: float = 382.0       # masa zastępcza koła z częścią nadwozia [kg]
    k: float = 253161.0    # sztywność opony [N/m]
    c: float = 1474.0      # współczynnik tłumienia [N*s/m]
    d: float = 0.003       # amplituda płyty [m]

    def __post_init__(self) -> None:
        if self.m <= 0:
            raise ValueError(f"Masa musi być dodatnia (m={self.m}).")
        if self.k <= 0:
            raise ValueError(f"Sztywność musi być dodatnia (k={self.k}).")
        if self.c < 0:
            raise ValueError(f"Tłumienie nie może być ujemne (c={self.c}).")

    def odpowiedz_ustalona(self, omega: float) -> tuple[float, float]:
        """Amplituda i faza odpowiedzi ustalonej dla wymuszenia harmonicznego.

        Dla z(t) = -d*cos(omega*t) odpowiedź ustalona ma postać
            x(t) = X * cos(omega*t - phi).
        Zwraca (X, phi) w radianach.
        """
        # Macierzowy zapis: m*x'' + c*x' + k*x = c*z' + k*z
        # z(t) = -d*cos(wt) -> z' = d*w*sin(wt)
        # Wymuszenie: F(t) = -k*d*cos(wt) + c*d*w*sin(wt)
        H_real = self.k - self.m * omega**2
        H_imag = self.c * omega
        # F = A*cos(wt) + B*sin(wt), A = -k*d, B = c*d*w
        A = -self.k * self.d
        B = self.c * self.d * omega
        F_amp = np.hypot(A, B)
        F_phase = np.arctan2(-B, A)  # F(t) = F_amp * cos(wt + F_phase)
        H_amp = np.hypot(H_real, H_imag)
        H_phase = np.arctan2(H_imag, H_real)
        X = F_amp / H_amp
        phi = H_phase - F_phase
        return X, phi

    def sila_kontaktu(self, omega: float) -> tuple[float, float, float]:
        """Amplituda dynamicznej siły kontaktu opony oraz przesunięcie fazowe
        między płytą a siłą F(t).

        F_dyn(t) = k*(x - z) + c*(x' - z').
        Zwraca (amp_F, faza_F, phi_shift), gdzie phi_shift to różnica faz
        między F(t) a wymuszeniem z(t) (w stopniach, zakres 0..180).
        """
        X, phi_x = self.odpowiedz_ustalona(omega)
        # x(t) = X*cos(wt - phi_x), z(t) = -d*cos(wt)
        # x - z = X*cos(wt - phi_x) + d*cos(wt)
        # rozkład w bazie cos(wt), sin(wt):
        a_xz = X * np.cos(phi_x) + self.d
        b_xz = X * np.sin(phi_x)
        # x' - z' = -X*w*sin(wt - phi_x) - d*w*sin(wt)
        # Z tożsamości -sin(wt - phi) = sin(phi)*cos(wt) - cos(phi)*sin(wt)
        # rozkład w bazie cos(wt), sin(wt):
        a_v = X * omega * np.sin(phi_x)
        b_v = -X * omega * np.cos(phi_x) - self.d * omega
        # F_dyn = k*(x-z) + c*(x'-z')
        A = self.k * a_xz + self.c * a_v
        B = self.k * b_xz + self.c * b_v
        amp_F = np.hypot(A, B)
        faza_F = np.arctan2(B, A)
        # Przesunięcie fazowe między F(t) a -z(t) (płyta dochodzi do góry)
        # z(t) = -d*cos(wt) ma maksimum przy wt = pi (TOP płyty na -d nie ma
        # sensu fizycznie; bierzemy fazę względem maksimum wzniesienia płyty).
        # Maksimum -z(t) (płyta najwyżej) jest przy wt = 0.
        # F_dyn = amp_F*cos(wt - faza_F)
        phi_shift = np.degrees(faza_F)
        if phi_shift < 0:
            phi_shift += 360
        if phi_shift > 180:
            phi_shift = 360 - phi_shift
        return amp_F, faza_F, phi_shift

    def krzywa_phi(self, f_min: float = 6.0, f_max: float = 18.0,
                   n: int = 200) -> tuple[np.ndarray, np.ndarray]:
        """Krzywa phi(f) dla zakresu częstotliwości [f_min, f_max] Hz."""
        f = np.linspace(f_min, f_max, n)
        phi = np.empty_like(f)
        for i, fi in enumerate(f):
            _, _, phi[i] = self.sila_kontaktu(2 * np.pi * fi)
        return f, phi

    def phi_min(self, f_min: float = 6.0, f_max: float = 18.0,
                n: int = 400) -> tuple[float, float]:
        """Wyznacza minimum phi w zakresie [f_min, f_max].
        Zwraca (phi_min [deg], f_phi_min [Hz])."""
        f, phi = self.krzywa_phi(f_min, f_max, n)
        idx = int(np.argmin(phi))
        return float(phi[idx]), float(f[idx])


# =============================================================================
#  Generator syntetycznego pomiaru CSV
# =============================================================================

def generuj_przyklad_csv(sciezka: str, fs: float = 1000.0,
                          model: Optional[ModelCwiartkowy] = None) -> None:
    """Wygeneruj plik CSV (t, F, S) na podstawie modelu 2DOF.

    Częstotliwość 1 kHz jest wystarczająca dla detekcji 18 Hz wg twierdzenia
    Nyquista (>> 36 Hz), a jednocześnie nie generuje gigantycznych plików.
    """
    if model is None:
        model = ModelCwiartkowy()
    wyniki = model.symuluj(fs=fs)
    import pandas as pd
    df = pd.DataFrame({
        't': wyniki['t'],
        'F': wyniki['F_t'],
        'S': wyniki['S'],
    })
    df.to_csv(sciezka, index=False)


# =============================================================================
#  Skrypt diagnostyczny (uruchomienie bezpośrednie)
# =============================================================================

if __name__ == "__main__":
    print("Uruchamiam diagnostyczną symulację modelu 2DOF...")
    model = ModelCwiartkowy()
    wynik = model.symuluj(fs=5000.0)
    print(f"  F_st              = {wynik['F_st']:.1f} N")
    print(f"  dT25              = {wynik['dT25']:.3f} s")
    print(f"  liczba próbek     = {len(wynik['t'])}")
    print(f"  liczba cykli (ST) = {len(wynik['st_indices'])}")
    print(f"  EUSAMA            = {wynik['eusama']:.2f} %")

    print("\nAnaliza zależności phi_min(c) (model 1DOF)...")
    c_values = [400, 800, 1200, 1474, 2000, 3000]
    for c in c_values:
        model1 = ModelJednomasowy(c=c)
        phi_min, f_at = model1.phi_min()
        print(f"  c = {c:4d} N*s/m  ->  phi_min = {phi_min:6.2f}°  przy f = {f_at:.2f} Hz")
