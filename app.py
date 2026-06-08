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

    st.sidebar.caption(
        "💡 **Aby zasymulować niesprawny amortyzator:**\n\n"
        "Tłumienie opony $c_m$ samo zapewnia silne tłumienie rezonansu koła, "
        "więc samo obniżenie $c_M$ nie wystarcza. Wypróbuj jednocześnie:\n"
        "- $c_M = 100$–$300$ N·s/m\n"
        "- $c_m = 10$–$30$ N·s/m\n\n"
        "Wskaźnik **EUSAMA** spadnie wtedy do wartości <30 % lub nawet "
        "ujemnych (koło traci kontakt z płytą) – uznajemy to za "
        "amortyzator **niesprawny**.\n\n"
        r"Dla klarownej zależności $\varphi_{\min}(c)$ użyj trybu "
        r"**Analiza φₘᵢₙ(c)**."
    )

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
                              annotation_text="AC_φmin = 35°",
                              annotation_position="top right")
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
        if sep_choice == "auto":
            df = pd.read_csv(plik, sep=None, engine="python")
        else:
            df = pd.read_csv(plik, sep=sep_choice)

        cols = list(df.columns)
        if len(cols) < 3:
            st.error("Plik musi zawierać co najmniej 3 kolumny: t, F, S.")
            st.stop()
        t_col, F_col, S_col = cols[:3]
        t = df[t_col].to_numpy(dtype=float)
        F = df[F_col].to_numpy(dtype=float)
        S = df[S_col].to_numpy(dtype=float)

        if auto_F_st:
            n_avg = max(1, int(0.5 / max(np.mean(np.diff(t)), 1e-6)))
            F_st_val = float(np.mean(F[:n_avg]))
        else:
            F_st_val = F_st_user

        with st.spinner(r"Trwa wyznaczanie $\varphi_{\min}$ wg procedury EGEA…"):
            analiza = oblicz_phi(t=t, F=F, S=S.astype(int), F_st=F_st_val)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("F_st [N]", f"{F_st_val:.0f}")
        phi_min = analiza['phi_min']
        c2.metric("φ_min [°]",
                  f"{phi_min:.2f}" if np.isfinite(phi_min) else "—")
        c3.metric("RFA_max [%]",
                  f"{analiza['RFA_max']:.2f}" if np.isfinite(analiza['RFA_max']) else "—")
        c4.metric("H25 [N]",
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
                       annotation_text="AC_φmin = 35°")
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

        if phi_min < 35 and np.isfinite(phi_min):
            st.error(
                rf"Wynik poniżej kryterium normy – $\varphi_{{\min}} = {phi_min:.2f}^\circ < 35^\circ$."
            )
        elif np.isfinite(phi_min):
            st.success(
                rf"Amortyzator spełnia kryterium normy: $\varphi_{{\min}} = {phi_min:.2f}^\circ \geq 35^\circ$."
            )
        else:
            st.warning(r"Nie udało się wyznaczyć $\varphi_{\min}$ – sprawdź jakość sygnału $S(t)$.")

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