# EGEA Suspension Tester

Advanced application for vehicle suspension diagnostic analysis according to EGEA standards (European Gauge of Automotive).

## Functionality

### Simulation Mode

- Full Quarter-Car Model (2 DOF) implementation
- Adjustable parameters: mass, stiffness, damping
- Simulation following 4 EGEA phases:
  - Phase 1: Startup 0-25 Hz (2 s)
  - Phase 2: Stabilization 25 Hz (~6.8 s)
  - Phase 3: Preparation 25-18 Hz (2 s)
  - Phase 4: Measurement 18-6 Hz (7.5 s) [measurement range]
  - Phase 5: Decay 6-0 Hz (3 s)

### Data Import Mode

- CSV file upload (format: time, force, sensor signal)
- Automatic signal filtering
- Peak detection and analysis
- Phase shift calculation

### Key Indicators

Minimum phase shift ($$\phi_{min}$$) is calculated as:

$$\phi_{min} = \arccos\left(\frac{F_{min} - \bar{F}}{\Delta F/2}\right)$$

where:
- $$F_{min}$$: minimum force in measurement range
- $$\bar{F}$$: average force = ($$F_{max}$$ + $$F_{min}$$)/2
- $$\Delta F$$: force amplitude = ($$F_{max}$$ - $$F_{min}$$)/2

Additional indicators:
- EUSAMA Index: $$\text{EUSAMA} = \frac{F_{min}}{F_{st}} \times 100\%$$
- RFA_max: Relative force amplitude
- Number of oscillation cycles

## Installation

```bash
pip install -r requirements.txt
```

## Running the Application

```bash
streamlit run app.py
```

Access at: http://localhost:8501

## Quarter-Car Model Parameters

The 2 DOF Quarter-Car Model uses:

| Parameter | Description | Default | Unit |
|-----------|-------------|---------|------|
| M | Sprung mass | 346 | kg |
| m | Unsprung mass | 36 | kg |
| k_M | Suspension stiffness | 25570 | N/m |
| k_m | Tire stiffness | 253161 | N/m |
| c_M | Damper coefficient | 1474 | N·s/m |
| c_m | Tire damping | 150 | N·s/m |
| d | Excitation amplitude | 0.003 | m |

## Mathematical Model

The system is described by 4 second-order differential equations:

$$\ddot{x}_m = -\frac{k_M + k_m}{m}x_m + \frac{k_M}{m}x_M - \frac{c_M + c_m}{m}\dot{x}_m + \frac{c_M}{m}\dot{x}_M + \frac{k_m z(t) + c_m\dot{z}(t)}{m}$$

$$\ddot{x}_M = \frac{k_M}{M}x_m - \frac{k_M}{M}x_M + \frac{c_M}{M}\dot{x}_m - \frac{c_M}{M}\dot{x}_M$$

Platform excitation:

$$z(t) = -d \cos(\theta(t))$$

## EGEA Standard

| Symbol | Description | Range | Tolerance |
|--------|-------------|-------|-----------|
| $$\phi_{min}$$ | Minimum phase shift | 0-180° | ±3° (>30°) |
| $$F_{st}$$ | Static force | 100-1100 daN | ±2% |
| RFA_max | Max relative amplitude | 0-100% | ±5% |
| $$h_{PS}$$ | Platform stroke p-p | 6 mm | ±0.3 mm |
| $$\Delta T_{meas}$$ | Measurement time | 7.5 s | ±2 Hz |
| $$\Delta T_{25}$$ | Stabilization time | $$F_{st} \times 0.16 + 1200$$ ms | - |

## Interface

- Phase Shift Analysis: Detailed analysis of minimum phase shift
- Plots: Frequency profile, motion, forces, trajectories
- EGEA Parameters: Standard values and tolerances
- Export: Results download and reporting

## Status

Production Ready

Version: 2.0

