# -*- coding: utf-8 -*-
"""
EGEA Suspension Tester - Aplikacja Inżynieryjna
Zaawansowana analiza diagnostyki zawieszenia pojazdu wg normy EGEA
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.integrate import odeint
from scipy.signal import find_peaks, butter, filtfilt
import io

st.set_page_config(
    page_title="EGEA Suspension Tester",
    page_icon="car",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("EGEA Suspension Tester")
st.markdown("Advanced suspension diagnostic analysis based on EGEA standards (Quarter-Car Model)")

# ============================================================================
# QUARTER-CAR MODEL CLASS
# ============================================================================
class EGEAQuarterCarModel:
    """Quarter-Car Model for vehicle suspension (2 DOF system)"""
    
    def __init__(self, M=346.0, m=36.0, kM=25570.0, km=253161.0, cM=1474.0, cm=150.0, d=0.003):
        self.M = M
        self.m = m
        self.kM = kM
        self.km = km
        self.cM = cM
        self.cm = cm
        self.d = d
        
        self.F_st = (M + m) * 9.81
        
        self.A = np.array([
            [0, 0, 1, 0],
            [0, 0, 0, 1],
            [-(km + kM)/m, kM/m, -(cm + cM)/m, cM/m],
            [kM/M, -kM/M, cM/M, -cM/M]
        ])
    
    def _get_target_frequency(self, t_val, dT25):
        T1 = 2.0
        T2_end = T1 + dT25
        T_prep = 2.0
        T3_start = T2_end + T_prep
        T_meas = 7.5
        T3_end = T3_start + T_meas
        T_ext = 3.0
        T4_end = T3_end + T_ext
        
        if t_val < T1:
            return 2.0 + (23.0 / T1) * t_val
        elif t_val < T2_end:
            return 25.0
        elif t_val < T3_start:
            return 25.0 - ((t_val - T2_end) / T_prep) * (25.0 - 18.0)
        elif t_val < T3_end:
            return 18.0 - ((t_val - T3_start) / T_meas) * (18.0 - 6.0)
        elif t_val < T4_end:
            return 6.0 - ((t_val - T3_end) / T_ext) * (6.0 - 0.0)
        else:
            return 0.0
    
    def simulate(self, fs=10000.0):
        dt = 1.0 / fs
        dT25_ms = self.F_st * 0.16 + 1200.0
        dT25 = dT25_ms / 1000.0
        
        T_total = 14.5 + dT25
        t = np.arange(0, T_total, dt)
        
        t_k = [0.0]
        f_k = []
        current_t = 0.0
        
        while current_t < T_total:
            target_f = self._get_target_frequency(current_t, dT25)
            if target_f > 0:
                period = 1.0 / target_f
                t_next = current_t + period
                if t_next > T_total:
                    t_next = T_total
                    period = t_next - current_t
                    if period > 0:
                        f_k.append(1.0 / period)
                    else:
                        f_k.append(0.0)
                    t_k.append(t_next)
                    break
                f_k.append(target_f)
                t_k.append(t_next)
                current_t = t_next
            else:
                if current_t < T_total:
                    if len(f_k) == 0 or f_k[-1] != 0:
                        f_k.append(0.0)
                        t_k.append(current_t + dt)
                    current_t += dt
                else:
                    break
        
        t_k = np.array(t_k)
        f_k = np.array(f_k)
        
        z = np.zeros_like(t)
        z_dot = np.zeros_like(t)
        f_step = np.zeros_like(t)
        
        current_k = 0
        for i, t_i in enumerate(t):
            while current_k < len(t_k) - 1 and t_i >= t_k[current_k + 1]:
                current_k += 1
            
            if current_k >= len(t_k) - 1:
                if len(f_k) > 0:
                    f_step[i] = f_k[-1]
                else:
                    f_step[i] = 0.0
                z[i] = z[i-1] if i > 0 else self.d
                z_dot[i] = 0.0
                continue
            
            t_current = t_k[current_k]
            t_next = t_k[current_k + 1]
            
            if (t_next - t_current) > 0:
                theta = 2 * np.pi * (t_i - t_current) / (t_next - t_current)
                theta_dot = 2 * np.pi / (t_next - t_current)
            else:
                theta = 0.0
                theta_dot = 0.0
            
            z[i] = -self.d * np.cos(theta)
            z_dot[i] = self.d * np.sin(theta) * theta_dot
            f_step[i] = f_k[current_k]
        
        def model(X, t_val):
            idx = int(t_val / dt)
            if idx >= len(z):
                idx = len(z) - 1
            z_val = z[idx]
            z_dot_val = z_dot[idx]
            B = np.array([0, 0, (self.km * z_val + self.cm * z_dot_val) / self.m, 0])
            return np.dot(self.A, X) + B
        
        X0 = [0, 0, 0, 0]
        X_sol = odeint(model, X0, t)
        
        x_m = X_sol[:, 0]
        x_M = X_sol[:, 1]
        v_m = X_sol[:, 2]
        v_M = X_sol[:, 3]
        
        F_dyn = self.km * (x_m - z) + self.cm * (v_m - z_dot)
        F_t = self.F_st + F_dyn
        
        idx_measure = np.where((f_step <= 18) & (f_step >= 6))[0]
        if len(idx_measure) > 0:
            F_min = np.min(F_t[idx_measure])
            eusama = (F_min / self.F_st) * 100
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
            'f_step': f_step,
            'eusama': eusama,
            'F_st': self.F_st,
            'dT25': dT25,
            'dt': dt
        }

def analyze_signal(t, F, f_step, F_st, fs=10000):
    dt = 1.0 / fs
    
    b, a = butter(4, 30.0 / (fs / 2), btype='low')
    F_filt = filtfilt(b, a, F)
    
    peaks, _ = find_peaks(F_filt, distance=fs/25, prominence=F_st*0.05)
    troughs, _ = find_peaks(-F_filt, distance=fs/25, prominence=F_st*0.05)
    
    amplitudes = []
    if len(peaks) > 0 and len(troughs) > 0:
        for p in peaks:
            closest_trough = troughs[np.argmin(np.abs(troughs - p))]
            amp = F_filt[p] - F_filt[closest_trough]
            amplitudes.append(amp)
    
    amplitudes = np.array(amplitudes) if amplitudes else np.array([0])
    RFA_max = (np.max(amplitudes) / F_st) * 100 if len(amplitudes) > 0 else 0
    
    idx_measure = np.where((f_step <= 18) & (f_step >= 6))[0]
    phase_shift_min = 0.0
    if len(idx_measure) > 0:
        F_measure = F_filt[idx_measure]
        F_min_val = np.min(F_measure)
        F_max_val = np.max(F_measure)
        F_avg = (F_max_val + F_min_val) / 2
        amplitude = (F_max_val - F_min_val) / 2
        
        if amplitude > 0:
            phase_shift_min = np.degrees(np.arccos((F_min_val - F_avg) / amplitude))
    
    return {
        'F_filt': F_filt,
        'peaks': peaks,
        'troughs': troughs,
        'amplitudes': amplitudes,
        'RFA_max': RFA_max,
        'num_cycles': len(peaks),
        'phase_shift_min': phase_shift_min
    }

# ============================================================================
# SIDEBAR CONFIGURATION
# ============================================================================

st.sidebar.header("Configuration")

mode = st.sidebar.radio("Working Mode:", ["Simulation", "Import Data"])

if mode == "Simulation":
    st.sidebar.subheader("Quarter-Car Model Parameters")
    
    col_m1, col_m2 = st.sidebar.columns(2)
    with col_m1:
        M = st.number_input("Sprung mass M (kg)", value=346.0, step=1.0)
        m = st.number_input("Unsprung mass m (kg)", value=36.0, step=1.0)
    
    with col_m2:
        kM = st.number_input("Suspension stiffness kM (N/m)", value=25570.0, step=100.0)
        km = st.number_input("Tire stiffness km (N/m)", value=253161.0, step=1000.0)
    
    col_c1, col_c2 = st.sidebar.columns(2)
    with col_c1:
        cM = st.number_input("Damper coefficient cM (N·s/m)", value=1474.0, step=10.0)
    
    with col_c2:
        cm = st.number_input("Tire damping cm (N·s/m)", value=150.0, step=10.0)
    
    d = st.sidebar.number_input("Excitation amplitude d (m)", value=0.003, step=0.0001, format="%.4f")
    fs = st.sidebar.number_input("Sampling frequency fs (Hz)", value=10000.0, step=1000.0)
    
    if st.sidebar.button("Run Simulation", use_container_width=True):
        with st.spinner("Running simulation..."):
            model = EGEAQuarterCarModel(M=M, m=m, kM=kM, km=km, cM=cM, cm=cm, d=d)
            results = model.simulate(fs=fs)
            st.session_state['simulation_data'] = results
            st.session_state['mode'] = 'simulation'
            st.success("Simulation completed!")

else:
    st.sidebar.subheader("Data Import")
    
    uploaded_file = st.sidebar.file_uploader(
        "Upload CSV file (columns: t, F, S)",
        type=['csv'],
        help="Format: time [s], force [N], sensor signal [0/1]"
    )
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.sidebar.success("File loaded!")
        
        F_st_input = st.sidebar.number_input("Static force F_st (N)", value=3820.0, step=10.0)
        
        if st.sidebar.button("Analyze Data", use_container_width=True):
            t_data = df.iloc[:, 0].values
            F_data = df.iloc[:, 1].values
            
            fs_est = 1.0 / np.mean(np.diff(t_data))
            
            analysis = analyze_signal(t_data, F_data, np.zeros_like(F_data), F_st_input, fs=int(fs_est))
            
            st.session_state['measured_data'] = {
                't': t_data,
                'F_t': F_data,
                'F_st': F_st_input,
                'analysis': analysis
            }
            st.session_state['mode'] = 'measured'
            st.success("Analysis completed!")

# ============================================================================
# MAIN CONTENT
# ============================================================================

if 'mode' in st.session_state:
    if st.session_state['mode'] == 'simulation':
        results = st.session_state['simulation_data']
        analysis = analyze_signal(
            results['t'], results['F_t'], results['f_step'], 
            results['F_st'], fs=1.0/results['dt']
        )
        
        tab1, tab2, tab3, tab4 = st.tabs(["Phase Shift Analysis", "Plots", "EGEA Parameters", "Export"])
        
        with tab1:
            st.header("Minimum Phase Shift Analysis")
            st.markdown("Minimum phase shift (phi_min) is the key indicator of damper performance")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("phi_min (degrees)", f"{analysis['phase_shift_min']:.2f}°")
            col2.metric("EUSAMA Index", f"{results['eusama']:.2f}%")
            col3.metric("RFA_max", f"{analysis['RFA_max']:.2f}%")
            
            st.markdown("### Phase Shift Theory")
            st.markdown("""
For a damped oscillator driven at frequency f:

$$\\phi_{min} = \\arccos\\left(\\frac{F_{min} - \\bar{F}}{\\Delta F/2}\\right)$$

where:
- F_min: minimum force in measurement range (18-6 Hz)
- F̄: average force = (F_max + F_min) / 2
- ΔF: force amplitude = (F_max - F_min) / 2

A good damper shows phi_min between 30° and 60°.
            """)
            
            idx_measure = np.where((results['f_step'] <= 18) & (results['f_step'] >= 6))[0]
            if len(idx_measure) > 0:
                F_measure = analysis['F_filt'][idx_measure] if 'F_filt' in analysis else results['F_t'][idx_measure]
                
                fig_phase = go.Figure()
                fig_phase.add_trace(go.Scatter(
                    x=results['t'][idx_measure], 
                    y=F_measure,
                    mode='lines', 
                    name='Force F(t)',
                    line=dict(color='blue', width=2)
                ))
                fig_phase.add_hline(y=results['F_st'], line_dash="dash", line_color="red", annotation_text="F_st")
                fig_phase.update_layout(
                    title="Force signal in measurement range (18-6 Hz)",
                    xaxis_title="Time (s)",
                    yaxis_title="Force (N)",
                    hovermode="x unified",
                    height=400,
                    width=None
                )
                st.plotly_chart(fig_phase, use_container_width=True)
        
        with tab2:
            st.header("Simulation Results")
            
            fig_freq = go.Figure()
            fig_freq.add_trace(go.Scatter(
                x=results['t'], y=results['f_step'],
                mode='lines', name='Frequency',
                line=dict(color='purple', width=2)
            ))
            
            meas_idx = np.where((results['f_step'] <= 18) & (results['f_step'] >= 6))[0]
            if len(meas_idx) > 0:
                fig_freq.add_vrect(
                    x0=results['t'][meas_idx[0]],
                    x1=results['t'][meas_idx[-1]],
                    fillcolor="yellow", opacity=0.2, layer="below", line_width=0,
                    annotation_text="Measurement range"
                )
            
            fig_freq.update_layout(
                title="Frequency sweep profile",
                xaxis_title="Time (s)", yaxis_title="Frequency (Hz)",
                hovermode="x unified", height=400, width=None
            )
            st.plotly_chart(fig_freq, use_container_width=True)
            
            fig_force = make_subplots(specs=[[{"secondary_y": True}]])
            fig_force.add_trace(
                go.Scatter(x=results['t'], y=results['z']*1000, name='Platform displacement',
                          line=dict(color='blue', width=2)),
                secondary_y=False
            )
            fig_force.add_trace(
                go.Scatter(x=results['t'], y=results['F_t'], name='Contact force',
                          line=dict(color='orange', width=2)),
                secondary_y=True
            )
            fig_force.add_hline(
                y=results['F_st'], line_dash="dash", line_color="red",
                secondary_y=True, annotation_text="F_st"
            )
            fig_force.update_layout(
                title="Platform motion and contact force",
                xaxis_title="Time (s)", height=400, width=None,
                hovermode="x unified"
            )
            fig_force.update_yaxes(title_text="Displacement (mm)", secondary_y=False)
            fig_force.update_yaxes(title_text="Force (N)", secondary_y=True)
            st.plotly_chart(fig_force, use_container_width=True)
            
            fig_trajectory = go.Figure()
            fig_trajectory.add_trace(go.Scatter(
                x=results['t'], y=results['x_m']*1000, name='Unsprung mass x_m',
                line=dict(color='green', width=2)
            ))
            fig_trajectory.add_trace(go.Scatter(
                x=results['t'], y=results['x_M']*1000, name='Sprung mass x_M',
                line=dict(color='brown', width=2)
            ))
            fig_trajectory.update_layout(
                title="System mass trajectories",
                xaxis_title="Time (s)", yaxis_title="Displacement (mm)",
                height=400, hovermode="x unified", width=None
            )
            st.plotly_chart(fig_trajectory, use_container_width=True)
        
        with tab3:
            st.header("EGEA Standard Parameters")
            
            params_data = {
                'Parameter': ['phi_min', 'F_st', 'RFA_max', 'f_measurement', 'Excitation amplitude', 'dT_meas', 'dT_25'],
                'Description': ['Min phase shift', 'Static force', 'Max relative force amplitude', 'Measurement range', 'Platform stroke p-p', 'Measurement time (18->6 Hz)', 'Stabilization time at 25 Hz'],
                'Range': ['0-180°', '100-1100 daN', '0-100%', '6-18 Hz', '6 mm', '7.5 s', f'{results["dT25"]:.2f} s'],
                'Tolerance': ['±3° (>30°)', '±2%', '±5%', '±1 Hz', '±0.3 mm', '±2 Hz', '-']
            }
            
            df_params = pd.DataFrame(params_data)
            st.dataframe(df_params, use_container_width=True, hide_index=True)
        
        with tab4:
            st.header("Results Export")
            
            report = f"""EGEA Suspension Test Report
==============================

QUARTER-CAR MODEL PARAMETERS
-----------------------------
Sprung mass M: {M} kg
Unsprung mass m: {m} kg
Suspension stiffness kM: {kM} N/m
Tire stiffness km: {km} N/m
Damper coefficient cM: {cM} N*s/m
Tire damping cm: {cm} N*s/m
Excitation amplitude d: {d*1000:.3f} mm

TEST RESULTS
-----------
Static force F_st: {results['F_st']:.0f} N
Minimum phase shift: {analysis['phase_shift_min']:.2f} degrees
EUSAMA Index: {results['eusama']:.2f}%
RFA_max: {analysis['RFA_max']:.2f}%
Number of cycles: {analysis['num_cycles']}
Max amplitude: {np.max(analysis['amplitudes']):.2f} N

PHASE SHIFT INTERPRETATION
--------------------------
phi_min < 30°: Damper may be too stiff
30° <= phi_min <= 60°: Good damper performance
phi_min > 60°: Damper may be too soft
            """
            
            st.text_area("Test Report", value=report, height=250, disabled=True)
            
            results_df = pd.DataFrame({
                'Time (s)': results['t'],
                'Excitation (mm)': results['z'] * 1000,
                'Contact Force (N)': results['F_t'],
                'Frequency (Hz)': results['f_step'],
                'Unsprung displacement (mm)': results['x_m'] * 1000,
                'Sprung displacement (mm)': results['x_M'] * 1000
            })
            
            csv_buffer = io.StringIO()
            results_df.to_csv(csv_buffer, index=False, sep=';')
            csv_data = csv_buffer.getvalue()
            
            st.download_button(
                label="Download Results (CSV)",
                data=csv_data,
                file_name="EGEA_results.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    elif st.session_state['mode'] == 'measured':
        data = st.session_state['measured_data']
        analysis = data['analysis']
        
        st.subheader("Measured Data Analysis")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("F_st", f"{data['F_st']:.0f} N")
        m2.metric("phi_min", f"{analysis['phase_shift_min']:.2f}°")
        m3.metric("RFA_max", f"{analysis['RFA_max']:.2f}%")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data['t'], y=data['F_t'], name='Raw signal',
            line=dict(color='gray', width=1)
        ))
        fig.add_trace(go.Scatter(
            x=data['t'], y=analysis['F_filt'], name='Filtered',
            line=dict(color='blue', width=2)
        ))
        fig.add_hline(y=data['F_st'], line_dash="dash", line_color="red", annotation_text="F_st")
        fig.update_layout(
            title="Contact Force - Measured Data",
            xaxis_title="Time (s)", yaxis_title="Force (N)",
            hovermode="x unified", height=500, width=None
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Select working mode in the sidebar and enter data")
