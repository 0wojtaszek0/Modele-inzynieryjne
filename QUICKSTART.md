# Quick Start - EGEA Suspension Tester v2.0

## Running in 3 Steps

### 1. Install Dependencies (first time only)
```bash
pip install -r requirements.txt
```

### 2. Launch Application
```bash
streamlit run app.py
```

### 3. Open in Browser
```
http://localhost:8501
```

---

## Basic Usage

### Simulation Mode (Default)
1. Select **"Simulation"** in sidebar
2. Click **"Run Simulation"**
3. Wait ~3 seconds for computation
4. Review results in 4 tabs

### Import Real Data
1. Select **"Import Data"**
2. Upload CSV file (format: time [s], force [N], signal [0/1])
3. Enter F_st (static force in N)
4. Click **"Analyze Data"**

---

## What You'll See

| Tab | Content |
|-----|---------|
| **Phase Shift Analysis** | Minimum phase shift calculation and interpretation |
| **Plots** | Frequency profile, motion, forces, mass trajectories |
| **EGEA Parameters** | Standard values and tolerances |
| **Export** | Download results and generate reports |

---

## Key Indicators

- **phi_min (degrees)**: Minimum phase shift - primary performance indicator
- **EUSAMA Index**: Percentage - functional damper > 50%
- **RFA_max**: Relative force amplitude percentage

---

## Important Files

- README.md - Complete technical documentation
- presentation.html - Professional overview (open in browser)
- example_measurement.csv - Sample data for testing

---

## Model Parameters

In the sidebar you can adjust:
- **M** - Sprung mass [kg]
- **m** - Unsprung mass [kg]
- **k_M** - Suspension stiffness [N/m]
- **k_m** - Tire stiffness [N/m]
- **c_M** - Damper coefficient [N·s/m]
- **c_m** - Tire damping [N·s/m]
- **d** - Excitation amplitude [m]

Change values and click "Run Simulation" again!

---

## Tips

- Experiment: Vary damping (c_M) and observe phi_min changes
- Save results: Download CSV from Export tab
- Compare: Run multiple simulations with different parameters
- Analyze: Import real measurements and compare with theory

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| App won't start | `pip install -r requirements.txt` |
| Simulation hangs | Reduce sampling frequency (e.g., 5000 Hz) |
| CSV won't load | Check: 3 columns, comma or semicolon separator |
| Empty plots | Click button again and wait for results |

---

## More Information

See **presentation.html** for professional overview

Version: 2.0 | Status: Production Ready

