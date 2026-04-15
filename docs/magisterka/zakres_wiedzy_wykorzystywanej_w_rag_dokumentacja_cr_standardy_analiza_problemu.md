# Zakres wiedzy wykorzystywanej w RAG (dokumentacja, CR, standardy)

## 1. Cel analizy

Celem tej analizy jest zdefiniowanie, jaka wiedza powinna zasilac warstwe RAG w kontekscie automatycznego code review oraz jakie ograniczenia jakosciowe tej wiedzy determinuja skutecznosc calego procesu.

Sekcja dotyczy poziomu analizy problemu, a nie projektu implementacyjnego.

## 2. Problem podstawowy

W literaturze i praktyce ACR powtarza sie ten sam mechanizm bledu: model oceniajacy zmiane na podstawie samego diffu ma zbyt maly kontekst, przez co zwieksza sie ryzyko:

- komentarzy ogolnikowych,
- nietrafnych sugestii,
- falszywych alarmow,
- pominiecia ograniczen architektonicznych i standardow projektu.

Dlatego RAG nalezy traktowac jako mechanizm dostarczania wiedzy operacyjnej i domenowej, a nie jedynie technike poprawy metryk tekstowych.

## 3. Dlaczego zakres wiedzy w RAG jest kluczowy

W analizowanym problemie najwazniejsze pytanie nie brzmi "czy uzywac RAG", lecz "jaka wiedze i z jaka jakoscia dostarczac do RAG".

Blad doboru zakresu wiedzy prowadzi do dwoch skrajnosci:

1. Zbyt waski zakres:
   model nie ma podstaw do oceny semantycznej i architektonicznej.
2. Zbyt szeroki lub zaszumiony zakres:
   model otrzymuje nieadekwatny kontekst i produkuje komentarze slabo uzyteczne.

Wniosek: kluczowe jest nie tylko zrodlo wiedzy, ale takze jej selekcja, reprezentacja, swiezosc i wiarygodnosc.

## 4. Trzy klasy wiedzy w RAG

## 4.1. Wiedza dokumentacyjna

Definicja:

Wiedza pochodzaca z artefaktow opisujacych system i decyzje projektowe.

Zakres semantyczny:

- architektura systemu,
- ADR i dokumenty techniczne,
- dokumentacja modulow i interfejsow,
- README i opis polityk jakosci.

Rola w analizie problemu:

- uziemienie komentarza w intencji architektonicznej,
- ograniczenie sugestii sprzecznych z zalozeniami systemu,
- wsparcie oceny zmian przekrojowych (cross-file, cross-module).

Ryzyka:

- nieaktualnosc dokumentacji,
- nadmierna ogolnosc opisow,
- niespojnosc miedzy dokumentacja formalna i kodem.

## 4.2. Wiedza z CR (Code Review history)

Definicja:

Wiedza pochodzaca z historycznych PR/MR i dyskusji recenzenckich.

Zakres semantyczny:

- komentarze recenzenckie (watki, odpowiedzi),
- uzasadnienia wczesniejszych decyzji,
- powtarzalne bledy i wzorce napraw,
- kontekst kompromisow technicznych.

Rola w analizie problemu:

- przeniesienie lokalnych norm zespolu do procesu analizy,
- redukcja ogolnikowosci przez analogie do rzeczywistych przypadkow,
- zwiekszenie actionability komentarzy (jak naprawiano podobny problem wczesniej).

Ryzyka:

- dziedziczenie blednych praktyk historycznych,
- wysoki poziom szumu w komentarzach niskiej jakosci,
- trudnosc odroznienia wiedzy trwalej od komentarzy incydentalnych.

## 4.3. Wiedza normatywna (standardy)

Definicja:

Wiedza opisujaca oczekiwane reguly jakosci i stylu dla danego repozytorium.

Zakres semantyczny:

- reguly globalne i per typ pliku,
- polityki bezpieczenstwa i jakosci,
- standardy formatowania, nazewnictwa i testowalnosci,
- reguly publikacji i priorytetyzacji uwag.

Rola w analizie problemu:

- zapewnienie spojnych kryteriow oceny zmian,
- redukcja subiektywnosci komentarzy,
- rozdzielenie "preferencji" od "wymagan".

Ryzyka:

- nadmierna sztywnosc regul,
- rozjazd miedzy regulami formalnymi a praktyka zespolu,
- konflikt standardow miedzy modulami lub jezykami.

## 5. Relacje miedzy klasami wiedzy

Klasy wiedzy nie sa niezalezne; tworza uklad komplementarny:

- dokumentacja odpowiada na pytanie "dlaczego" system jest taki,
- historia CR odpowiada na pytanie "jak" zespol rozwiazywal podobne problemy,
- standardy odpowiadaja na pytanie "wedlug jakich kryteriow" oceniac zmiane.

Brak jednej klasy oslabia jakosc RAG:

- bez dokumentacji rosnie ryzyko bledow architektonicznych,
- bez historii CR rosnie ogolnikowosc i niski poziom praktycznej uzytecznosci,
- bez standardow rosnie niespojnosc i arbitralnosc komentarzy.

## 6. Wymagania jakosciowe dla wiedzy RAG

Dla kazdej klasy wiedzy nalezy analizowac co najmniej piec wymiarow jakosci:

1. Trafnosc:
   czy fragment wiedzy jest powiazany z konkretna zmiana?
2. Swiezosc:
   czy wiedza odzwierciedla aktualny stan systemu i praktyk?
3. Wiarygodnosc:
   czy zrodlo jest autorytatywne dla podejmowanej decyzji?
4. Granularnosc:
   czy poziom szczegolu jest adekwatny do zadania review?
5. Spojnosc:
   czy fragment nie stoi w konflikcie z innymi zrodlami kontekstu?

## 7. Hierarchia zaufania do wiedzy

W analizie problemu uzasadnione jest przyjecie hierarchii zaufania do zrodel:

1. Standardy i reguly formalne (wymagania normatywne).
2. Aktualna dokumentacja architektoniczna i techniczna.
3. Kontekst lokalny kodu i zmiany.
4. Historia CR (najbardziej wartosciowa, ale tez najbardziej zaszumiona).

Interpretacja:

- historia CR daje cenna praktyke, ale nie powinna nadpisywac formalnych regul,
- dokumentacja i standardy pelnia role ram decyzyjnych,
- sygnaly historyczne powinny byc uzywane selektywnie.

## 8. Glowne problemy badawcze zwiazane z zakresem wiedzy RAG

1. Problem selekcji:
   jak dobrac fragmenty wiedzy, aby zwiekszyc trafnosc bez przeladowania kontekstu?
2. Problem konfliktu zrodel:
   jak postepowac, gdy historia CR jest sprzeczna z dokumentacja lub standardem?
3. Problem szumu:
   jak odfiltrowac komentarze i artefakty o niskiej wartosci merytorycznej?
4. Problem temporalny:
   jak uwzgledniac zmiane standardow i starzenie sie wiedzy?
5. Problem transferu:
   jak uniknac mechanicznego przenoszenia dawnych decyzji do nowego kontekstu?

## 9. Hipotezy analityczne pod dalsza czesc pracy

1. Poszerzenie RAG o trzy klasy wiedzy (dokumentacja + CR + standardy) zwieksza merytoryczna uzytecznosc komentarzy wzgledem podejscia opartego tylko na diff.
2. Najwiekszy wzrost jakosci pochodzi z wlasciwej selekcji i rangowania wiedzy, nie z samego zwiekszenia liczby fragmentow.
3. Wiedza historyczna z CR poprawia actionability, ale bez filtracji jakosciowej zwieksza ryzyko szumu.
4. Wiedza normatywna (standardy) jest kluczowa dla redukcji niespojnosci i arbitralnosci komentarzy.

## 10. Ograniczenia analizy

- Nie zaklada sie pelnej automatycznej oceny wiarygodnosci wszystkich zrodel.
- Nie zaklada sie, ze kazda dokumentacja jest aktualna i kompletna.
- Nie zaklada sie pelnej obiektywnosci historycznych komentarzy recenzenckich.
- Nie zaklada sie uniwersalnych progow jakosci kontekstu dla wszystkich projektow.

## 11. Wniosek pod podrozdzial

W problemie automatycznego code review zakres wiedzy wykorzystywanej przez RAG nalezy definiowac jako kontrolowany, wielowarstwowy zasob obejmujacy dokumentacje, historie CR i standardy jakosci, gdzie kluczowe znaczenie ma nie ilosc kontekstu, lecz jego trafnosc, wiarygodnosc i zgodnosc z aktualnymi regulami projektu.

## 12. Material zrodlowy wykorzystany do opracowania

- [README.md](README.md)
- [architektura-systemu.md](architektura-systemu.md)
- [acr_system/domain/services/services.py](acr_system/domain/services/services.py)
- [acr_system/domain/interfaces/ports.py](acr_system/domain/interfaces/ports.py)
- [acr_system/application/use_cases/index_pr_history.py](acr_system/application/use_cases/index_pr_history.py)
- [acr_system/infrastructure/rag/faiss_store.py](acr_system/infrastructure/rag/faiss_store.py)
- [acr_system/infrastructure/config/project_config.py](acr_system/infrastructure/config/project_config.py)
- [acr_system/infrastructure/config/yaml_config_loader.py](acr_system/infrastructure/config/yaml_config_loader.py)
- [src/5-3-rag-cr.tex](src/5-3-rag-cr.tex)
- [src/5-4-llm-and-static-cr.tex](src/5-4-llm-and-static-cr.tex)
- [src/5-5-eval.tex](src/5-5-eval.tex)
- [src/5-llm-cr.tex](src/5-llm-cr.tex)
- [src/6-sum.tex](src/6-sum.tex)
