# Analiza problemu i wymagan systemu ACR

## 1. Problem badawczy i kontekst

Nowoczesne zespoly wytworcze opieraja proces code review na recenzjach eksperckich, ale przy rosnacej liczbie zmian i presji czasowej pojawiaja sie powtarzalne problemy:

- niestabilna jakosc recenzji miedzy zespolami,
- ograniczona skala recenzji manualnej,
- slaba wykrywalnosc skutkow ubocznych zmian miedzy plikami,
- niska ponowna wykorzystywalnosc wiedzy z historycznych PR/MR,
- trudnosc laczenia wynikow CI/CD i reguly domenowych w jednej, spojnej recenzji.

System ACR (Automated Code Review) adresuje powyzszy problem przez polaczenie LLM, RAG, analizy AST oraz integracji z platformami VCS (GitHub/GitLab).

## 2. Cel systemu

Celem systemu jest automatyczne generowanie komentarzy code review dla PR/MR w sposob:

- kontekstowy (na podstawie dokumentacji i historii zmian),
- wielozrodlowy (LLM + CI/CD + analiza zaleznosci),
- konfigurowalny na poziomie projektu,
- mozliwy do uruchomienia jako CLI i jako usluga webhookowa.

## 3. Zakres analizy wymagan

Analiza obejmuje:

- wymagania funkcjonalne (co system ma robic),
- wymagania niefunkcjonalne (jakosciowe i ograniczenia),
- kryteria akceptacyjne,
- priorytety wdrozeniowe (MVP vs dalszy rozwoj),
- zgodnosc z aktualnym stanem implementacji.

## 4. Interesariusze

- Deweloper: oczekuje szybkich i trafnych komentarzy do zmian.
- Reviewer techniczny: oczekuje redukcji szumu i wsparcia decyzji.
- Tech Lead/Architekt: oczekuje spojnosc z zasadami architektury i polityka jakosci.
- DevOps/Platform Team: oczekuje bezpiecznej i stabilnej integracji z VCS/CI.
- Badacz/autor pracy: oczekuje mierzalnych metryk jakosci i kosztu.

## 5. Wymagania funkcjonalne systemu

Ponizej przedstawiono wymagania funkcjonalne w postaci identyfikatorow FR (Functional Requirement).

### FR-01. Pobranie i normalizacja danych PR/MR

System musi pobrac metadane PR/MR, diff hunki i liste zmienionych plikow z systemu VCS.

Kryteria akceptacji:

- dla podanego PR/MR system tworzy reprezentacje obiektu PullRequest,
- system wyodrebnia hunki i mapuje je do plikow,
- obsluguje co najmniej GitHub oraz GitLab.

Priorytet: Must
Stan: Zrealizowane (GitHub, GitLab adaptery)

### FR-02. Ladowanie konfiguracji recenzji z repozytorium

System musi pobrac i sparsowac plik .acr-config.yml z gałęzi docelowej oraz zastosowac wartosci domyslne, gdy plik nie istnieje.

Kryteria akceptacji:

- system laduje konfiguracje globalna i per-pattern,
- system waliduje i mapuje ustawienia LLM, RAG, impact analysis i polityki publikacji,
- brak pliku konfiguracyjnego nie blokuje przetwarzania.

Priorytet: Must
Stan: Zrealizowane

### FR-03. Dopasowanie regul recenzji per plik

System musi laczyc reguly globalne i reguly file pattern, z uwzglednieniem priorytetow patternow.

Kryteria akceptacji:

- reguly sa skladane do finalnego rules_text,
- najwyzszy priorytet patternu moze nadpisac LLM/RAG config,
- wynik jest deterministyczny dla tej samej konfiguracji.

Priorytet: Must
Stan: Zrealizowane

### FR-04. Generowanie komentarzy LLM dla diff hunk

System musi wygenerowac komentarze review na podstawie diff, regul, kontekstu i issue z CI.

Kryteria akceptacji:

- dla kazdego hunka tworzona jest lista komentarzy ReviewComment,
- komentarze zawieraja co najmniej: plik, linie (lub ogolny poziom), severity, tresc,
- obsluga wielu providerow LLM (OpenAI, Anthropic).

Priorytet: Must
Stan: Zrealizowane

### FR-05. Budowanie kontekstu RAG

System musi rozszerzac kontekst recenzji przez wyszukiwanie semantyczne w dokumentacji oraz historii PR.

Kryteria akceptacji:

- system wykonuje retrieval dla zapytania zbudowanego z diff hunka,
- wspiera top_k i filtrowanie po zrodle,
- dolacza kontekst otaczajacego kodu z biezacej galezi.

Priorytet: Must
Stan: Zrealizowane

### FR-06. Integracja wynikow CI/CD

System musi pobrac wyniki CI i przefiltrowac je do problemow istotnych dla zmienionych plikow/linii.

Kryteria akceptacji:

- adapter CI pobiera check-runs/jobs,
- LLM parsuje raw output do ParsedCIIssue,
- issue sa dolaczane do recenzji odpowiednich hunkow.

Priorytet: Should
Stan: Zrealizowane (GitHub Checks), Zrealizowane bazowo (GitLab CI)

### FR-07. Wykrywanie potencjalnych breaking changes (Impact Analysis)

System powinien wykrywac skutki uboczne zmian przez analize callerow/importerow i semantyczna ocene LLM.

Kryteria akceptacji:

- system identyfikuje zmienione funkcje z AST,
- wyszukuje bezposrednich callerow (depth = 1),
- generuje komentarz ostrzegawczy dla zmian o istotnej wadze.

Priorytet: Should
Stan: Zrealizowane (wg testow 42/42)

### FR-08. Publikacja komentarzy do PR/MR

System musi umiec opublikowac komentarze z uwzglednieniem polityki publikacji.

Kryteria akceptacji:

- publikacja pojedyncza i zbiorcza,
- filtrowanie po min_severity, rule_name, patternach wiadomosci,
- mozliwosc pomijania komentarzy pozytywnych.

Priorytet: Must
Stan: Zrealizowane

### FR-09. Uruchamianie przez CLI

System musi udostepniac komendy CLI co najmniej: review, index-history, evaluate.

Kryteria akceptacji:

- poprawne parsowanie URL PR/MR i wybor providera,
- raportowanie podsumowania wynikow,
- obsluga trybu publikacji komentarzy.

Priorytet: Must
Stan: Zrealizowane

### FR-10. Uruchamianie przez API/webhook

System musi obslugiwac webhooki i uruchamiac review asynchronicznie.

Kryteria akceptacji:

- endpoint przyjmuje zdarzenia PR/MR,
- review uruchamiany jest jako background task,
- endpoint healthcheck raportuje gotowosc uslugi.

Priorytet: Must
Stan: Zrealizowane (GitHub), Czesciowe (GitLab webhook trigger)

### FR-11. Indeksacja historii PR do RAG

System powinien indeksowac historyczne zmiany i dyskusje PR/MR do bazy wektorowej.

Kryteria akceptacji:

- system pobiera liste zmergowanych PR/MR,
- indeksuje diff + discussion comments,
- wspiera ograniczenie liczby analizowanych PR.

Priorytet: Should
Stan: Zrealizowane

### FR-12. Ewaluacja eksperymentalna jakosci recenzji

System powinien umozliwiac eksperymentalna ewaluacje jakości (np. BLEU/ROUGE/METEOR/BERTScore, koszty tokenowe).

Kryteria akceptacji:

- uruchomienie scenariusza evaluate dla wskazanego PR,
- wyliczenie metryk porownawczych do komentarzy referencyjnych,
- zapis raportu JSON.

Priorytet: Could
Stan: Zrealizowane (modul eksperymentalny)

## 6. Wymagania niefunkcjonalne systemu

Wymagania niefunkcjonalne przedstawiono jako NFR (Non-Functional Requirement) wraz z miernikami i docelowym poziomem.

### NFR-01. Modułowosc i separacja odpowiedzialnosci

System musi byc oparty o czysta architekture i porty/adaptery, aby minimalizowac sprzezenie z dostawcami zewnetrznymi.

Miary:

- warstwy Domain/Application/Infrastructure/Presentation sa rozdzielone,
- zaleznosci kierowane do interfejsow domenowych,
- mozliwa wymiana adaptera bez zmian logiki domeny.

Poziom docelowy: Wysoki
Stan: Osiagniety

### NFR-02. Testowalnosc

System musi umozliwiac testy jednostkowe i integracyjne dla kluczowych scenariuszy.

Miary:

- testy unit + integration dla krytycznych modulow,
- CI-impact analysis: 42/42 testow passing,
- mozliwosc mockowania portow i adapterow.

Poziom docelowy: Wysoki
Stan: Wysoki, z miejscem na dalsze E2E i coverage globalny

### NFR-03. Wydajnosc i skalowalnosc operacyjna

System powinien obslugiwac review wieloplikowych PR poprzez przetwarzanie rownolegle i kontrolowana wspolbieznosc.

Miary:

- rownolegle review plikow i hunkow (asyncio.gather),
- ograniczenie wspolbieznosci dla index-history (semafor),
- ograniczanie danych (top_k, limity historii, truncation logow CI).

Poziom docelowy: Sredni-Wysoki
Stan: Osiagniety bazowo

### NFR-04. Niezawodnosc i odpornosc na bledy

System musi degradawac lagodnie przy bledach zewnetrznych (API, brak configu, brak kontekstu).

Miary:

- fallback do domyslnej konfiguracji,
- obsluga wyjatkow infrastrukturalnych,
- kontynuacja przetwarzania pomimo bledu czesci zadan (gather return_exceptions).

Poziom docelowy: Wysoki
Stan: Osiagniety bazowo

### NFR-05. Obserwowalnosc

System musi zapewniac logowanie zdarzen operacyjnych i diagnostycznych.

Miary:

- centralna konfiguracja loggingu,
- spojny format logow z timestamp, poziomem i nazwa modułu,
- brak duplikacji logow (propagate=False).

Poziom docelowy: Sredni
Stan: Osiagniety

### NFR-06. Bezpieczenstwo integracji

System powinien chronic dane uwierzytelniajace i endpointy webhook.

Miary:

- autoryzacja przez GitHub App / token GitLab,
- sekrety dostarczane przez zmienne srodowiskowe,
- (do domkniecia) walidacja podpisu webhook i rate limiting.

Poziom docelowy: Wysoki
Stan: Czesciowo osiagniety

### NFR-07. Konfigurowalnosc

System musi wspierac adaptacje do repozytorium bez modyfikacji kodu zrodlowego.

Miary:

- konfiguracja YAML obejmuje reguly, LLM, RAG, impact analysis i publish policy,
- wsparcie override per-file pattern,
- sensowne wartosci domyslne.

Poziom docelowy: Wysoki
Stan: Osiagniety

### NFR-08. Przenaszalnosc i wdrazalnosc

System powinien byc latwy do uruchomienia lokalnie i na serwerze CI/CD.

Miary:

- Python 3.11+, packaging przez pyproject,
- API FastAPI i CLI jako alternatywne interfejsy,
- mozliwosc deploymentu jako usluga webhookowa.

Poziom docelowy: Sredni-Wysoki
Stan: Osiagniety

### NFR-09. Jakosc komentarzy AI

System powinien utrzymywac wysoka użytecznosc komentarzy, ograniczajac halucynacje i szum.

Miary:

- uzasadnienie komentarzy przez kontekst (RAG + surrounding code + CI),
- filtrowanie publikacji po severity/pattern,
- eksperymentalna ewaluacja metryczna wobec komentarzy referencyjnych.

Poziom docelowy: Wysoki
Stan: Osiagniety bazowo (zalezne od danych i modelu)

## 7. Ograniczenia i zalozenia

- System nie gwarantuje pelnej poprawnosci semantycznej komentarzy LLM.
- Skutecznosc review zalezy od jakosci konfiguracji i dokumentacji projektowej.
- Integracje z API VCS/LLM podlegaja limitom i dostepnosci dostawcow.
- Czesci funkcji GitLab (np. pełny inline review w webhook flow) sa w trakcie domykania.

## 8. Priorytety wdrozeniowe (MoSCoW)

Must:

- FR-01, FR-02, FR-03, FR-04, FR-05, FR-08, FR-09, FR-10

Should:

- FR-06, FR-07, FR-11

Could:

- FR-12

Wont (na obecnym etapie MVP):

- Zaawansowane E2E produkcyjne dla wielu organizacji i pelne policy enforcement wielodzierzawcze.

## 9. Kryteria gotowosci podrozdzialu pracy

Material z tego dokumentu moze stanowic bezposrednie zrodlo do sekcji "Wymagania funkcjonalne i niefunkcjonalne systemu", poniewaz:

- formalizuje wymagania przez identyfikatory FR/NFR,
- rozdziela stan aktualny i docelowy,
- wiąże wymagania z miernikami i kryteriami akceptacji,
- jest zgodny z architektura Clean/Hexagonal i biezaca implementacja.

## 10. Proponowana struktura podrozdzialu w pracy magisterskiej

1. Wprowadzenie do problemu i motywacji automatyzacji code review.
2. Zakres systemu i aktorzy.
3. Wymagania funkcjonalne (FR-01...FR-12).
4. Wymagania niefunkcjonalne (NFR-01...NFR-09).
5. Ograniczenia i ryzyka.
6. Podsumowanie i przejscie do rozdzialu o architekturze/implementacji.
