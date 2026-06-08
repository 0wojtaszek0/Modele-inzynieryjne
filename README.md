# Stanowisko EGEA – Diagnostyka Zawieszenia Pojazdu

Aplikacja inżynierska realizująca **metodę minimalnego przesunięcia fazowego φₘᵢₙ**
zgodnie ze specyfikacją **EGEA SPECSUS2018** (European Garage Equipment
Association, *Suspension Tester Specifications*). Projekt obejmuje pełną
implementację modeli dynamicznych zawieszenia (1 DOF i 2 DOF), procedurę
*MinPhaseShift* z rozdziałów 3.7–3.22 normy oraz interaktywny interfejs
oparty o **Streamlit**.

---

## Spis treści

1. [Funkcjonalność](#funkcjonalność)
2. [Instalacja i uruchomienie](#instalacja-i-uruchomienie)
3. [Struktura projektu](#struktura-projektu)
4. [Tryby pracy aplikacji](#tryby-pracy-aplikacji)
5. [Kluczowe wskaźniki diagnostyczne](#kluczowe-wskaźniki-diagnostyczne)
6. [Wieloskładnikowa diagnoza amortyzatora](#wieloskładnikowa-diagnoza-amortyzatora)
7. [Modele matematyczne](#modele-matematyczne)
8. [Procedura MinPhaseShift](#procedura-minphaseshift-rozdz-37–322-normy)
9. [Domyślne parametry pojazdu](#domyślne-parametry-pojazdu)
10. [Format pliku CSV](#format-pliku-csv)
11. [Założenia i ograniczenia](#założenia-i-ograniczenia)
12. [Testy modułów (bez UI)](#testy-modułów-bez-ui)
13. [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Funkcjonalność

Aplikacja oferuje trzy uzupełniające się tryby pracy:

1. **Symulacja modelu ćwiartkowego (2 DOF)** – pełna symulacja stanowiska
   z pełnym profilem zmienności częstotliwości wg rozdz. 5.4 normy.
2. **Import pomiaru z pliku CSV** – analiza rzeczywistych przebiegów
   `(t, F, S)` algorytmem MinPhaseShift.
3. **Analiza parametryczna φₘᵢₙ(c)** – wykres zależności minimalnego
   przesunięcia fazowego od współczynnika tłumienia (model 1 DOF).

Wszystkie wzory matematyczne renderowane są w LaTeX w obrębie UI.

---

## Instalacja i uruchomienie

### Wymagania

- Python ≥ 3.9
- Biblioteki: `streamlit`, `numpy`, `pandas`, `scipy`, `plotly`, `matplotlib`
  (pełna lista w `requirements.txt`)

### Krok 1 – instalacja zależności

```bash
pip install -r requirements.txt
```

### Krok 2 – uruchomienie

Wariant zalecany (skrypt sprawdza zależności):

```bash
./START.sh
```

Wariant bezpośredni:

```bash
streamlit run src/app.py
```

Aplikacja otworzy się w przeglądarce pod adresem `http://localhost:8501`.

### Sprawdzenie poprawności instalacji

Po uruchomieniu domyślnej symulacji 2 DOF (przy parametrach fabrycznych)
powinno się wyświetlić:

| Wskaźnik   | Wartość oczekiwana |
|------------|--------------------|
| φₘᵢₙ       | ≈ 88°              |
| EUSAMA     | ≈ 57 %             |
| RFA_max    | ≈ 43 %             |
| F_st       | ≈ 3 747 N          |

Jeżeli wartości są zbliżone – aplikacja działa poprawnie.

---

## Struktura projektu

```
Aplikacja_EGEA/
├── src/                          – kod aplikacji
│   ├── app.py                    – interfejs Streamlit (trzy tryby)
│   ├── egea_suspension_model.py  – modele 2 DOF i 1 DOF + generator wymuszeń EGEA
│   └── phase_shift.py            – algorytm MinPhaseShift (φ(i), φₘᵢₙ)
│
├── web/                          – statyczna strona dokumentacyjna
│   ├── index.html                – główna dokumentacja techniczna w HTML
│   ├── presentation.html         – prezentacja projektu
│   ├── README.html               – README wyrenderowane do HTML
│   ├── CHANGELOG.html            – historia zmian (HTML)
│   ├── style.css                 – arkusz stylów
│   └── main.js                   – skrypty UI strony
│
├── docs/                         – dokumentacja i materiały referencyjne
│   ├── dokumentacja.pdf          – pełna dokumentacja projektu (LaTeX → PDF)
│   ├── dokumentacja.tex          – źródło LaTeX
│   ├── INSTRUKCJA.txt            – instrukcja użytkownika
│   ├── PODSUMOWANIE.txt          – streszczenie projektu
│   └── 08 EGEA Suspension Tester Specifications FINAL.pdf  – norma referencyjna
│
├── data/                         – dane testowe
│   └── example_measurement.csv   – przykładowy pomiar (t, F, S)
│
├── START.sh                      – skrypt uruchamiający z weryfikacją zależności
├── requirements.txt              – lista pakietów Pythona
├── README.md                     – ten plik
├── QUICKSTART.md                 – szybki start dla użytkownika
├── CHANGELOG.md                  – historia zmian
└── app_old.py                    – archiwalna wersja aplikacji (przed v3.0)
```

---

## Tryby pracy aplikacji

### Tryb 1 – Symulacja modelu ćwiartkowego (2 DOF)

Pełna symulacja stanowiska. Implementowane są wszystkie fazy procedury
EGEA (rozdz. 5.4 normy):

| Faza | Opis                                       | Czas trwania                  |
|------|--------------------------------------------|-------------------------------|
| 1    | Rozruch: 2 → 25 Hz                         | 2 s                           |
| 2    | Stabilizacja przy 25 Hz                    | ΔT₂₅ = F_st·0.16 + 1200 [ms]  |
| 3    | Przejście 25 → 18 Hz                       | 2 s                           |
| 4    | **Rampa pomiarowa 18 → 6 Hz**              | ΔT_meas = 7.5 s               |
| 5    | Wygaszenie 6 → 0 Hz                        | 3 s                           |

Wynikowe zakładki:

- **Wyniki kluczowe** – metryki diagnostyczne + interpretacja wyniku
- **Przebiegi czasowe** – f(t), z(t), F(t), trajektorie mas x_m, x_M
- **Krzywa φ(f)** – charakterystyka fazowa w pasmie pomiarowym
- **Parametry EGEA** – tabela wskaźników i tolerancji wg normy
- **Eksport** – pobieranie pełnego przebiegu (CSV) i raportu tekstowego

### Tryb 2 – Import pomiaru z pliku CSV

Wczytuje rzeczywisty pomiar w formacie `t, F, S` i wyznacza φₘᵢₙ
pełną procedurą MinPhaseShift (patrz niżej). Aplikacja sama wyznacza
F_st (średnia z pierwszych 0,5 s) albo można podać wartość ręcznie.

### Tryb 3 – Analiza parametryczna φₘᵢₙ(c)

Wykorzystuje model 1 DOF do wyznaczenia zależności φₘᵢₙ od współczynnika
tłumienia. Dla każdej wartości *c* z wybranego zakresu obliczana jest
analityczna odpowiedź ustalona układu, krzywa φ(f) w przedziale 6–18 Hz
oraz jej minimum. Wynik prezentowany jako:

- wykres φₘᵢₙ(c) z naniesionym kryterium AC_φₘᵢₙ = 35°,
- rodzina krzywych φ(f) dla 8 reprezentatywnych wartości *c*,
- tabela liczbowa z oznaczeniem sprawny / niesprawny,
- wyznaczenie c_kryt – wartości tłumienia, przy której φₘᵢₙ = 35°.

---

## Kluczowe wskaźniki diagnostyczne

| Symbol     | Opis                                                        | Wartość referencyjna |
|------------|-------------------------------------------------------------|----------------------|
| φₘᵢₙ       | Minimalne przesunięcie fazowe w paśmie 6–18 Hz              | **AC_φₘᵢₙ = 35°**    |
| φₘₐₓ       | Maks. przesunięcie przy 18 Hz (informacyjne)                | —                    |
| F_st       | Statyczne obciążenie koła = (M+m)·g                          | 100–1100 daN         |
| F_min      | Minimum siły kontaktu opona–płyta w paśmie pomiarowym       | > 0 (brak odrywania) |
| RFA_max    | Maksymalna względna amplituda F(t) = FA_max / F_st · 100 %  | 0–100 %              |
| H₂₅        | Amplituda F(t) przy stabilizacji 25 Hz                      | informacyjne         |
| rig        | Sztywność opony = 0,571·H₂₅/eₚ + 46                          | 160–400 N/mm         |
| EUSAMA     | Wskaźnik historyczny = F_min / F_st · 100 %                  | ≥ 45 % zalecane      |
| f_res      | Częstotliwość rezonansu masy nieresorowanej                 | typowo 10–15 Hz      |

Tolerancje normowe (rozdz. 6.1.4):

| Wielkość          | Powtarzalność | Błąd całkowity |
|-------------------|---------------|-----------------|
| φₘᵢₙ > 30°        | ±3°           | 7,5°            |
| φₘᵢₙ = 0°         | ±6°           | 15°             |
| RFA_max           | ±1,5 %        | 5 %             |
| H₂₅               | ±24 daN       | 8 %             |
| F_st ≥ 300 daN    | ±2 %          | ±2 %            |
| F_st < 300 daN    | ±6 daN        | ±6 daN          |

---

## Wieloskładnikowa diagnoza amortyzatora

W modelu 2 DOF samo kryterium `φₘᵢₙ ≥ 35°` nie wystarcza – ze względu na
strukturalnie wysoką wartość φₘᵢₙ przy każdym sensownym tłumieniu
(rezonans masy nieresorowanej dominuje fazę). Aplikacja łączy więc trzy
niezależne wskaźniki w funkcji `kategoryzuj_amortyzator()` w `src/app.py`:

| Warunek                                                | Status         |
|--------------------------------------------------------|----------------|
| F_min < 0 (koło traci kontakt z płytą)                 | **NIESPRAWNY** |
| EUSAMA < 30 %                                          | **NIESPRAWNY** |
| φₘᵢₙ < 25°                                              | **NIESPRAWNY** |
| 25° ≤ φₘᵢₙ < 35°                                       | GRANICZNY      |
| EUSAMA < 45 %                                          | GRANICZNY      |
| φₘᵢₙ ≥ 35° **oraz** EUSAMA ≥ 45 % **oraz** F_min ≥ 0   | **SPRAWNY**    |

Ta sama funkcja jest źródłem oceny w UI (zakładka „Wyniki kluczowe") oraz
w eksportowanym raporcie tekstowym – dzięki temu obie oceny są zawsze
spójne. Aby zasymulować niesprawny amortyzator w trybie 2 DOF wystarczy
ustawić jednocześnie:

- c_M ≈ 100–300 N·s/m
- c_m ≈ 10–30 N·s/m

– wówczas EUSAMA spada poniżej 30 % lub F_min schodzi poniżej zera.

> W trybie CSV stosowane jest pojedyncze kryterium `φₘᵢₙ ≥ 35°` – tak,
> jak przewiduje norma dla rzeczywistego stanowiska. Wieloskładnikowa
> diagnoza jest specyficzna dla symulacji 2 DOF.

---

## Modele matematyczne

### Model ćwiartkowy 2 DOF (`ModelCwiartkowy`)

Wektor stanu **X** = [x_m, x_M, ẋ_m, ẋ_M]ᵀ.

Równania ruchu mas nieresorowanej i resorowanej:

```
m·ẍ_m = −(k_M + k_m)·x_m + k_M·x_M − (c_M + c_m)·ẋ_m + c_M·ẋ_M + k_m·z(t) + c_m·ż(t)
M·ẍ_M = k_M·x_m − k_M·x_M + c_M·ẋ_m − c_M·ẋ_M
```

Postać macierzowa Ẋ = A·X + B(t):

```
        ┌  0                 0          1                0          ┐
A =     │  0                 0          0                1          │
        │ −(k_m+k_M)/m       k_M/m     −(c_m+c_M)/m      c_M/m      │
        └  k_M/M            −k_M/M      c_M/M           −c_M/M      ┘

                              ┌    0                          ┐
                              │    0                          │
B(t) =                        │  ( k_m·z(t) + c_m·ż(t) ) / m  │
                              └    0                          ┘
```

Całkowanie równań – `scipy.integrate.odeint`.

Wymuszenie kinematyczne płyty:  **z(t) = +d·cos(θ(t))**,
gdzie θ(t) jest fazą cykli o zmiennej częstotliwości f(t).

Konwencja: TOP płyty (najwyższe położenie) w θ = 0, BOTTOM w θ = π.
ST_i (impuls czujnika) wyzwalany w TOP, zgodnie z konwencją sprzętową EGEA
(rozdz. 3.8 normy).

Siła kontaktu opony z płytą (rozdz. 3.6 normy):

```
F(t) = F_st + k_m·(x_m − z) + c_m·(ẋ_m − ż)
```

Siła bezwładności pustej płyty (rozdz. 3.4):  `F_p(t) = m_p · z̈(t)`.

### Model jednomasowy 1 DOF (`ModelJednomasowy`)

Równanie ruchu:

```
m·ẍ + c·(ẋ − ż) + k·(x − z) = 0
```

Po przeniesieniu wymuszenia:  `m·ẍ + c·ẋ + k·x = c·ż + k·z`.

Konwencja wymuszenia (różna od 2 DOF dla wygody analitycznej):
**z(t) = −d·cos(ωt)**. Faza F(t) liczona jest względem maksimum −z(t),
czyli płyty w najwyższym położeniu, więc obie konwencje dają
porównywalny wynik φ.

Dla wymuszenia harmonicznego model ma rozwiązanie ustalone

```
X(ω) = |F₀(ω)| / √((k − m·ω²)² + (c·ω)²),
φ_x(ω) = arctan( c·ω / (k − m·ω²) ) − φ_{F₀}
```

z wymuszeniem zastępczym `F₀(t) = c·ż + k·z = A·cos(ωt) + B·sin(ωt)`,
gdzie A = −k·d, B = c·d·ω.

---

## Procedura MinPhaseShift (rozdz. 3.7–3.22 normy)

Moduł `phase_shift.py` realizuje sześć kroków normy:

1. **Detekcja znaczników ST_i** – pierwsza jedynka w grupie sąsiadujących
   jedynek sygnału S(t) (rozdz. 3.8).
2. **Kalibracja dynamiczna pustej płyty** – dla każdego okresu wyznaczenie
   ΔPeriod(i) = CalcTOP(i) − ST(i) (rozdz. 3.9–3.10). Gdy brak osobnego
   pomiaru pustej płyty, przyjmuje się ΔPeriod = 0 (ST zsynchronizowane
   z TOP – konwencja sprzętowa EGEA).
3. **Skorygowana chwila TOP**:  `TOPp(i) = ST(i) + ΔPeriod(i)` (rozdz. 3.11).
4. **Wyznaczenie F_ref(i)** jako środka między dwoma przecięciami F(t)
   z poziomem F_st, w oknie ograniczonym marginesami RFstFMin/RFstFMax = 25 %
   (rozdz. 3.7, 3.21).
5. **Przesunięcie fazowe okresu**:
   `φ(i) = 2π · (F_ref(i) − TOPp(i)) / Period(i)`, sprowadzane do 0°–180°.
6. **Minimum w paśmie pomiarowym**:
   `φₘᵢₙ = min φ(i)` dla `f(i) ∈ [6, 18] Hz` (rozdz. 3.22).

Sygnał F(t) jest wstępnie filtrowany filtrem Butterwortha 4. rzędu z
częstotliwością odcięcia 50 Hz przy użyciu `filtfilt` (zerowe przesunięcie
fazowe).

---

## Domyślne parametry pojazdu

Parametry modelu odpowiadają osi przedniej pojazdu kategorii M1 (osobowy):

| Parametr | Opis                          | Wartość | Jednostka |
|----------|-------------------------------|---------|-----------|
| M        | Masa resorowana (nadwozie)    | 346     | kg        |
| m        | Masa nieresorowana (koło)     | 36      | kg        |
| k_M      | Sztywność zawieszenia         | 25 570  | N/m       |
| k_m      | Sztywność opony               | 253 161 | N/m       |
| c_M      | Tłumienie amortyzatora        | 1 474   | N·s/m     |
| c_m      | Tłumienie opony               | 150     | N·s/m     |
| d        | Amplituda płyty (p-p = 6 mm)  | 3       | mm        |
| m_p      | Masa płyty wzbudnika          | 20      | kg        |
| f_s      | Częstotliwość próbkowania     | 2 000   | Hz        |

W trybie 1 DOF domyślne wartości: m = 382 kg, k = 253 161 N/m, c = zmienne.

---

## Format pliku CSV

Tryb 2 przyjmuje plik o co najmniej trzech kolumnach, w kolejności:

| Kolumna | Opis                                | Jednostka  |
|---------|-------------------------------------|------------|
| `t`     | Czas próbki                         | s          |
| `F`     | Siła kontaktu opony z płytą         | N          |
| `S`     | Sygnał wyzwalania czujnika płyty    | 0 / 1      |

Separator: `,`, `;` lub wykrywanie automatyczne. Przykład:

```csv
t,F,S
0.0000,3747.2,0
0.0005,3748.1,0
0.0010,3749.3,1
...
```

Przykładowy plik referencyjny: **`data/example_measurement.csv`** (wygenerowany
z domyślnej symulacji 2 DOF, fs = 1 kHz, sprawny amortyzator).

---

## Założenia i ograniczenia

1. **Model 2 DOF jest liniowy** – nie uwzględnia tarcia suchego, ogranicznika
   zawieszenia, nieliniowej charakterystyki amortyzatora dwustronnego ani
   utraty kontaktu opony z płytą (siła kontaktu może w symulacji przyjąć
   wartości ujemne; jest to interpretowane jako „liftoff").
2. **Model 1 DOF używa masy zastępczej** m = M + m (≈ 382 kg) na sprężynie
   opony k_m. Rezonans wypada przy ≈ 4 Hz, **poniżej** pasma pomiarowego
   6–18 Hz, więc krzywa φₘᵢₙ(c) jest monotonicznie rosnąca. To uproszczenie
   dydaktyczne pokazujące trend, a nie pełen model dynamiczny pojazdu.
3. **φₘᵢₙ w modelu 2 DOF** strukturalnie nie spada poniżej ≈ 75° dla
   całego sensownego zakresu c_M, c_m. Powód: rezonans masy nieresorowanej
   na ≈ 13 Hz dominuje fazę. Dlatego dla 2 DOF stosujemy wieloskładnikową
   diagnozę (φₘᵢₙ + EUSAMA + F_min). W trybie CSV (rzeczywisty pomiar)
   takiego problemu nie ma – obowiązuje czyste kryterium φₘᵢₙ ≥ 35°.
4. **Brak filtra NER** opisanego w referencji [10] normy – stosujemy
   prostszy Butterworth 50 Hz, co jest wystarczające dla syntetycznych
   przebiegów oraz pomiarów wolnych od silnych zakłóceń EMI.
5. **Kalibracja dynamiczna pustej płyty** w trybie CSV jest pomijana
   (`ΔPeriod = 0`) – zakładamy idealną synchronizację ST z TOP.
6. **Konwencja znaku z(t)** różni się między modelami: 2 DOF używa
   `z = +d·cos(θ)` (TOP w θ = 0), 1 DOF używa `z = −d·cos(ωt)`. Każdy
   model jest wewnętrznie spójny; rozbieżność wynika z analitycznej
   wygody w 1 DOF.

---

## Testy modułów (bez UI)

Każdy moduł posiada własny tryb diagnostyczny:

```bash
python3 src/egea_suspension_model.py   # symulacja 2 DOF + analiza 1 DOF
python3 src/phase_shift.py             # test algorytmu MinPhaseShift
```

Oczekiwane wyjście `egea_suspension_model.py`:

```
F_st       = 3747.2 N
dT25       = 1.800 s
EUSAMA     = ~57 %
phi_min(c=1474) ≈ 22° (model 1 DOF)
```

Oczekiwane wyjście `phase_shift.py`:

```
liczba okresów  > 100
phi_min         ≈ 85–90°
RFA_max         ≈ 40–45 %
H25             ≈ 90 N → rig ≈ 60 N/mm
```

---

## Rozwiązywanie problemów

| Problem                                          | Rozwiązanie                                                       |
|--------------------------------------------------|-------------------------------------------------------------------|
| `streamlit: command not found`                   | `pip install -r requirements.txt`, sprawdź PATH                   |
| Aplikacja nie startuje                           | Uruchom `./START.sh` – sprawdzi brakujące pakiety                |
| Symulacja zawiesza się przy fs ≥ 10 kHz          | Zmniejsz fs do 2000 Hz – Nyquist >> 36 Hz wystarcza               |
| `ModuleNotFoundError: egea_suspension_model`     | Uruchamiaj `streamlit run src/app.py` z głównego katalogu projektu|
| Plot/Plotly: błąd serializacji protobuf          | Już rozwiązany – używamy `Scattergl` zamiast `Scatter` dla dużych |
| CSV nie wczytuje się                             | Sprawdź separator (`,`, `;` lub auto) i kolejność kolumn `t,F,S`  |
| φₘᵢₙ = NaN                                       | Brak poprawnych impulsów S(t) lub F_st poza zakresem F(t)        |
| Wynik 2 DOF zawsze „sprawny"                     | Patrz sekcja [Wieloskładnikowa diagnoza](#wieloskładnikowa-diagnoza-amortyzatora) |

---

Wersja: 3.1 · Data: czerwiec 2026 · Licencja: projekt akademicki
