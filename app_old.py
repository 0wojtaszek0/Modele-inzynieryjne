import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.signal import find_peaks, butter, filtfilt

# Konfiguracja strony
st.set_page_config(page_title="Phase Shift Suspension Tester", page_icon="⚙️", layout="wide")

st.title("Phase Shift Suspension Tester")
st.markdown("Aplikacja inżynieryjna analizująca sygnały z diagnostyki amortyzatorów oparta o dokumentację projektową.")

# Pasek boczny z parametrami
st.sidebar.header("Parametry Układu i Maszyny")
m_p = st.sidebar.number_input("Masa płyty diagnostycznej $m_p$ [kg]", value=50.0, step=1.0)
F_st = st.sidebar.number_input("Siła statyczna $F_{st}$ [N]", value=3820.0, step=10.0)
noise_level = st.sidebar.slider("Poziom zaszumienia sygnału [%]", 0.0, 15.0, 2.0)

# Generowanie danych symulowanych
@st.cache_data
def generate_data(noise_pct, F_st_val):
    fs = 1000  # 1 kHz
    # Odtwarzamy czasy faz z wzorca EGEA
    dT25_ms = F_st_val * 0.16 + 1200.0
    dT25 = dT25_ms / 1000.0
    T_total = 22.0
    t = np.linspace(0, T_total, int(T_total * fs), endpoint=False)
    dt = 1.0 / fs
    
    def get_target_frequency(t_val):
        T1 = 5.0
        T2_end = T1 + dT25
        T_prep = 2.0
        T3_start = T2_end + T_prep
        T_meas = 7.5
        T3_end = T3_start + T_meas
        T_ext = 3.0
        T4_end = T3_end + T_ext
        
        if t_val < T1: return (25.0 / T1) * t_val
        elif t_val < T2_end: return 25.0
        elif t_val < T3_start: return 25.0 - ((t_val - T2_end) / T_prep) * (25.0 - 18.0)
        elif t_val < T3_end: return 18.0 - ((t_val - T3_start) / T_meas) * (18.0 - 6.0)
        elif t_val < T4_end: return 6.0 - ((t_val - T3_end) / T_ext) * (6.0 - 0.0)
        else: return 0.0
    
    f_continuous = np.array([get_target_frequency(ti) for ti in t])
    phase_continuous = np.cumsum(f_continuous) * dt
    
    t_k = [0.0]
    f_k = []
    target_cycles = 1.0
    for i in range(len(t)):
        if phase_continuous[i] >= target_cycles:
            dt_cycle = t[i] - t_k[-1]
            t_k.append(t[i])
            f_k.append(1.0 / dt_cycle)
            target_cycles += 1.0

    if t_k[-1] < T_total:
        t_k.append(T_total)
        f_k.append(f_k[-1] if len(f_k) > 0 else 0)

    t_k = np.array(t_k)
    f_k = np.array(f_k)

    freq_sweep = np.zeros_like(t)
    phase_step = np.zeros_like(t)
    current_k = 0
    for i, t_i in enumerate(t):
        while current_k < len(t_k) - 1 and t_i >= t_k[current_k + 1]:
            current_k += 1
        if current_k >= len(t_k) - 1:
            break
            
        tk_start = t_k[current_k]
        tk_end = t_k[current_k + 1]
        
        if tk_end > tk_start:
            theta = 2 * np.pi * (t_i - tk_start) / (tk_end - tk_start)
        else:
            theta = 0
            
        freq_sweep[i] = f_k[current_k]
        phase_step[i] = theta
    
    A = 0.003
    h_p_ideal = A * np.cos(phase_step)
    h_dot_dot_ideal = -A * np.cos(phase_step) * (2*np.pi * freq_sweep)**2
    F_p_ideal = m_p * h_dot_dot_ideal
    
    rel_amp = np.ones_like(freq_sweep)
    for i, f in enumerate(freq_sweep):
        if f > 18:
            rel_amp[i] = 0.5
        elif 6 <= f <= 18:
            if f > 14:
                rel_amp[i] = 0.1 + 0.4 * (f - 14) / 4.0
            else:
                rel_amp[i] = 0.1 + 0.3 * (14 - f) / 8.0
        else:
            rel_amp[i] = 0.4 * (f / 6.0)

    F_contact_ideal = F_st_val + (F_st_val * rel_amp) * np.cos(phase_step + np.pi/4)
    F_r_ideal = F_contact_ideal + F_p_ideal
    
    h_p_noisy = h_p_ideal + np.random.normal(0, A * (noise_pct/100.0), len(t))
    F_r_noisy = F_r_ideal + np.random.normal(0, F_st_val * (noise_pct/100.0), len(t))
    
    return t, h_p_noisy, F_r_noisy, fs, freq_sweep

t, h_p_raw, F_r_raw, fs, freq_sweep = generate_data(noise_level, F_st)
dt = 1.0 / fs

tab1, tab2 = st.tabs(["Analiza Sygnałów", "Oznaczenia i Parametry"])

with tab1:
    st.header("1. Profil Częstotliwości")
    st.markdown("Wykres przedstawiający częstotliwość pracy wymuszarki w czasie całego pomiaru (rampa zwalniająca).")

    fig0 = go.Figure()
    fig0.add_trace(go.Scatter(x=t, y=freq_sweep, name="Częstotliwość [Hz]", line=dict(color='purple', width=2)))
    fig0.update_layout(title="Zmienność częstotliwości wymuszenia f(t)", xaxis_title="Czas [s]", yaxis_title="Częstotliwość [Hz]")
    st.plotly_chart(fig0)

    st.header("2. Wprowadzanie Danych i Obliczanie Sił Bezwładności")
    st.markdown(r"Pobieramy surowy sygnał z urządzenia oraz obliczamy siłę bezwładności platformy wg wzoru: $F_p(t) = m_p \cdot \ddot{h}_p(t)$.")

    b, a = butter(4, 30.0 / (fs / 2), btype='low')
    h_p_filt = filtfilt(b, a, h_p_raw)

    h_dot = np.gradient(h_p_filt, dt)
    h_dot_dot = np.gradient(h_dot, dt)

    F_p = m_p * h_dot_dot
    F_contact = F_r_raw - F_p

    col1, col2 = st.columns(2)
    with col1:
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=t[:500], y=h_p_raw[:500], name="Sygnał Surowy h_p(t)", line=dict(color='gray', width=1)))
        fig1.add_trace(go.Scatter(x=t[:500], y=h_p_filt[:500], name="Przefiltrowany h_p(t)", line=dict(color='blue', width=2)))
        fig1.update_layout(title="Ruch płyty wymuszającej (pierwsze 0.5s)", xaxis_title="Czas [s]", yaxis_title="Przemieszczenie [m]")
        st.plotly_chart(fig1)

    with col2:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=t[:500], y=F_r_raw[:500], name="Z tensometrów F_r(t)", line=dict(color='orange')))
        fig2.add_trace(go.Scatter(x=t[:500], y=F_p[:500], name="Bezwładność platformy F_p(t)", line=dict(color='red', dash='dash')))
        fig2.update_layout(title="Składowe surowej siły", xaxis_title="Czas [s]", yaxis_title="Siła [N]")
        st.plotly_chart(fig2)

    st.header("3. Rzeczywista Siła Kontaktu Opony F(t)")
    st.markdown(r"Siłę kontaktu opony wyznacza się przez odjęcie wpływu mas z urządzenia: $F(t) = F_r(t) - F_p(t)$.")

    F_contact_filt = filtfilt(b, a, F_contact)

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=t, y=F_contact, name="Zaszumiona Siła F(t)", line=dict(color='lightgray', width=1)))
    fig3.add_trace(go.Scatter(x=t, y=F_contact_filt, name="Przefiltrowana Siła F(t)", line=dict(color='green', width=2)))
    fig3.add_hline(y=F_st, line_dash="dash", line_color="red", annotation_text="Siła statyczna F_st")
    fig3.update_layout(title="Wykres Siły Kontaktu Opony z Podłożem", xaxis_title="Czas [s]", yaxis_title="Siła [N]")
    st.plotly_chart(fig3)

    st.header("4. Analiza Cykli i Wskaźnik RFA")
    st.markdown(r"Algorytm wylicza parametr $\Delta F(i) = \max F(i) - \min F(i)$ oraz wskaźnik **$RFA_{max}$**.")

    peaks, _ = find_peaks(F_contact_filt, distance=fs/25) 
    troughs, _ = find_peaks(-F_contact_filt, distance=fs/25)

    if len(peaks) > 0 and len(troughs) > 0:
        amplitudes = []
        for p in peaks:
            closest_trough_idx = np.argmin(np.abs(troughs - p))
            closest_trough = troughs[closest_trough_idx]
            amp = F_contact_filt[p] - F_contact_filt[closest_trough]
            amplitudes.append(amp)
        
        FA_max = max(amplitudes)
        RFA_max = (FA_max / F_st) * 100.0
    
        m1, m2, m3 = st.columns(3)
        m1.metric("Największa Amplituda (FA_max)", f"{FA_max:.2f} N")
        m2.metric("Wskaźnik RFA_max", f"{RFA_max:.2f} %")
        m3.metric("Liczba pełnych cykli", len(peaks))
    
        idx_max = np.argmax(amplitudes)
        p_max = peaks[idx_max]
        closest_t_max = troughs[np.argmin(np.abs(troughs - p_max))]
    
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=t[max(0, p_max-80):min(len(t), p_max+80)], y=F_contact_filt[max(0, p_max-80):min(len(t), p_max+80)], name="Siła (filtrowana)", line=dict(color='green')))
        fig4.add_trace(go.Scatter(x=[t[p_max]], y=[F_contact_filt[p_max]], mode='markers', marker=dict(color='red', size=12, symbol='triangle-up'), name="F_up"))
        fig4.add_trace(go.Scatter(x=[t[closest_t_max]], y=[F_contact_filt[closest_t_max]], mode='markers', marker=dict(color='blue', size=12, symbol='triangle-down'), name="F_dn"))
        st.plotly_chart(fig4)
    else:
        st.warning("Nie udało się zidentyfikować pełnych cykli.")

with tab2:
    st.header("Słownik Pojęć i Parametrów EGEA")
    st.markdown("Zestawienie parametrów zgodnie z normą **EGEA**.")

    # Tworzymy tabelę Markdown z Latexem, ponieważ st.dataframe nie obsługuje renderowania matematycznego
    table_md = """
| Symbol | Opis parametru | Wartość/Zakres | Jednostka | Tolerancja | Źródło |
| :--- | :--- | :--- | :--- | :--- | :--- |
| $\phi_{min}$ | Minimalne przesunięcie fazowe | $0 - 180$ | $^\circ$ | $\pm 3^\circ (>30^\circ)$ | EGEA 3.22 |
| $F_{st}$ | Siła statyczna koła | $100 - 1100$ | daN | $\pm 2\%$ | EGEA 3.1 |
| $RFA_{max}$ | Maks. względna amplituda siły | $0 - 100$ | $\%$ | $\pm 5\%$ | EGEA 3.18 |
| $h_p(t)$ | Pionowe wzbudzenie platformy | $25 - 5$ | Hz | $\pm 1$ Hz | EGEA 3.2 |
| $h_{PS}$ | Skok platformy (amplituda p-p) | $6$ | mm | $\pm 0.3$ mm | EGEA 5.1 |
| $\Delta\phi_{min}$ | Nierównomierność (asymetria) osi | max $30$ | $\%$ | - | EGEA 5.3 |
| $f_{res}$ | Częstotliwość rezonansowa | $6 - 18$ | Hz | - | EGEA 3.17 |
| $rig$ | Sztywność opony (statyczna) | $160 - 400$ | N/mm | - | EGEA 3.20 |
| $\Delta T_{meas}$ | Czas spadku f ($18 \to 6$ Hz) | $7.5$ | s | $\pm 2$ Hz | EGEA 5.4 |
| $\Delta T_{25}$ | Czas stabilizacji przy $25$ Hz | $F_{st} \cdot 0.16 + 1200$ | ms | - | EGEA 5.4 |
| $H_{25}$ | Amplituda siły $F(t)$ przy $25$ Hz | - | N | $8\%$ | EGEA 3.19 |
"""
    st.markdown(table_md)