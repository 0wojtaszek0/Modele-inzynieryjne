#!/bin/bash

# ============================================================================
# EGEA SUSPENSION TESTER - SKRYPT URUCHAMIAJĄCY
# ============================================================================

echo "🚗 EGEA Suspension Tester v2.0"
echo "================================"

# Sprawdzenie Pythona
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 nie znaleziony. Zainstaluj Python 3.8 lub wyżej."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python3 $PYTHON_VERSION znaleziony"

# Sprawdzenie wymaganych pakietów
echo "✓ Sprawdzanie zależności..."

REQUIRED_PACKAGES=("streamlit" "numpy" "pandas" "plotly" "scipy" "matplotlib")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    python3 -c "import $package" 2>/dev/null
    if [ $? -ne 0 ]; then
        MISSING_PACKAGES+=($package)
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo "⚠️ Brakujące pakiety: ${MISSING_PACKAGES[@]}"
    echo "📦 Instaluję zależności..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Instalacja nie powiodła się. Spróbuj: pip install -r requirements.txt"
        exit 1
    fi
fi

echo "✅ Wszystkie zależności zainstalowane"
echo ""
echo "🚀 Uruchamianie aplikacji..."
echo "📌 Aplikacja będzie dostępna na: http://localhost:8501"
echo ""
echo "💡 Aby zatrzymać aplikację, naciśnij Ctrl+C"
echo ""

streamlit run src/app.py

