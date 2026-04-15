# Koncepcja dynamicznego doboru modelu

## 1. Cel analityczny

Na etapie analizy problemu koncepcja dynamicznego doboru modelu opisuje zasade podejmowania decyzji o klasie modelu LLM w zaleznosci od charakteru zadania review, bez wchodzenia w szczegoly implementacyjne.

Pytanie przewodnie: jak laczyc jakosc i bezpieczenstwo komentarzy z ograniczeniami kosztu i czasu?

## 2. Dlaczego potrzebny jest dobor dynamiczny

Podejscie statyczne (jeden profil modelu dla wszystkich przypadkow) prowadzi do dwoch przeciwstawnych bledow:

1. Przeszacowanie kosztu dla przypadkow prostych.
2. Niedoszacowanie jakosci dla przypadkow trudnych i wysokiego ryzyka.

Wniosek: dobor modelu powinien zalezec od trudnosci i ryzyka konkretnej zmiany, a nie od stalej reguly globalnej.

## 3. Definicja koncepcyjna

Dynamiczny dobor modelu to strategia, w ktorej decyzja o profilu inferencji jest funkcja cech analizowanego przypadku.

Formalizacja:

- wejscie: wektor cech X,
- decyzja: profil P,
- cel: minimalizacja kosztu lacznego

$$
J = \alpha \cdot (1 - Q) + \beta \cdot R + \gamma \cdot C + \delta \cdot T
$$

gdzie:

- $Q$ oznacza jakosc komentarza,
- $R$ oznacza ryzyko bledu/regresji,
- $C$ oznacza koszt inferencji,
- $T$ oznacza opoznienie.

## 4. Cechy decyzyjne na poziomie problemu

W analizie konceptualnej przyjmuje sie, ze decyzja moze zalezec od:

- zlozonosci zmiany (rozmiar, liczba fragmentow, heterogenicznosc),
- krytycznosci domenowej zmiany (np. bezpieczenstwo, logika biznesowa),
- jakosci i jednoznacznosci dostepnego kontekstu,
- obecnosci sygnalow narzedziowych wskazujacych wysokie ryzyko,
- niepewnosci poprzednich predykcji modelu.

## 5. Profile inferencji (model ogolny)

### Profil ekonomiczny

Stosowany dla przypadkow niskiego ryzyka i niskiej zlozonosci.

Cel: redukcja kosztu i czasu.

### Profil standardowy

Stosowany dla przypadkow typowych.

Cel: kompromis jakosc-koszt.

### Profil krytyczny

Stosowany dla przypadkow wysokiego ryzyka.

Cel: maksymalizacja wiarygodnosci komentarza kosztem wyzszej inferencji.

### Profil eskalacyjny

Stosowany, gdy wynik nie przechodzi kryteriow jakosciowych.

Cel: ponowna analiza z ostrzejszym profilem.

## 6. Regula decyzyjna (wersja analityczna)

1. Ocen zlozonosc przypadku.
2. Ocen ryzyko bledu i potencjalny koszt pomylki.
3. Przypisz profil inferencji adekwatny do pary (zlozonosc, ryzyko).
4. Zweryfikuj wynik przez quality gate.
5. W razie niespelnienia kryteriow uruchom eskalacje.

To podejscie realizuje zasade: "tani model dla prostego przypadku, mocny model dla przypadku krytycznego".

## 7. Quality gate na poziomie koncepcyjnym

Niezaleznie od klasy modelu wynik powinien spelniac minimalne warunki:

- trafnosc lokalizacji problemu,
- merytoryczna zgodnosc z dostepnymi dowodami,
- operacyjnosc sugestii (actionability),
- stabilnosc formatu odpowiedzi,
- brak sygnalow oczywistej halucynacji.

Jesli warunki nie sa spelnione, decyzja modelowa jest uznawana za niewystarczajaca.

## 8. Zwiazek z literatura

Koncepcja dynamiczna jest spojna z glownymi wnioskami z badan:

- sam model bez kontekstu ma ograniczona skutecznosc,
- jakosc zalezy od selektywnego podania kontekstu,
- metryki tekstowe sa niewystarczajace do oceny wartosci komentarza,
- ryzyko regresji uzasadnia wielowarstwowa walidacje,
- podejscia wieloetapowe i hybrydowe sa bardziej praktyczne niz monolityczne.

## 9. Hipotezy badawcze dla dalszej czesci pracy

1. Dynamiczny dobor modelu poprawia kompromis jakosc-koszt wzgledem doboru statycznego.
2. Profilowanie wedlug zlozonosci i ryzyka redukuje liczbe komentarzy niskiej wartosci.
3. Eskalacja warunkowa ogranicza koszt, utrzymujac jakosc dla przypadkow krytycznych.
4. Quality gate oparty o kryteria merytoryczne jest lepszym filtrem niz sama zgodnosc leksykalna.

## 10. Ograniczenia koncepcji

- Trudnosc wiarygodnej estymacji ryzyka przed inferencja.
- Ryzyko zbyt czestej eskalacji i utraty korzysci kosztowej.
- Wymagana kalibracja progow decyzyjnych.
- Potrzeba danych referencyjnych do porownan.

## 11. Wniosek pod podrozdzial

Koncepcja dynamicznego doboru modelu traktuje wybor LLM jako decyzje adaptacyjna pod niepewnoscia, gdzie profil inferencji musi zmieniac sie wraz ze zlozonoscia i ryzykiem przypadku, a skutecznosc systemu jest mierzona nie tylko jakoscia tekstu, lecz lacznym bilansem wiarygodnosci, bezpieczenstwa, kosztu i czasu.

## 12. Material zrodlowy wykorzystany do analizy

- [src/5-1-prompt-based-cr.tex](src/5-1-prompt-based-cr.tex)
- [src/5-2-fine-tune-cr.tex](src/5-2-fine-tune-cr.tex)
- [src/5-3-rag-cr.tex](src/5-3-rag-cr.tex)
- [src/5-4-llm-and-static-cr.tex](src/5-4-llm-and-static-cr.tex)
- [src/5-5-eval.tex](src/5-5-eval.tex)
- [src/6-sum.tex](src/6-sum.tex)
