# Kryteria oceny jakosci Code Review

## 1. Cel podrozdzialu

Celem podrozdzialu jest zdefiniowanie, jak oceniac jakosc automatycznego Code Review w sposob merytoryczny i porownywalny, tak aby wynik oceny odzwierciedlal rzeczywista wartosc komentarza dla recenzenta, a nie tylko podobienstwo tekstowe do komentarzy referencyjnych.

Punkt wyjscia analityczny: jakosc review jest wielowymiarowa i nie moze byc redukowana do jednej metryki.

## 2. Problem oceny jakosci review

W literaturze i praktyce ACR wystepuje roznica miedzy:

- jakoscia jezykowa komentarza,
- jakoscia merytoryczna komentarza,
- efektem technicznym po zastosowaniu sugestii.

To prowadzi do kluczowego problemu metodologicznego: komentarz moze byc dobrze sformulowany, ale nietrafny albo potencjalnie szkodliwy.

Wniosek: kryteria oceny musza laczyc perspektywe semantyczna, techniczna i procesowa.

## 3. Definicja jakosci Code Review

Na potrzeby analizy przyjmuje sie, ze komentarz review ma wysoka jakosc, gdy jednoczesnie:

1. Trafnie identyfikuje problem i jego lokalizacje.
2. Jest uzasadniony dostepnym kontekstem projektu.
3. Jest operacyjny (pozwala wykonac konkretna poprawke).
4. Nie podnosi nieakceptowalnie ryzyka regresji.
5. Jest zgodny ze standardami i priorytetami projektu.

## 4. Wymiary oceny jakosci

## 4.1. Trafnosc merytoryczna

Pytanie: czy komentarz odnosi sie do rzeczywistego problemu technicznego, a nie do artefaktu promptu lub szumu kontekstowego?

Uzasadnienie: literatura pokazuje ograniczona wiarygodnosc metryk leksykalnych jako przyblizenia wartosci technicznej komentarza.

## 4.2. Trafnosc lokalizacji (change localization)

Pytanie: czy komentarz wskazuje wlasciwy plik i linie zmiany?

Uzasadnienie: w benchmarkach dekomponujacych review (np. CTR, CL, SI) lokalizacja jest czestym waskim gardlem.

## 4.3. Uzytecznosc operacyjna (actionability)

Pytanie: czy recenzent, czytajac komentarz, wie co konkretnie poprawic i dlaczego?

Uzasadnienie: wysoka ogolnikowosc komentarzy jest jednym z najczesciej raportowanych problemow w badaniach ACR.

## 4.4. Zgodnosc normatywna

Pytanie: czy komentarz jest zgodny z zasadami projektu (reguly globalne, reguly per plik, polityki jakosci i bezpieczenstwa)?

Uzasadnienie: bez osi normatywnej rosnace ryzyko arbitralnosci i niespojnosci ocen.

## 4.5. Bezpieczenstwo techniczne sugestii

Pytanie: czy proponowana poprawka zmniejsza problem bez wprowadzania regresji?

Uzasadnienie: z perspektywy engineeringowej komentarz review ma wartosc tylko wtedy, gdy jego zastosowanie nie degraduje poprawnosci kodu.

## 4.6. Stabilnosc odpowiedzi

Pytanie: czy drobne zmiany promptu lub kontekstu nie powoduja silnie rozbieznych wnioskow?

Uzasadnienie: niedeterministycznosc modeli LLM jest cecha systemowa i musi byc jawnie uwzgledniona w ocenie.

## 4.7. Efektywnosc procesowa

Pytanie: czy jakosc komentarzy jest osiagana przy akceptowalnym koszcie i czasie odpowiedzi?

Uzasadnienie: w realnym workflow PR/MR przydatnosc narzedzia zalezy takze od latency i kosztu, nie tylko od jakosci semantycznej.

## 5. Operacjonalizacja kryteriow

Ponizsza tabela laczy kryteria z miernikami i danymi, ktore sa dostepne lub naturalnie wynikaja z artefaktow projektu.

| Kryterium | Przykladowe wskazniki | Zrodla danych | Ograniczenia |
|---|---|---|---|
| Trafnosc merytoryczna | ocena ekspercka trafnosci; semantyczne podobienstwo do komentarzy referencyjnych | komentarze wygenerowane i historyczne komentarze PR/MR | podobienstwo semantyczne nie gwarantuje poprawnosci technicznej |
| Trafnosc lokalizacji | generated_file_in_diff_rate; generated_line_in_hunk_rate | diff hunks + metadane komentarza (plik, linia) | komentarz globalny moze byc wartosciowy mimo braku linii |
| Actionability | odsetek komentarzy z konkretna sugestia i uzasadnieniem; ocena recenzenta | tresc komentarza, pole suggestion, ocena ekspercka | czesciowo subiektywna ocena szczegolowosci |
| Zgodnosc normatywna | zgodnosc z active rules (global/file patterns); odsetek komentarzy odrzuconych przez filtrowanie publikacji | konfiguracja regul, polityki severity, logika publikacji | reguly moga byc niepelne lub nieaktualne |
| Bezpieczenstwo techniczne | Correction Ratio; Regression Ratio; wynik testow po zastosowaniu sugestii | pipeline testowy, CI results, walidacja funkcjonalna | wysoki koszt pelnej walidacji dla kazdej sugestii |
| Stabilnosc | wariancja wynikow dla kontrolowanych zmian promptu/kontekstu | powtarzane uruchomienia na tym samym przypadku | brak pelnej deterministycznosci modeli |
| Efektywnosc procesowa | czas review, zuzycie tokenow, koszt jednostkowy komentarza uzytecznego | telemetry uruchomien, token usage, metryki ewaluacyjne | koszt zalezy od dostawcy, modelu i kontekstu |

## 6. Warstwy ewaluacji

Aby uniknac blednej oceny opartej na jednej klasie metryk, analiza powinna byc warstwowa.

### Warstwa A: Ewaluacja automatyczna (tekstowo-semantyczna)

Cel: szybkie porownanie wariantow modeli i promptow.

Przykladowe metryki:

- BLEU-4,
- ROUGE-L,
- METEOR,
- BERTScore,
- Exact Match (pomocniczo, z uwzglednieniem ograniczen).

### Warstwa B: Ewaluacja diagnostyczna (zrozumienie zmiany)

Cel: ocena czy model rozumie zmiane zanim zaproponuje rozwiazanie.

Przykladowe osie:

- rozpoznanie typu zmiany,
- lokalizacja zmiany,
- identyfikacja poprawnego kierunku naprawy.

### Warstwa C: Ewaluacja funkcjonalna

Cel: sprawdzenie efektu technicznego po zastosowaniu sugestii.

Przykladowe osie:

- czy poprawka naprawia problem,
- czy nie wprowadza regresji,
- czy przechodzi walidacje testowa.

### Warstwa D: Ewaluacja ekspercka

Cel: ocena wartosci komentarza z perspektywy recenzenta.

Przykladowe osie:

- trafnosc,
- actionability,
- zrozumialosc,
- adekwatnosc do standardow projektu.

### Warstwa E: Ewaluacja procesowa

Cel: ocena czy system jest praktycznie uzywalny w workflow PR/MR.

Przykladowe osie:

- opoznienie odpowiedzi,
- koszt,
- stabilnosc publikacji,
- odsetek komentarzy rzeczywiscie wykorzystanych przez zespol.

## 7. Kryteria minimalnej akceptacji jakosci (poziom analizy)

Na etapie analizy problemu przyjmuje sie, ze system review nie powinien byc uznany za dojrzaly, jezeli:

- nie utrzymuje satysfakcjonujacej trafnosci lokalizacji,
- generuje wysoki odsetek komentarzy ogolnikowych,
- nie ma mechanizmu kontroli ryzyka regresji,
- nie zapewnia zgodnosci z regulami projektu,
- osiagnieta jakosc wymaga nieakceptowalnego kosztu lub czasu.

Uwaga metodologiczna: konkretne progi liczbowe sa przedmiotem kalibracji eksperymentalnej i nie powinny byc arbitralnie ustalane bez danych referencyjnych.

## 8. Ryzyka metodologiczne w ocenie jakosci

- Ryzyko przeszacowania modeli przez metryki tekstowe.
- Ryzyko zanieczyszczenia danych referencyjnych i data leakage.
- Ryzyko mylenia jakosci modelu z jakoscia dostarczonego kontekstu.
- Ryzyko nieuwzglednienia roznic miedzy typami komentarzy (globalne vs inline).
- Ryzyko ignorowania kosztu i opoznienia przy interpretacji wynikow.

## 9. Wniosek pod podrozdzial

Ocena jakosci automatycznego Code Review powinna byc projektowana jako procedura wielokryterialna i wielowarstwowa, laczaca metryki semantyczne, poprawna lokalizacje, uzytecznosc operacyjna, zgodnosc z regulami projektu, ryzyko regresji oraz efektywnosc procesowa; dopiero laczna analiza tych wymiarow pozwala wiarygodnie okreslic realna wartosc systemu dla praktyki review.

## 10. Material zrodlowy wykorzystany do opracowania

- [README.md](README.md)
- [architektura-systemu.md](architektura-systemu.md)
- [acr_system/domain/entities/entities.py](acr_system/domain/entities/entities.py)
- [acr_system/domain/value_objects/value_objects.py](acr_system/domain/value_objects/value_objects.py)
- [acr_system/domain/services/services.py](acr_system/domain/services/services.py)
- [acr_system/application/use_cases/process_pull_request.py](acr_system/application/use_cases/process_pull_request.py)
- [acr_system/application/use_cases/evaluate_pull_request.py](acr_system/application/use_cases/evaluate_pull_request.py)
- [acr_system/application/use_cases/publish_review.py](acr_system/application/use_cases/publish_review.py)
- [docs/IMPACT_ANALYSIS_TESTS_STATUS.md](docs/IMPACT_ANALYSIS_TESTS_STATUS.md)
- [src/5-5-eval.tex](src/5-5-eval.tex)
- [src/5-4-llm-and-static-cr.tex](src/5-4-llm-and-static-cr.tex)
- [src/5-llm-cr.tex](src/5-llm-cr.tex)
- [src/6-sum.tex](src/6-sum.tex)
