# -*- coding: utf-8 -*-
"""
Aplikacja Streamlit: stanowisko EGEA do diagnostyki zawieszenia pojazdu.

Trzy tryby pracy:
  1) Symulacja modelu ćwiartkowego (2DOF) wg normy EGEA SPECSUS2018.
  2) Import pomiaru z pliku CSV (kolumny: t, F, S) i wyznaczenie phi_min.
  3) Analiza zależności phi_min(c) - parametryczne badanie wpływu tłumienia.

Wszystkie wzory matematyczne renderowane są w LaTeX (st.latex / $...$).
"""

import io
from string import Template

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from egea_suspension_model import ModelCwiartkowy, ModelJednomasowy
from phase_shift import ParametryPrzetwarzania, oblicz_phi, oblicz_rig


def _wybierz_kolumne(cols: list[str], wzorce: list[str]) -> int:
    """Zwraca indeks pierwszej kolumny pasującej do dowolnego wzorca
    (case-insensitive, dopasowanie po podciągu). -1 gdy brak trafień."""
    cols_low = [c.lower() for c in cols]
    for wz in wzorce:
        wz_low = wz.lower()
        for i, c in enumerate(cols_low):
            if wz_low in c:
                return i
    return -1


def kategoryzuj_amortyzator(phi_min: float, eusama: float,
                             F_min: float) -> str:
    """Łączne kryterium diagnostyczne dla modelu 2DOF.

    Zwraca jeden z: 'NIESPRAWNY', 'GRANICZNY', 'SPRAWNY'.
    Kolejność warunków musi być spójna z gałęziami komunikatów w UI.
    """
    if F_min < 0.0:
        return "NIESPRAWNY"
    if eusama < 30.0:
        return "NIESPRAWNY"
    if phi_min < 25.0:
        return "NIESPRAWNY"
    if phi_min < 35.0:
        return "GRANICZNY"
    if eusama < 45.0:
        return "GRANICZNY"
    return "SPRAWNY"


# =============================================================================
#  Konfiguracja strony
# =============================================================================

st.set_page_config(
    page_title="Stanowisko EGEA – Diagnostyka Zawieszenia",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Stanowisko EGEA – Diagnostyka Zawieszenia Pojazdu")
st.markdown(
    r"""
Implementacja metody minimalnego przesunięcia fazowego $\varphi_{\min}$
zgodnie ze specyfikacją **EGEA SPECSUS2018** (model ćwiartkowy 2 DOF
oraz model jednomasowy 1 DOF do analizy parametrycznej).
"""
)


# =============================================================================
#  Panel boczny – wybór trybu i parametrów
# =============================================================================

st.sidebar.header("Konfiguracja")

tryb = st.sidebar.radio(
    "Tryb pracy:",
    options=("Symulacja 2DOF", "Import pomiaru (CSV)", "Analiza φₘᵢₙ(c)"),
)


def _panel_parametrow_pojazdu(prefix: str = "") -> dict:
    """Wspólny widget do parametrów modelu.

    Wartości muszą być dodatnie (masy i sztywności występują w mianowniku
    macierzy stanu A). Tłumienia mogą być zerowe (układ nietłumiony).
    """
    st.sidebar.subheader("Parametry pojazdu")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        M = st.number_input(r"$M$ – masa resorowana [kg]",
                            value=346.0, step=1.0, min_value=1.0,
                            key=f"{prefix}M")
        m = st.number_input(r"$m$ – masa nieresorowana [kg]",
                            value=36.0, step=1.0, min_value=1.0,
                            key=f"{prefix}m")
    with col2:
        kM = st.number_input(r"$k_M$ – sztywność zawieszenia [N/m]",
                              value=25570.0, step=100.0, min_value=1.0,
                              key=f"{prefix}kM")
        km = st.number_input(r"$k_m$ – sztywność opony [N/m]",
                              value=253161.0, step=1000.0, min_value=1.0,
                              key=f"{prefix}km")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        cM = st.number_input(r"$c_M$ – tłumienie amortyzatora [N·s/m]",
                              value=1474.0, step=10.0, min_value=0.0,
                              key=f"{prefix}cM")
    with col4:
        cm = st.number_input(r"$c_m$ – tłumienie opony [N·s/m]",
                              value=150.0, step=10.0, min_value=0.0,
                              key=f"{prefix}cm")
    return {"M": M, "m": m, "kM": kM, "km": km, "cM": cM, "cm": cm}


# =============================================================================
#  TRYB 1: Symulacja modelu 2DOF
# =============================================================================

if tryb == "Symulacja 2DOF":
    par = _panel_parametrow_pojazdu()

    st.sidebar.subheader("Parametry stanowiska")
    d_mm = st.sidebar.number_input(r"Amplituda płyty $d$ [mm]",
                                    value=3.0, step=0.1, min_value=0.1,
                                    format="%.2f")
    m_p = st.sidebar.number_input(r"Masa płyty $m_p$ [kg]",
                                   value=20.0, step=1.0, min_value=0.1)
    fs = st.sidebar.number_input(r"Częstotliwość próbkowania $f_s$ [Hz]",
                                  value=2000.0, step=500.0, min_value=500.0)

    # st.sidebar.caption(
    #     "💡 **Aby zasymulować niesprawny amortyzator:**\n\n"
    #     "Tłumienie opony $c_m$ samo zapewnia silne tłumienie rezonansu koła, "
    #     "więc samo obniżenie $c_M$ nie wystarcza. Wypróbuj jednocześnie:\n"
    #     "- $c_M = 100$–$300$ N·s/m\n"
    #     "- $c_m = 10$–$30$ N·s/m\n\n"
    #     "Wskaźnik **EUSAMA** spadnie wtedy do wartości <30 % lub nawet "
    #     "ujemnych (koło traci kontakt z płytą) – uznajemy to za "
    #     "amortyzator **niesprawny**.\n\n"
    #     r"Dla klarownej zależności $\varphi_{\min}(c)$ użyj trybu "
    #     r"**Analiza φₘᵢₙ(c)**."
    # )

    if st.sidebar.button("Uruchom symulację", use_container_width=True):
        with st.spinner("Trwa całkowanie równań ruchu 2 DOF…"):
            model = ModelCwiartkowy(
                M=par["M"], m=par["m"], kM=par["kM"], km=par["km"],

                cM=par["cM"], cm=par["cm"],
                d=d_mm / 1000.0, m_p=m_p,
            )
            wyniki = model.symuluj(fs=fs)
            analiza = oblicz_phi(
                t=wyniki['t'],
                F=wyniki['F_t'],
                S=wyniki['S'],
                F_st=wyniki['F_st'],
                Fp=wyniki['F_p'],
            )
        st.session_state["sym_wyniki"] = wyniki
        st.session_state["sym_analiza"] = analiza
        st.success("Symulacja zakończona.")

    # ---- Sekcja teoretyczna - zawsze widoczna --------------------------
    with st.expander("Model matematyczny 2 DOF (rozwiń)", expanded=False):
        st.markdown("**Wektor stanu:**")
        st.latex(r"\mathbf{X}(t) = \begin{bmatrix} x_m \\ x_M \\ \dot{x}_m \\ \dot{x}_M \end{bmatrix}")

        st.markdown("**Równania ruchu mas nieresorowanej i resorowanej (II zasada Newtona):**")
        st.latex(r"""
        \begin{aligned}
        m\,\ddot{x}_m &= -(k_M+k_m)\,x_m + k_M\,x_M - (c_M+c_m)\,\dot{x}_m
                       + c_M\,\dot{x}_M + k_m\,z(t) + c_m\,\dot{z}(t) \\
        M\,\ddot{x}_M &= k_M\,x_m - k_M\,x_M + c_M\,\dot{x}_m - c_M\,\dot{x}_M
        \end{aligned}
        """)

        st.markdown("**Postać macierzowa** $\\dot{\\mathbf{X}} = \\mathbf{A}\\mathbf{X} + \\mathbf{B}(t)$:")
        st.latex(r"""
        \mathbf{A} = \begin{bmatrix}
        0 & 0 & 1 & 0 \\
        0 & 0 & 0 & 1 \\
        -\dfrac{k_m+k_M}{m} & \dfrac{k_M}{m} & -\dfrac{c_m+c_M}{m} & \dfrac{c_M}{m} \\[6pt]
        \dfrac{k_M}{M} & -\dfrac{k_M}{M} & \dfrac{c_M}{M} & -\dfrac{c_M}{M}
        \end{bmatrix},\qquad
        \mathbf{B}(t) = \begin{bmatrix} 0 \\ 0 \\ \dfrac{k_m\,z(t) + c_m\,\dot{z}(t)}{m} \\ 0 \end{bmatrix}
        """)

        st.markdown("**Wymuszenie kinematyczne płyty:**")
        st.latex(r"z(t) = d\cos(\theta(t)),\qquad \theta(t) = \int_0^t 2\pi f(\tau)\,d\tau")

        st.markdown("**Pionowa siła kontaktu opony z płytą (rozdz. 3.6 normy):**")
        st.latex(r"F(t) = F_{st} + \underbrace{k_m(x_m-z) + c_m(\dot{x}_m-\dot{z})}_{F_{dyn}(t)}")

        st.markdown("**Siła pustej płyty (rozdz. 3.4 normy):**")
        st.latex(r"F_p(t) = m_p\,\ddot{z}(t)")

        st.markdown("**Statyczne obciążenie koła:**")
        st.latex(r"F_{st} = (M + m)\,g")

    if "sym_wyniki" in st.session_state:
        wyniki = st.session_state["sym_wyniki"]
        analiza = st.session_state["sym_analiza"]

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Wyniki kluczowe",
            "Przebiegi czasowe",
            "Krzywa φ(f)",
            "Parametry EGEA",
            "Eksport"
        ])

        # ---- TAB 1: wskaźniki diagnostyczne -----------------------------
        with tab1:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("F_st [N]", f"{wyniki['F_st']:.0f}")
            phi_min = analiza['phi_min']
            c2.metric("φ_min [°]",
                      f"{phi_min:.1f}" if np.isfinite(phi_min) else "—")
            c3.metric("EUSAMA [%]", f"{wyniki['eusama']:.1f}")
            c4.metric("RFA_max [%]",
                      f"{analiza['RFA_max']:.1f}" if np.isfinite(analiza['RFA_max']) else "—")

            st.markdown("---")
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("f_φmin [Hz]",
                      f"{analiza['f_phi_min']:.2f}" if np.isfinite(analiza['f_phi_min']) else "—")
            c6.metric("f_res [Hz]",
                      f"{analiza['fres']:.2f}" if np.isfinite(analiza['fres']) else "—")
            c7.metric("H25 [N]",
                      f"{analiza['H25']:.0f}" if np.isfinite(analiza['H25']) else "—")
            rig = oblicz_rig(analiza['H25'])
            c8.metric("rig [N/mm]",
                      f"{rig:.0f}" if np.isfinite(rig) else "—")

            st.markdown("### Wzory wyznaczonych wskaźników")
            colA, colB = st.columns(2)
            with colA:
                st.markdown("**Minimalne przesunięcie fazowe:**")
                st.latex(r"\varphi_{\min} = \min_{f\in[6,\,18]\,\mathrm{Hz}} \varphi(f)")
                st.markdown("**Przesunięcie fazowe okresu $i$:**")
                st.latex(r"\varphi(i) = \frac{2\pi\bigl(F_{\mathrm{ref}}(i) - TOP_p(i)\bigr)}{\mathrm{Period}(i)}")
                st.markdown("**Wskaźnik EUSAMA (historyczny):**")
                st.latex(r"\mathrm{EUSAMA} = \frac{F_{\min}}{F_{st}}\cdot 100\,\%")
            with colB:
                st.markdown("**Względna amplituda maksymalna:**")
                st.latex(r"RFA_{\max} = \frac{FA_{\max}}{F_{st}}\cdot 100\,\%,\qquad FA_{\max} = F_{st} - F_{\min}")
                st.markdown("**Sztywność opony (z amplitudy $H_{25}$):**")
                st.latex(r"\mathrm{rig} = a_{\mathrm{rig}}\frac{H_{25}}{e_p} + b_{\mathrm{rig}},\quad a_{\mathrm{rig}}=0{,}571,\; b_{\mathrm{rig}}=46")
                st.markdown("**Częstotliwość rezonansowa:**")
                st.latex(r"f_{\mathrm{res}} = f\bigl|_{t = t_{F_{\max}}}")

            st.markdown("### Interpretacja wyniku")
            st.latex(rf"\varphi_{{\min}} = {phi_min:.2f}^\circ")

            eusama_val = wyniki['eusama']
            F_min_val = float(np.min(wyniki['F_t']))
            wheel_liftoff = F_min_val < 0.0

            # Wieloskładnikowe kryterium oceny: phi_min (EGEA AC),
            # EUSAMA i odrywanie koła od płyty (F < 0). W modelu
            # ćwiartkowym phi_min nie zawsze przekracza próg 35° dla
            # uszkodzonego amortyzatora (rezonans masy nieresorowanej
            # bywa "wymywany" przez tłumienie opony), dlatego dodatkowe
            # wskaźniki są niezbędne do prawidłowej diagnozy.
            if wheel_liftoff:
                st.error(
                    rf"**Amortyzator NIESPRAWNY – koło traci kontakt z płytą.** "
                    rf"$F_{{\min}} = {F_min_val:.0f}$ N $< 0$, co oznacza, że "
                    rf"siła kontaktu opona-płyta spada poniżej zera w okolicach "
                    rf"rezonansu masy nieresorowanej. Wskazana wymiana "
                    rf"amortyzatora (EUSAMA = {eusama_val:.1f}%)."
                )
            elif eusama_val < 30.0:
                st.error(
                    rf"**Amortyzator NIESPRAWNY** – EUSAMA = {eusama_val:.1f}% < 30%. "
                    rf"Niewielka redukcja siły kontaktu opony w rezonansie świadczy "
                    rf"o utracie zdolności tłumienia. Wskazana wymiana."
                )
            elif phi_min < 25:
                st.error(
                    r"**Amortyzator uszkodzony/zużyty** – "
                    r"$\varphi_{\min} < 25^\circ$. Wskazana wymiana."
                )
            elif phi_min < 35:
                st.warning(
                    r"**Amortyzator w stanie granicznym** – "
                    r"$25^\circ \leq \varphi_{\min} < 35^\circ$. "
                    "Zalecana powtórka pomiaru."
                )
            elif eusama_val < 45.0:
                st.warning(
                    rf"**Stan graniczny** – $\varphi_{{\min}} \geq 35^\circ$, ale "
                    rf"EUSAMA = {eusama_val:.1f}% < 45%. Zalecana powtórka pomiaru."
                )
            else:
                st.success(
                    rf"**Amortyzator sprawny** – $\varphi_{{\min}} \geq 35^\circ$ "
                    rf"oraz EUSAMA = {eusama_val:.1f}% $\geq 45\%$ "
                    rf"(zgodnie z kryterium $\mathrm{{AC}}_{{\varphi_{{\min}}}}$ "
                    rf"oraz dobrymi praktykami warsztatowymi)."
                )

            st.caption(
                "ℹ️ **Uwaga metodologiczna:** zgodnie z normą SPECSUS2018 "
                r"głównym kryterium jest $\varphi_{\min} \geq 35^\circ$. W modelu "
                "ćwiartkowym (2 DOF) wskaźnik ten ma jednak ograniczoną "
                "wrażliwość na uszkodzenie amortyzatora przy silnym tłumieniu "
                "opony, dlatego aplikacja łączy go z dwoma dodatkowymi "
                "wskaźnikami: EUSAMA (redukcja siły kontaktu w rezonansie) "
                "oraz detekcją odrywania koła ($F_{\\min} < 0$)."
            )

        # ---- TAB 2: przebiegi czasowe -----------------------------------
        with tab2:
            t = wyniki['t']
            f_step = wyniki['f_step']

            st.markdown("**Funkcja zmienności częstotliwości** (rozdz. 5.4 normy):")
            st.latex(r"""
            f(t) = \begin{cases}
              2 + \dfrac{f_{\max}-2}{T_1}\,t, & 0 \leq t < T_1 \\[4pt]
              f_{\max} = 25\,\mathrm{Hz}, & T_1 \leq t < T_1 + \Delta T_{25} \\[4pt]
              25 - \dfrac{25-18}{T_{\mathrm{prep}}}(t-T_2),
                & T_2 \leq t < T_2 + T_{\mathrm{prep}} \\[4pt]
              18 - \dfrac{18-6}{\Delta T_{\mathrm{meas}}}(t-T_3),
                & T_3 \leq t < T_3 + \Delta T_{\mathrm{meas}} \\[4pt]
              6 - \dfrac{6}{T_{\mathrm{ext}}}(t-T_4), & T_4 \leq t < T_4 + T_{\mathrm{ext}}
            \end{cases}
            """)
            st.latex(r"\Delta T_{25} = F_{st}\cdot 0{,}16 + 1200\,\mathrm{[ms]},\quad \Delta T_{\mathrm{meas}} = 7{,}5\,\mathrm{s}")

            fig_freq = go.Figure()
            fig_freq.add_trace(go.Scattergl(
                x=t, y=f_step, mode='lines', name='f(t)',
                line=dict(color="#7c3aed", width=2)
            ))
            meas_mask = (f_step >= 6) & (f_step <= 18)
            if meas_mask.any():
                idx_meas = np.where(meas_mask)[0]
                # Plotly's protobuf serializer chokes on numpy scalars
                # for vrect bounds when the chart is large; cast to float.
                fig_freq.add_vrect(
                    x0=float(t[idx_meas[0]]),
                    x1=float(t[idx_meas[-1]]),
                    fillcolor="rgba(232,245,66,0.12)",
                    line_width=0,
                    annotation_text="Zakres pomiarowy 18 do 6 Hz",
                    annotation_position="top left",
                )
            fig_freq.update_layout(
                title="Profil zmienności częstotliwości wg EGEA",
                xaxis_title="Czas t [s]", yaxis_title="Częstotliwość f [Hz]",
                height=350, hovermode="x unified"
            )
            st.plotly_chart(fig_freq, use_container_width=True)

            st.markdown("**Przemieszczenie płyty i siła kontaktu opony:**")
            st.latex(r"z(t) = d\cos\theta(t),\qquad F(t) = F_{st} + k_m(x_m-z) + c_m(\dot{x}_m-\dot{z})")

            fig_F = make_subplots(specs=[[{"secondary_y": True}]])
            fig_F.add_trace(
                go.Scattergl(x=t, y=wyniki['z']*1000, name="z(t) [mm]",
                             line=dict(color="#42d4f5", width=1.5)),
                secondary_y=False,
            )
            fig_F.add_trace(
                go.Scattergl(x=t, y=wyniki['F_t'], name="F(t) [N]",
                             line=dict(color="#f59e0b", width=1.5)),
                secondary_y=True,
            )
            fig_F.add_hline(y=wyniki['F_st'], line_dash="dash",
                            line_color="#ef4444", secondary_y=True,
                            annotation_text="F_st")
            fig_F.update_layout(
                title="Wymuszenie z(t) i siła kontaktu F(t)",
                xaxis_title="Czas t [s]", height=380, hovermode="x unified",
            )
            fig_F.update_yaxes(title_text="Przemieszczenie z [mm]", secondary_y=False)
            fig_F.update_yaxes(title_text="Siła F [N]", secondary_y=True)
            st.plotly_chart(fig_F, use_container_width=True)

            # ---- Wykres porównawczy: znormalizowane z(t) i F_dyn(t) --------
            st.markdown("**Porównanie fazowe: znormalizowane $z(t)$ i $F_{dyn}(t)$**")
            st.markdown(
                r"Oba sygnały sprowadzone do amplitudy $\pm 1$ na wspólnej osi, "
                r"$\hat z(t) = z(t)/\max|z|$, $\hat F_{dyn}(t) = (F(t)-F_{st})/\max|F-F_{st}|$. "
                r"Pozwala wizualnie odczytać przesunięcie fazowe $\varphi$ między "
                r"płytą a siłą kontaktu — przy spadku tłumienia $c_M$ przebiegi powinny "
                r"się zbliżyć (w 1DOF $\varphi$ maleje wraz z $c$)."
            )

            z_arr = wyniki['z']
            F_dyn = wyniki['F_t'] - wyniki['F_st']
            z_scale = float(np.max(np.abs(z_arr))) if np.any(z_arr) else 1.0
            F_scale = float(np.max(np.abs(F_dyn))) if np.any(F_dyn) else 1.0
            z_norm = z_arr / z_scale if z_scale > 0 else z_arr
            F_norm = F_dyn / F_scale if F_scale > 0 else F_dyn

            # Domyślne okno wycentrowane na f_phi_min — to tam fizycznie
            # objawia się przesunięcie fazowe odpowiadające phi_min.
            f_step_arr = wyniki['f_step']
            meas_mask_t = (f_step_arr >= 6) & (f_step_arr <= 18)
            if np.isfinite(analiza['f_phi_min']) and meas_mask_t.any():
                # szukamy najdłuższego ciągłego zakresu w paśmie 6–18 Hz
                # (faza pomiarowa) i w nim najbliższego f_phi_min.
                idx_meas_t = np.where(meas_mask_t)[0]
                splits_t = np.where(np.diff(idx_meas_t) > 1)[0]
                starts_t = np.concatenate(([0], splits_t + 1))
                ends_t = np.concatenate((splits_t, [len(idx_meas_t) - 1]))
                longest_t = int(np.argmax(ends_t - starts_t + 1))
                meas_run = idx_meas_t[starts_t[longest_t]:ends_t[longest_t] + 1]
                f_in_run = f_step_arr[meas_run]
                idx_at_fmin = meas_run[int(np.argmin(np.abs(f_in_run - analiza['f_phi_min'])))]
                t_center = float(t[idx_at_fmin])
                half = max(0.15, 3.0 / max(float(analiza['f_phi_min']), 1.0))
                t_win_default = (
                    max(float(t[0]), t_center - half),
                    min(float(t[-1]), t_center + half),
                )
            elif meas_mask_t.any():
                idx_meas_t = np.where(meas_mask_t)[0]
                t_mid = 0.5 * (float(t[idx_meas_t[0]]) + float(t[idx_meas_t[-1]]))
                t_win_default = (
                    max(float(t[0]), t_mid - 0.2),
                    min(float(t[-1]), t_mid + 0.2),
                )
            else:
                t_win_default = (float(t[0]), float(t[-1]))

            t_window = st.slider(
                "Okno czasowe [s] — zawęź, żeby zobaczyć kilka okresów",
                min_value=float(t[0]),
                max_value=float(t[-1]),
                value=t_win_default,
                step=0.01,
                key="overlay_window",
            )
            zoom_mask = (t >= t_window[0]) & (t <= t_window[1])

            fig_overlay = go.Figure()
            fig_overlay.add_trace(go.Scattergl(
                x=t[zoom_mask], y=z_norm[zoom_mask],
                name=r"ẑ(t) — wymuszenie płyty",
                line=dict(color="#42d4f5", width=2),
            ))
            fig_overlay.add_trace(go.Scattergl(
                x=t[zoom_mask], y=F_norm[zoom_mask],
                name=r"F̂_dyn(t) — dynamiczna siła kontaktu",
                line=dict(color="#f59e0b", width=2),
            ))
            fig_overlay.add_hline(y=0, line_dash="dot",
                                  line_color="rgba(255,255,255,0.25)")

            # Nakładamy znaczniki TOP_p(i) i F_ref(i) z analizy — pokazują,
            # między czym dokładnie algorytm liczy phi(i).
            pairs_an = analiza['pairs']
            if pairs_an.size:
                topp = analiza['TOPp']
                fref = analiza['F_ref_t']
                valid_an = analiza['valid']
                f_per = analiza['f_period']
                # Tylko znaczniki w oknie i w pasmie pomiarowym
                mask_band = (
                    (f_per >= 6) & (f_per <= 18) & valid_an &
                    (topp >= t_window[0]) & (topp <= t_window[1])
                )
                topp_show = topp[mask_band]
                fref_show = fref[mask_band & np.isfinite(fref)]
                for ttop in topp_show:
                    fig_overlay.add_vline(
                        x=float(ttop), line_dash="dash",
                        line_color="rgba(239,68,68,0.55)", line_width=1,
                    )
                for tref in fref_show:
                    fig_overlay.add_vline(
                        x=float(tref), line_dash="dash",
                        line_color="rgba(34,197,94,0.55)", line_width=1,
                    )

            fig_overlay.update_layout(
                title=(
                    "Nałożone przebiegi z(t) i F(t) — porównanie fazowe "
                    "(czerwone: TOP_p, zielone: F_ref)"
                ),
                xaxis_title="Czas t [s]",
                yaxis_title="Sygnał znormalizowany [–]",
                yaxis=dict(range=[-1.15, 1.15]),
                height=440, hovermode="x unified",
                legend=dict(orientation="h", y=-0.18),
            )
            st.plotly_chart(fig_overlay, use_container_width=True)
            st.caption(
                r"Jeżeli $\hat F_{dyn}$ wyprzedza/opóźnia $\hat z$ o pełne ćwierć okresu, "
                r"to $\varphi(i) \approx 90^\circ$. Im bliżej przebiegi pokrywają się "
                r"(extrema w tych samych chwilach), tym $\varphi$ jest bliższe $0^\circ$ "
                r"lub $180^\circ$. Pionowe linie pokazują znaczniki użyte do wyliczenia "
                r"$\varphi(i) = 2\pi(F_{ref}-TOP_p)/T$."
            )

            st.markdown("**Trajektorie mas modelu 2 DOF:**")
            st.latex(r"x_m(t)\ \text{– masa nieresorowana (koło)},\qquad x_M(t)\ \text{– masa resorowana (nadwozie)}")

            fig_xy = go.Figure()
            fig_xy.add_trace(go.Scattergl(x=t, y=wyniki['x_m']*1000,
                                          name="x_m (koło) [mm]",
                                          line=dict(color="#22c55e", width=1.5)))
            fig_xy.add_trace(go.Scattergl(x=t, y=wyniki['x_M']*1000,
                                          name="x_M (nadwozie) [mm]",
                                          line=dict(color="#a78bfa", width=1.5)))
            fig_xy.update_layout(
                title="Trajektorie mas modelu 2 DOF",
                xaxis_title="Czas t [s]", yaxis_title="Przemieszczenie [mm]",
                height=360, hovermode="x unified"
            )
            st.plotly_chart(fig_xy, use_container_width=True)

        # ---- TAB 3: krzywa phi(f) z analizy okresów ---------------------
        with tab3:
            phi_deg = analiza['phi_deg']
            f_period = analiza['f_period']
            valid = analiza['valid']

            st.markdown("**Definicja przesunięcia fazowego okresu $i$** (rozdz. 3.21 normy):")
            st.latex(r"""
            \varphi(i) = \frac{2\pi\bigl(F_{\mathrm{ref}}(i) - TOP_p(i)\bigr)}{\mathrm{Period}(i)},
            \qquad 0^\circ \leq \varphi(i) < 180^\circ
            """)
            st.markdown(
                r"gdzie $F_{\mathrm{ref}}(i)$ to środek między dwoma kolejnymi "
                r"przecięciami $F(t)$ z poziomem $F_{st}$, a $TOP_p(i) = ST(i) + \Delta\mathrm{Period}(i)$ "
                r"to skorygowana chwila najwyższego położenia płyty."
            )

            mask = valid & np.isfinite(phi_deg)
            fig_phi = go.Figure()
            fig_phi.add_trace(go.Scatter(
                x=f_period[mask], y=phi_deg[mask],
                mode='markers+lines', name='φ(f)',
                line=dict(color="#42d4f5", width=1),
                marker=dict(size=4, color="#42d4f5"),
            ))
            fig_phi.add_hline(y=35, line_dash="dash", line_color="#fbbf24",
                              annotation_text="AC_φmin = 35° (próg EGEA)",
                              annotation_position="top right")
            fig_phi.add_hline(y=90, line_dash="dot", line_color="#22c55e",
                              annotation_text="φ = 90° (granica dobrego tłumienia)",
                              annotation_position="bottom right")
            if np.isfinite(analiza['phi_min']):
                fig_phi.add_trace(go.Scatter(
                    x=[analiza['f_phi_min']],
                    y=[analiza['phi_min']],
                    mode='markers', name='φ_min',
                    marker=dict(size=14, color="#ef4444", symbol="star"),
                ))
            fig_phi.update_layout(
                title="Charakterystyka fazowa φ w funkcji częstotliwości",
                xaxis_title="Częstotliwość f [Hz]",
                yaxis_title="Przesunięcie fazowe φ [°]",
                height=480, hovermode="closest",
                xaxis=dict(range=[5, 26]),
            )
            st.plotly_chart(fig_phi, use_container_width=True)

            st.latex(rf"""
            \varphi_{{\min}} = {analiza['phi_min']:.2f}^\circ
            \qquad\text{{przy}}\qquad f = {analiza['f_phi_min']:.2f}\,\mathrm{{Hz}}
            """)
            st.info(
                "Minimum φ wyznaczone w zakresie $[f_{\\min},\\,f_{\\max}] = [6,\\,18]$ Hz. "
                "Im wyższe $\\varphi_{\\min}$, tym lepszy stan amortyzatora "
                "(zob. rozdz. 4.2 normy SPECSUS2018)."
            )

        # ---- TAB 4: tabela parametrów EGEA ------------------------------
        with tab4:
            st.markdown("### Wszystkie obliczone wskaźniki diagnostyczne")
            # Używamy string.Template - nie koliduje z LaTeX-owym '\%' i '{...}'.
            _tabela_tpl = Template(r"""
            \begin{array}{l|r|l}
            \text{Symbol} & \text{Wartość} & \text{Jednostka} \\ \hline
            F_{st}       & $Fst    & \mathrm{N} \\
            \varphi_{\min} & $phi_min & {}^\circ \\
            \varphi_{\max}(18\,\mathrm{Hz}) & $phi_max & {}^\circ \\
            f_{\varphi_{\min}} & $fpmin & \mathrm{Hz} \\
            f_{\mathrm{res}} & $fres & \mathrm{Hz} \\
            RFA_{\max}   & $rfa & \% \\
            H_{25}       & $H25 & \mathrm{N} \\
            \mathrm{rig} & $rig & \mathrm{N/mm} \\
            \mathrm{EUSAMA} & $eus & \% \\
            \Delta T_{25} & $dT25 & \mathrm{s}
            \end{array}
            """)

            def _fmt(value: float, dec: int) -> str:
                return f"{value:.{dec}f}" if np.isfinite(value) else "—"

            st.latex(_tabela_tpl.substitute(
                Fst=_fmt(wyniki['F_st'], 1),
                phi_min=_fmt(analiza['phi_min'], 2),
                phi_max=_fmt(analiza['phi_max'], 2),
                fpmin=_fmt(analiza['f_phi_min'], 2),
                fres=_fmt(analiza['fres'], 2),
                rfa=_fmt(analiza['RFA_max'], 2),
                H25=_fmt(analiza['H25'], 1),
                rig=_fmt(oblicz_rig(analiza['H25']), 1),
                eus=_fmt(wyniki['eusama'], 2),
                dT25=_fmt(wyniki['dT25'], 3),
            ))

            st.markdown("### Tolerancje normy EGEA (rozdz. 6.1.4)")
            st.latex(r"""
            \begin{array}{l|c|c}
            \text{Wielkość} & \text{Powtarzalność} & \text{Błąd całkowity} \\ \hline
            \varphi_{\min} > 30^\circ & \pm 3^\circ & 7{,}5^\circ \\
            \varphi_{\min} = 0^\circ  & \pm 6^\circ & 15^\circ \\
            RFA_{\max}     & \pm 1{,}5\,\% & 5\,\% \\
            H_{25}         & \pm 24\,\mathrm{daN} & 8\,\% \\
            F_{st} \geq 300\,\mathrm{daN} & \pm 2\,\% & \pm 2\,\% \\
            F_{st} < 300\,\mathrm{daN}   & \pm 6\,\mathrm{daN} & \pm 6\,\mathrm{daN}
            \end{array}
            """)

        # ---- TAB 5: eksport CSV -----------------------------------------
        with tab5:
            st.markdown(
                r"Eksportowane są wszystkie przebiegi czasowe: $t$, $z(t)$, "
                r"$\dot{z}(t)$, $x_m(t)$, $x_M(t)$, $F(t)$, $F_p(t)$, $S(t)$, $f(t)$."
            )

            df_eksport = pd.DataFrame({
                "t [s]":         wyniki['t'],
                "z [mm]":        wyniki['z'] * 1000,
                "z_dot [mm/s]":  wyniki['z_dot'] * 1000,
                "x_m [mm]":      wyniki['x_m'] * 1000,
                "x_M [mm]":      wyniki['x_M'] * 1000,
                "F(t) [N]":      wyniki['F_t'],
                "F_p(t) [N]":    wyniki['F_p'],
                "S":             wyniki['S'],
                "f_step [Hz]":   wyniki['f_step'],
            })
            buf = io.StringIO()
            # Nagłówek z metadanymi: F_st jest niezbędny do prawidłowej
            # rekonstrukcji phi_min (algorytm wyznacz_F_ref jest bardzo
            # wrażliwy — błąd 1 N w F_st potrafi przesunąć phi_min o 40°).
            # Linie zaczynające się od '#' są ignorowane przez pandas
            # przy czytaniu z `comment='#'`.
            buf.write(f"# EGEA_export_version=1\n")
            buf.write(f"# F_st_N={wyniki['F_st']:.6f}\n")
            buf.write(f"# m_p_kg={m_p:.6f}\n")
            buf.write(f"# d_mm={d_mm:.6f}\n")
            df_eksport.to_csv(buf, index=False, sep=";")
            st.download_button(
                "Pobierz przebieg symulacji (CSV)",
                data=buf.getvalue(),
                file_name="EGEA_symulacja.csv",
                mime="text/csv",
                use_container_width=True,
            )

            F_min_raport = float(np.min(wyniki['F_t']))
            status_raport = kategoryzuj_amortyzator(
                phi_min=analiza['phi_min'],
                eusama=wyniki['eusama'],
                F_min=F_min_raport,
            )
            raport = (
                "RAPORT BADANIA STANOWISKA EGEA\n"
                "================================\n\n"
                "PARAMETRY POJAZDU\n"
                f"  M  = {par['M']} kg\n"
                f"  m  = {par['m']} kg\n"
                f"  kM = {par['kM']} N/m\n"
                f"  km = {par['km']} N/m\n"
                f"  cM = {par['cM']} N*s/m\n"
                f"  cm = {par['cm']} N*s/m\n"
                f"  d  = {d_mm:.2f} mm\n\n"
                "WYNIKI\n"
                f"  F_st     = {wyniki['F_st']:.1f} N\n"
                f"  F_min    = {F_min_raport:.1f} N\n"
                f"  phi_min  = {analiza['phi_min']:.2f} stopni\n"
                f"  f_phi_min= {analiza['f_phi_min']:.2f} Hz\n"
                f"  EUSAMA   = {wyniki['eusama']:.2f} %\n"
                f"  RFA_max  = {analiza['RFA_max']:.2f} %\n"
                f"  H25      = {analiza['H25']:.1f} N\n"
                f"  rig      = {oblicz_rig(analiza['H25']):.1f} N/mm\n\n"
                "OCENA (kryterium lacznosciowe: phi_min, EUSAMA, F_min<0)\n"
                f"  Stan amortyzatora: {status_raport}\n"
            )
            st.text_area("Raport tekstowy", value=raport, height=320)


# =============================================================================
#  TRYB 2: Import pomiaru z pliku CSV
# =============================================================================

elif tryb == "Import pomiaru (CSV)":
    st.sidebar.subheader("Wczytanie danych")
    plik = st.sidebar.file_uploader(
        "Plik CSV (kolumny: t, F, S)",
        type=["csv"],
        help="Format wymagany przez normę: czas [s], siła F(t) [N], "
             "sygnał czujnika płyty S (0/1).",
    )
    F_st_user = st.sidebar.number_input(
        r"$F_{st}$ – statyczne obciążenie koła [N]",
        value=3747.0, step=1.0, min_value=100.0,
        help="Mierzone przed testem (rozdz. 3.1 normy).",
    )
    auto_F_st = st.sidebar.checkbox(
        "Wyznacz F_st automatycznie (średnia z pierwszych 0,5 s)", value=True
    )
    sep_choice = st.sidebar.selectbox("Separator", [",", ";", "auto"], index=2)

    # ---- Opis procedury - zawsze widoczny ------------------------------
    with st.expander("Procedura MinPhaseShift (rozdz. 3.7–3.22 normy)", expanded=False):
        st.markdown("**Krok 1: Detekcja znaczników $ST_i$:**")
        st.latex(r"ST_i = \min\{k : S_k = 1 \,\wedge\, S_{k-1} = 0\}")

        st.markdown("**Krok 2: Macierz kalibracji dynamicznej (test bez pojazdu, rozdz. 3.10):**")
        st.latex(r"\Delta\mathrm{Period}(i) = \mathrm{CalcTOP}(i) - ST(i)")

        st.markdown("**Krok 3: Skorygowana chwila TOP (rozdz. 3.11):**")
        st.latex(r"TOP_p(i) = ST(i) + \Delta\mathrm{Period}(i)")

        st.markdown(r"**Krok 4: Wyznaczenie $F_{\mathrm{ref}}(i)$ z dwóch przecięć $F(t)$ z $F_{st}$:**")
        st.latex(r"""
        \begin{aligned}
        F_{st,\,lo} &= \min F(i) + \Delta F(i)\,\frac{RFstFMin}{100} \\
        F_{st,\,hi} &= \max F(i) - \Delta F(i)\,\frac{RFstFMax}{100} \\
        F_{st,\,lo} &< F_{up}(i),\,F_{dn}(i) < F_{st,\,hi}
        \end{aligned}
        """)
        st.latex(r"F_{\mathrm{ref}}(i) = \tfrac{1}{2}\bigl(F_{up}(i) + F_{dn}(i)\bigr)")

        st.markdown("**Krok 5: Przesunięcie fazowe:**")
        st.latex(r"\varphi(i) = \frac{2\pi\bigl(F_{\mathrm{ref}}(i) - TOP_p(i)\bigr)}{\mathrm{Period}(i)}")

        st.markdown("**Krok 6: Wyznaczenie minimum w zakresie 6–18 Hz:**")
        st.latex(r"\varphi_{\min} = \min_{f(i)\in[6,\,18]\,\mathrm{Hz}} \varphi(i)")

    if plik is not None:
        # Pre-parse nagłówka komentarzy (linie '# klucz=wartość') — zawiera
        # m.in. F_st zapisany przy eksporcie z trybu 2DOF. Bez tego nie da
        # się dokładnie zrekonstruować F_st z samego sygnału (wrażliwość
        # phi_min na F_st jest ekstremalna).
        meta: dict = {}
        try:
            plik.seek(0)
            for raw in plik:
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                if not line.startswith("#"):
                    break
                kv = line.lstrip("#").strip()
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    meta[k.strip()] = v.strip()
            plik.seek(0)
        except Exception:
            meta = {}

        if sep_choice == "auto":
            df = pd.read_csv(plik, sep=None, engine="python", comment="#")
        else:
            df = pd.read_csv(plik, sep=sep_choice, comment="#")

        if meta:
            znalezione = ", ".join(f"{k}={v}" for k, v in meta.items())
            st.info(f"Znaleziono nagłówek z metadanymi: {znalezione}")

        cols = list(df.columns)
        if len(cols) < 3:
            st.error("Plik musi zawierać co najmniej 3 kolumny: t, F, S.")
            st.stop()

        # Auto-detekcja kolumn. Pasuje do formatu eksportowanego z trybu 2DOF
        # (kolumny "t [s]", "F(t) [N]", "S") oraz do minimalnego pliku t,F,S.
        # Wzorce uporządkowane od najbardziej do najmniej specyficznych —
        # np. "F(t)" musi być sprawdzone PRZED samym "F", żeby nie złapać
        # "F_p(t) [N]" zamiast "F(t) [N]".
        idx_t_default = _wybierz_kolumne(cols, ["t [s]", "t[s]", "time", "czas"])
        if idx_t_default < 0:
            idx_t_default = 0  # pierwsza kolumna jako fallback dla "t"
        idx_F_default = _wybierz_kolumne(cols, ["f(t)", "f [n]", "siła", "sila"])
        if idx_F_default < 0:
            idx_F_default = _wybierz_kolumne(cols, ["f"])
        if idx_F_default < 0 or idx_F_default == idx_t_default:
            idx_F_default = 1 if len(cols) > 1 else 0
        idx_S_default = _wybierz_kolumne(cols, [" s", "trigger", "st_signal"])
        # Dokładne dopasowanie "S" jako nazwy kolumny (typowe w eksporcie).
        for i, c in enumerate(cols):
            if c.strip().lower() == "s":
                idx_S_default = i
                break
        if idx_S_default < 0 or idx_S_default in (idx_t_default, idx_F_default):
            idx_S_default = 2 if len(cols) > 2 else len(cols) - 1

        # Opcjonalna kolumna F_p (siła pustej płyty). Jeśli plik pochodzi z
        # eksportu 2DOF zawiera ją — wtedy oblicz_phi może użyć kalibracji
        # dynamicznej i wynik phi_min będzie identyczny z trybem symulacji.
        OPCJA_BRAK = "— brak —"
        idx_Fp_default = _wybierz_kolumne(cols, ["f_p(t)", "f_p ", "fp "])

        st.markdown("### Mapowanie kolumn")
        st.caption(
            "Aplikacja próbuje rozpoznać kolumny po nazwach. Sprawdź wybór "
            "— eksport z trybu *Symulacja 2DOF* zawiera 9 kolumn, "
            "więc bez właściwego mapowania `F`, `S` (i opcjonalnie `F_p`) "
            "zostałyby pomylone z przemieszczeniem i prędkością płyty."
        )
        col_t, col_F, col_S, col_Fp = st.columns(4)
        with col_t:
            t_col = st.selectbox("Kolumna czasu $t$ [s]",
                                 cols, index=idx_t_default, key="map_t")
        with col_F:
            F_col = st.selectbox(r"Kolumna siły $F$ [N]",
                                 cols, index=idx_F_default, key="map_F")
        with col_S:
            S_col = st.selectbox("Kolumna sygnału $S$ (0/1)",
                                 cols, index=idx_S_default, key="map_S")
        with col_Fp:
            Fp_options = [OPCJA_BRAK] + cols
            Fp_idx_default = (idx_Fp_default + 1) if idx_Fp_default >= 0 else 0
            Fp_col = st.selectbox(
                r"Kolumna $F_p$ [N] (opcjonalna)",
                Fp_options, index=Fp_idx_default, key="map_Fp",
                help="Siła pustej płyty — zwiększa dokładność kalibracji "
                     "dynamicznej. Bez tej kolumny algorytm zakłada ST = TOP "
                     "płyty, co daje phi_min ~2° większą.",
            )

        if len({t_col, F_col, S_col}) < 3:
            st.error("Te same kolumny przypisane do różnych ról — wybierz "
                     "trzy różne kolumny.")
            st.stop()
        if Fp_col != OPCJA_BRAK and Fp_col in (t_col, F_col, S_col):
            st.error(f"Kolumna `{Fp_col}` jest już użyta jako t/F/S.")
            st.stop()

        t = df[t_col].to_numpy(dtype=float)
        F = df[F_col].to_numpy(dtype=float)
        S_raw = df[S_col].to_numpy(dtype=float)
        Fp_arr = df[Fp_col].to_numpy(dtype=float) if Fp_col != OPCJA_BRAK else None

        # Walidacja S: powinien być binarny (0/1) lub bliski temu. Sygnał
        # ciągły (np. z_dot [mm/s]) traktujemy jako błędne mapowanie.
        s_unique = np.unique(S_raw[np.isfinite(S_raw)])
        s_is_binary = (
            s_unique.size <= 3
            and np.all(np.isin(s_unique, [0, 1]))
        )
        if not s_is_binary:
            st.warning(
                f"Kolumna `{S_col}` nie wygląda na sygnał wyzwalający 0/1 "
                f"(unikalnych wartości: {s_unique.size}, "
                f"zakres: [{np.nanmin(S_raw):.3g}, {np.nanmax(S_raw):.3g}]). "
                "Sprawdź mapowanie kolumn — w eksporcie z 2DOF właściwa "
                "kolumna nazywa się `S`."
            )
        S = S_raw.astype(int)

        if auto_F_st:
            # Kolejność wyboru F_st:
            # 1) Z nagłówka pliku (najbardziej dokładne — zapisane przy
            #    eksporcie z trybu 2DOF). Algorytm phi_min ma ekstremalną
            #    wrażliwość: 1 N błędu = 40° skoku, więc dla pliku z eksportu
            #    musimy użyć dokładnej wartości.
            # 2) Mean z całego sygnału (dla zewnętrznych pomiarów). Działa
            #    gdy F_dyn ma zerową średnią, czyli mierzony zakres pokrywa
            #    pełne cykle. Dokładność ~1-2 N — może być za mało dla
            #    sygnałów blisko progów detekcji.
            # 3) Ręczna wartość z pola "F_st" w panelu bocznym jako fallback.
            F_st_src = ""
            F_st_val = None
            if "F_st_N" in meta:
                try:
                    F_st_val = float(meta["F_st_N"])
                    F_st_src = "z nagłówka pliku"
                except ValueError:
                    F_st_val = None
            if F_st_val is None:
                F_st_auto = float(np.mean(F))
                if F_st_auto < 50.0:
                    st.warning(
                        f"Auto-detekcja $F_{{st}}$ dała nierealistyczną "
                        f"wartość {F_st_auto:.2f} N — używam wartości z pola "
                        f"obok ({F_st_user:.0f} N). Prawdopodobnie kolumna "
                        "$F$ została źle wybrana."
                    )
                    F_st_val = F_st_user
                    F_st_src = "ręcznie (panel boczny)"
                else:
                    F_st_val = F_st_auto
                    F_st_src = "średnia całego sygnału"
            st.caption(f"$F_{{st}}$ = {F_st_val:.2f} N (źródło: {F_st_src}).")
        else:
            F_st_val = F_st_user

        with st.spinner(r"Trwa wyznaczanie $\varphi_{\min}$ wg procedury EGEA…"):
            analiza = oblicz_phi(t=t, F=F, S=S, F_st=F_st_val, Fp=Fp_arr)

        # F_min (min siły kontaktu w pasmie pomiarowym 6-18 Hz) i wynikający
        # z niego wskaźnik EUSAMA — analiza['F_min'] jest już ograniczony
        # do tego pasma (zob. phase_shift.oblicz_phi → idx_meas).
        phi_min = analiza['phi_min']
        F_min_imp = analiza.get('F_min', float('nan'))
        eusama_imp = (F_min_imp / F_st_val * 100.0) if np.isfinite(F_min_imp) else float('nan')

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("F_st [N]", f"{F_st_val:.0f}")
        c2.metric("φ_min [°]",
                  f"{phi_min:.2f}" if np.isfinite(phi_min) else "—")
        c3.metric("EUSAMA [%]",
                  f"{eusama_imp:.1f}" if np.isfinite(eusama_imp) else "—")
        c4.metric("RFA_max [%]",
                  f"{analiza['RFA_max']:.2f}" if np.isfinite(analiza['RFA_max']) else "—")
        c5.metric("H25 [N]",
                  f"{analiza['H25']:.0f}" if np.isfinite(analiza['H25']) else "—")

        st.markdown("### Wynik")
        st.latex(rf"""
        \varphi_{{\min}} = {phi_min:.2f}^\circ\quad
        @ \quad f_{{\varphi_{{\min}}}} = {analiza['f_phi_min']:.2f}\,\mathrm{{Hz}}
        """)

        # Wykres sygnału (Scattergl - WebGL renderuje >10k punktów bez
        # ryzyka błędu serializacji protobuf w Streamlit).
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=t, y=F, name="F(t) (surowy)",
                                   line=dict(color="rgba(255,255,255,0.35)", width=0.8)))
        fig.add_trace(go.Scattergl(x=t, y=analiza['F_filt'], name="F(t) (filtrowany)",
                                   line=dict(color="#42d4f5", width=1.5)))
        fig.add_hline(y=F_st_val, line_dash="dash", line_color="#ef4444",
                      annotation_text="F_st")
        fig.update_layout(
            title="Siła kontaktu opony F(t) – pomiar wczytany z CSV",
            xaxis_title="Czas t [s]", yaxis_title="Siła F [N]",
            height=420, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # phi(f)
        mask = analiza['valid'] & np.isfinite(analiza['phi_deg'])
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=analiza['f_period'][mask], y=analiza['phi_deg'][mask],
            mode='markers+lines', name='φ(f)',
            line=dict(color="#42d4f5", width=1),
            marker=dict(size=5),
        ))
        fig2.add_hline(y=35, line_dash="dash", line_color="#fbbf24",
                       annotation_text="AC_φmin = 35° (próg EGEA)")
        fig2.add_hline(y=90, line_dash="dot", line_color="#22c55e",
                       annotation_text="φ = 90° (granica dobrego tłumienia)")
        if np.isfinite(analiza['phi_min']):
            fig2.add_trace(go.Scatter(
                x=[analiza['f_phi_min']], y=[analiza['phi_min']],
                mode='markers', name='φ_min',
                marker=dict(size=14, color="#ef4444", symbol="star"),
            ))
        fig2.update_layout(
            title="Charakterystyka fazowa wyznaczona z pomiaru",
            xaxis_title="Częstotliwość f [Hz]",
            yaxis_title="Przesunięcie fazowe φ [°]",
            height=440,
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Pełna diagnoza wg tych samych kryteriów co tryb 2DOF
        # (kategoryzuj_amortyzator: F_min<0, EUSAMA, phi_min). Dzięki temu
        # ten sam plik CSV daje ten sam werdykt w obu trybach.
        if not np.isfinite(phi_min):
            st.warning(r"Nie udało się wyznaczyć $\varphi_{\min}$ – sprawdź jakość sygnału $S(t)$.")
        else:
            wheel_liftoff = np.isfinite(F_min_imp) and F_min_imp < 0.0
            eusama_for_diag = eusama_imp if np.isfinite(eusama_imp) else 100.0
            status = kategoryzuj_amortyzator(
                phi_min=phi_min, eusama=eusama_for_diag,
                F_min=F_min_imp if np.isfinite(F_min_imp) else 1.0,
            )
            if status == "NIESPRAWNY":
                if wheel_liftoff:
                    st.error(
                        rf"**Amortyzator NIESPRAWNY – koło traci kontakt z płytą.** "
                        rf"$F_{{\min}} = {F_min_imp:.0f}$ N $< 0$ w pasmie 6–18 Hz. "
                        rf"EUSAMA = {eusama_imp:.1f}%. Wskazana wymiana."
                    )
                elif eusama_imp < 30.0:
                    st.error(
                        rf"**Amortyzator NIESPRAWNY** – EUSAMA = {eusama_imp:.1f}% < 30%. "
                        rf"$\varphi_{{\min}} = {phi_min:.2f}^\circ$. Wskazana wymiana."
                    )
                else:
                    st.error(
                        rf"**Amortyzator uszkodzony/zużyty** – "
                        rf"$\varphi_{{\min}} = {phi_min:.2f}^\circ < 25^\circ$. Wskazana wymiana."
                    )
            elif status == "GRANICZNY":
                st.warning(
                    rf"**Stan graniczny** – $\varphi_{{\min}} = {phi_min:.2f}^\circ$, "
                    rf"EUSAMA = {eusama_imp:.1f}%. Zalecana powtórka pomiaru."
                )
            else:
                st.success(
                    rf"**Amortyzator sprawny** – $\varphi_{{\min}} = {phi_min:.2f}^\circ \geq 35^\circ$, "
                    rf"EUSAMA = {eusama_imp:.1f}% $\geq 45\%$, koło utrzymuje kontakt z płytą."
                )

            st.caption(
                "ℹ️ Diagnoza łączy trzy kryteria (jak w trybie 2DOF): "
                r"odrywanie koła ($F_{\min} < 0$), EUSAMA i $\varphi_{\min}$. "
                r"Samo $\varphi_{\min} \geq 35^\circ$ nie wystarcza w modelu "
                "ćwiartkowym, bo rezonans masy nieresorowanej dominuje fazę."
            )

    else:
        st.info(
            r"Wgraj plik CSV w formacie `t, F, S`. W panelu bocznym możesz wskazać "
            r"separator i wartość $F_{st}$. Przykładowy plik: `data/example_measurement.csv`."
        )


# =============================================================================
#  TRYB 3: Analiza zależności phi_min(c)
# =============================================================================

else:
    st.sidebar.subheader("Model jednomasowy (1 DOF)")
    m1 = st.sidebar.number_input(r"$m$ – masa zastępcza [kg]",
                                  value=382.0, step=1.0, min_value=1.0)
    k1 = st.sidebar.number_input(r"$k$ – sztywność [N/m]",
                                  value=253161.0, step=1000.0, min_value=1.0)
    d_mm = st.sidebar.number_input(r"$d$ – amplituda płyty [mm]",
                                    value=3.0, step=0.1, min_value=0.1)

    st.sidebar.subheader("Zakres analizy")
    c_min = st.sidebar.number_input(r"$c_{\min}$ [N·s/m]",
                                     value=200.0, step=100.0, min_value=0.0)
    c_max = st.sidebar.number_input(r"$c_{\max}$ [N·s/m]",
                                     value=4000.0, step=100.0, min_value=1.0)
    n_c = st.sidebar.slider("Liczba próbek c", 5, 50, 25)

    if c_max <= c_min:
        st.sidebar.error(r"Wymagane $c_{\max} > c_{\min}$")
        st.stop()

    st.markdown("### Model 1 DOF – sformułowanie")
    st.markdown(
        "Analiza wykorzystuje **model jednomasowy** zgodnie ze sformułowaniem zadania:"
    )
    st.latex(r"m\ddot{x} + c(\dot{x} - \dot{z}) + k(x - z) = 0")
    st.markdown("co po przeniesieniu wymuszenia na prawą stronę daje:")
    st.latex(r"m\ddot{x} + c\dot{x} + k\,x = c\,\dot{z} + k\,z,\qquad z(t) = -d\cos(\omega t)")

    st.markdown("### Rozwiązanie ustalone")
    st.markdown(
        r"Dla wymuszenia harmonicznego $z(t) = -d\cos(\omega t)$ "
        r"i $\dot{z}(t) = d\omega\sin(\omega t)$ przyjmujemy postać próbną "
        r"$x(t) = X\cos(\omega t - \varphi_x)$. Po podstawieniu otrzymujemy:"
    )
    st.latex(r"""
    X(\omega) = \frac{|F_0(\omega)|}{\sqrt{(k - m\omega^2)^2 + (c\omega)^2}},\qquad
    \varphi_x(\omega) = \arctan\!\frac{c\omega}{k - m\omega^2} - \varphi_{F_0}
    """)
    st.markdown(
        r"gdzie wymuszenie zastępcze ma postać "
        r"$F_0(t) = c\dot{z} + kz = A\cos\omega t + B\sin\omega t$, z $A = -kd$, $B = cd\omega$."
    )

    st.markdown("### Przesunięcie fazowe φ")
    st.markdown(r"Siła kontaktu opony $F_{\mathrm{dyn}}(t) = k(x-z) + c(\dot{x}-\dot{z})$ "
                r"jest również harmoniczna o amplitudzie $|F_{\mathrm{dyn}}|$ i fazie $\varphi_F$, więc:")
    st.latex(r"\varphi(\omega) = \varphi_F(\omega) - \varphi_z(\omega)\quad [\mathrm{rad}]")
    st.latex(r"\varphi_{\min} = \min_{f\in[f_{\min},\,f_{\max}]} \varphi(2\pi f),\qquad f \in [6,\,18]\,\mathrm{Hz}")

    if st.button("Uruchom analizę parametryczną", use_container_width=True):
        c_arr = np.linspace(c_min, c_max, n_c)
        phi_min_arr = np.empty_like(c_arr)
        f_at_min = np.empty_like(c_arr)
        krzywe = []
        for i, c in enumerate(c_arr):
            mod = ModelJednomasowy(m=m1, k=k1, c=c, d=d_mm/1000.0)
            phi_min_arr[i], f_at_min[i] = mod.phi_min()
            f_curve, phi_curve = mod.krzywa_phi()
            krzywe.append((c, f_curve, phi_curve))

        # Wykres phi_min(c)
        st.markdown("### Wykres głównej zależności")
        st.latex(r"\varphi_{\min}(c) = \min_{f\in[6,18]\,\mathrm{Hz}} \varphi(2\pi f;\,c)")

        fig_c = go.Figure()
        fig_c.add_trace(go.Scatter(
            x=c_arr, y=phi_min_arr,
            mode='lines+markers',
            line=dict(color="#42d4f5", width=2),
            marker=dict(size=6),
            name='φ_min(c)',
        ))
        fig_c.add_hline(y=35, line_dash="dash", line_color="#fbbf24",
                        annotation_text="AC_φmin = 35°")
        fig_c.update_layout(
            title="Zależność minimalnego przesunięcia fazowego od tłumienia c",
            xaxis_title="Współczynnik tłumienia c [N·s/m]",
            yaxis_title="φ_min [°]",
            height=460, hovermode="x unified",
        )
        st.plotly_chart(fig_c, use_container_width=True)

        # Wykres rodziny krzywych phi(f)
        st.markdown("### Rodzina krzywych $\\varphi(f)$ dla wybranych $c$")
        fig_f = go.Figure()
        n_show = min(8, len(krzywe))
        idx_show = np.linspace(0, len(krzywe)-1, n_show).astype(int)
        for j, idx in enumerate(idx_show):
            c, fc, pc = krzywe[idx]
            fig_f.add_trace(go.Scatter(
                x=fc, y=pc, mode='lines', name=f"c = {c:.0f}",
                line=dict(width=1.5),
            ))
        fig_f.add_hline(y=35, line_dash="dash", line_color="#fbbf24",
                        annotation_text="AC_φmin = 35°")
        fig_f.update_layout(
            title="Krzywe φ(f) dla różnych wartości c",
            xaxis_title="Częstotliwość f [Hz]",
            yaxis_title="Przesunięcie fazowe φ [°]",
            height=460, hovermode="x unified",
        )
        st.plotly_chart(fig_f, use_container_width=True)

        # Tabela wyników
        st.subheader("Wyniki tabelaryczne")
        df = pd.DataFrame({
            "c [N·s/m]": c_arr,
            "φ_min [°]": np.round(phi_min_arr, 2),
            "f przy φ_min [Hz]": np.round(f_at_min, 2),
            "Status": ["Sprawny" if p >= 35 else "Niesprawny"
                       for p in phi_min_arr],
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Wnioski
        c_critical_idx = int(np.argmin(np.abs(phi_min_arr - 35)))
        st.markdown("### Wnioski")
        st.latex(rf"""
        c_{{\mathrm{{krit}}}} \approx {c_arr[c_critical_idx]:.0f}\,\mathrm{{N\!\cdot\!s/m}}
        \quad\text{{przy}}\quad \varphi_{{\min}} = 35^\circ
        """)
        st.markdown(
            r"$\varphi_{\min}$ rośnie monotonicznie z $c$ – zgodnie z teorią opisaną "
            r"w rozdz. 4.3 normy SPECSUS2018 oraz w pracy "
            r"_M. Klapka i in._, Meccanica 52(9), 2017."
        )