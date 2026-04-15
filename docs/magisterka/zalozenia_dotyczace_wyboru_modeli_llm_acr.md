# Zalozenia dotyczace wyboru modeli LLM

## 1. Zakres i cel analityczny

Na etapie analizy problemu celem nie jest jeszcze opis implementacji, lecz okreslenie zasad, wedlug ktorych mozna racjonalnie wybierac modele LLM do automatycznego code review.

Punkt wyjscia: wybor modelu jest decyzja wielokryterialna, a nie jednowymiarowym rankingiem "najlepszego" modelu.

## 2. Dlaczego wybor modelu jest trudny

Z literatury i analizy stanu badan wynikaja jednoczesnie sprzeczne wymagania:

- wysoka trafnosc merytoryczna komentarzy,
- niskie ryzyko halucynacji i regresji,
- akceptowalny koszt i opoznienie inferencji,
- stabilny, parsowalny format odpowiedzi,
- odpornosc na zmiany promptu i kontekstu.

Konsekwencja: nie istnieje jeden model optymalny dla wszystkich scenariuszy review.

## 3. Zalozenia metodologiczne (poziom problemu)

### ZA-M-01. Zadanie review jest heterogeniczne

Komentarze review dotycza roznych wymiarow (poprawnosc, utrzymywalnosc, bezpieczenstwo, styl, architektura), wiec ocena modelu musi obejmowac rozne typy przypadkow.

### ZA-M-02. Ocena jakosci nie moze opierac sie tylko na metrykach tekstowych

Miary typu BLEU/ROUGE/METEOR sa pomocnicze i nie wystarczaja do oceny uzytecznosci technicznej komentarza.

### ZA-M-03. Kontekst jest czynnikiem pierwszorzednym

Jakosc predykcji zalezy od jakosci i adekwatnosci kontekstu, a nie tylko od samego modelu.

### ZA-M-04. Niepewnosc modelu jest cecha systemowa

Niedeterministycznosc odpowiedzi LLM nalezy traktowac jako naturalne ograniczenie, ktore wymaga procedur kontrolnych.

## 4. Zalozenia merytoryczne doboru modeli (poziom decyzji)

### ZA-D-01. Dobor modelu musi byc zadaniowy

Inne wymagania ma generacja komentarza, inne ekstrakcja sygnalow z raportow narzedziowych, a inne analiza zmian wysokiego ryzyka.

### ZA-D-02. Priorytet ma wiarygodnosc komentarza

Komentarz uznaje sie za wartosciowy, gdy jest:

- trafny,
- uzasadniony,
- weryfikowalny,
- operacyjny dla recenzenta (actionable).

### ZA-D-03. Koszt i czas sa ograniczeniami twardymi

Model o najwyzszej jakosci nie jest domyslnie najlepszy, jesli jego koszt i latency uniemozliwiaja praktyczne uzycie w procesie review.

### ZA-D-04. Stabilnosc formatu wyjscia jest krytyczna

W zastosowaniach review model musi utrzymywac przewidywalny format odpowiedzi, bo od tego zalezy dalsza analiza i publikacja komentarzy.

### ZA-D-05. Model bez uziemienia kontekstem nie powinien byc traktowany jako autorytatywny

Ocena zmian bez odniesienia do danych projektowych podnosi ryzyko ogolnikowosci i falszywych wnioskow.

### ZA-D-06. Human-in-the-loop pozostaje warunkiem bezpieczenstwa

Na etapie obecnego stanu badan modele powinny wspierac recenzenta, nie zastepowac decyzji koncowej.

## 5. Kryteria analizy wyboru modelu

| Kryterium | Pytanie analityczne |
|---|---|
| Trafnosc merytoryczna | Czy model poprawnie identyfikuje problem i jego lokalizacje? |
| Uzytecznosc | Czy komentarz prowadzi do konkretnej poprawki? |
| Bezpieczenstwo | Jakie jest ryzyko sugerowania zmian pogarszajacych kod? |
| Stabilnosc | Jak bardzo wynik zalezy od drobnych zmian promptu/kontekstu? |
| Koszt | Jaki jest koszt tokenowy uzyskania komentarza uzytecznego? |
| Czas odpowiedzi | Czy model miesci sie w wymaganiach procesu review? |
| Odpornosc na szum kontekstowy | Jak model reaguje na czesciowo nieadekwatny kontekst? |

## 6. Hipotezy robocze dla dalszych rozdzialow

1. Architektura wielomodelowa powinna dawac lepszy kompromis jakosc-koszt niz podejscie jednomodelowe.
2. Selektywnie podawany kontekst powinien poprawiac trafnosc bardziej niz samo zwiekszanie liczby tokenow kontekstu.
3. Walidacja funkcjonalna i kryteria uzytecznosci powinny lepiej przewidywac wartosc komentarzy niz metryki leksykalne.
4. Eskalacja do mocniejszego modelu tylko w przypadkach wysokiego ryzyka powinna obnizac koszt sredni bez utraty jakosci krytycznej.

## 7. Ryzyka metodologiczne

- Ryzyko przeceniania metryk tekstowych.
- Ryzyko stronniczosci danych referencyjnych.
- Ryzyko mieszania oceny modelu z ocena jakosci kontekstu.
- Ryzyko nadmiernego uproszczenia zadania review do jednego wskaznika.

## 8. Wniosek pod podrozdzial

Dobor modeli LLM do automatycznego code review nalezy opisywac jako problem decyzji wielokryterialnej pod niepewnoscia, gdzie jakosc, wiarygodnosc, koszt i czas pozostaja wspolzalezne, a skutecznosc zalezy od dopasowania modelu do typu zadania i jakosci kontekstu, a nie od samej marki lub wielkosci modelu.

## 9. Material zrodlowy wykorzystany do analizy

- [src/5-1-prompt-based-cr.tex](src/5-1-prompt-based-cr.tex)
- [src/5-2-fine-tune-cr.tex](src/5-2-fine-tune-cr.tex)
- [src/5-3-rag-cr.tex](src/5-3-rag-cr.tex)
- [src/5-4-llm-and-static-cr.tex](src/5-4-llm-and-static-cr.tex)
- [src/5-5-eval.tex](src/5-5-eval.tex)
- [src/6-sum.tex](src/6-sum.tex)
