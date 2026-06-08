# Szybki start – Stanowisko EGEA v3.0

## Uruchomienie w 3 krokach

### 1. Instalacja zależności (jednorazowo)
```bash
pip install -r requirements.txt
```

### 2. Uruchomienie aplikacji
```bash
streamlit run src/app.py
```

Albo prościej (skrypt sprawdza zależności):
```bash
./START.sh
```

### 3. Otwarcie w przeglądarce
```
http://localhost:8501
```

---

## Podstawowe użycie

### Tryb symulacji 2DOF (domyślny)
1. Wybierz **„Symulacja 2DOF"** w panelu bocznym.
2. Pozostaw lub zmień parametry pojazdu (M, m, kM, km, cM, cm, d).
3. Kliknij **„Uruchom symulację"**.
4. Wyniki pojawią się w pięciu zakładkach.

### Tryb importu CSV
1. Wybierz **„Import pomiaru (CSV)"**.
2. Wgraj plik o kolumnach `t, F, S` (czas, siła, sygnał ST).
3. Aplikacja sama wyznaczy F_st (lub podaj ręcznie).
4. Wyniki φ_min i krzywa φ(f) pojawią się natychmiast.

### Tryb analizy φ_min(c)
1. Wybierz **„Analiza φₘᵢₙ(c)"**.
2. Ustaw zakres c (np. 200–4000 N·s/m).
3. Kliknij **„Uruchom analizę parametryczną"**.
4. Otrzymasz wykres φ_min(c) oraz rodzinę krzywych φ(f).

---

## Co zobaczysz

| Zakładka                | Zawartość                                              |
|-------------------------|--------------------------------------------------------|
| **Wyniki kluczowe**     | φ_min, EUSAMA, RFA_max, H25, rig, fres                |
| **Przebiegi czasowe**   | f(t), z(t), F(t), trajektorie mas x_m, x_M             |
| **Krzywa φ(f)**         | Wykres przesunięcia fazowego w funkcji częstotliwości |
| **Parametry EGEA**      | Tabela parametrów i tolerancji wg normy SPECSUS2018   |
| **Eksport**             | Pobranie CSV i raportu tekstowego                      |

---

## Najważniejsze wskaźniki

- **φ_min [°]** – główny wskaźnik diagnostyczny (kryterium AC_φmin = 35°).
- **EUSAMA [%]** – historyczny wskaźnik adhezji koła.
- **RFA_max [%]** – maksymalna względna amplituda F(t).
- **rig [N/mm]** – sztywność opony (informacja o ciśnieniu).

---

## Sprawdzenie poprawności instalacji

Po uruchomieniu domyślnej symulacji powinno się wyświetlić:
- φ_min ≈ 88° (sprawny amortyzator),
- EUSAMA ≈ 57 %,
- RFA_max ≈ 43 %.

Jeżeli wartości wyglądają sensownie – wszystko działa poprawnie.

---

## Najważniejsze pliki

- `README.md` – pełna dokumentacja techniczna (Markdown)
- `web/index.html` – dokumentacja w przeglądarce
- `docs/INSTRUKCJA.txt` – instrukcja użytkownika
- `docs/dokumentacja.pdf` – pełna dokumentacja projektu (PDF)
- `data/example_measurement.csv` – przykładowy pomiar do testów
- `docs/08 EGEA Suspension Tester Specifications FINAL.pdf` – norma referencyjna

---

## Rozwiązywanie problemów

| Problem                          | Rozwiązanie                                       |
|----------------------------------|---------------------------------------------------|
| Aplikacja nie startuje           | `pip install -r requirements.txt`                 |
| Symulacja zawiesza się           | Zmniejsz f_s (np. 2000 Hz zamiast 10000 Hz)       |
| CSV nie wczytuje się             | Sprawdź separator i 3 kolumny `t, F, S`           |
| φ_min = NaN                       | Sprawdź sygnał S i F_st                            |

---

## Test modułów (bez UI)

```bash
python3 src/egea_suspension_model.py   # diagnostyka modelu 2DOF/1DOF
python3 src/phase_shift.py             # test algorytmu φ_min
```

Wersja: 3.0  |  Status: zgodna z EGEA SPECSUS2018
