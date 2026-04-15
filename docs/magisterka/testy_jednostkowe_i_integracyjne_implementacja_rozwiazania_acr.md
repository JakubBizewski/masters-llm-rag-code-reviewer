# Testy jednostkowe i integracyjne

## 1. Cel podrozdzialu

Celem podrozdzialu jest opisanie sposobu projektowania i wykonywania testow jednostkowych oraz integracyjnych w systemie ACR, ze wskazaniem:

- podzialu odpowiedzialnosci miedzy poziomami testow,
- stosowanych narzedzi i konfiguracji,
- praktyk uruchamiania testow lokalnie,
- roli testow w ograniczaniu ryzyka regresji.

Opis opiera sie na rzeczywistej strukturze katalogu `tests`, konfiguracji `pytest` oraz komendach developerskich z `Makefile`.

## 2. Miejsce testow w implementacji ACR

System ACR laczy logike domenowa, integracje z API zewnetrznymi (GitHub/GitLab, LLM) oraz warstwe prezentacji (API/CLI). Z tego powodu strategia testowa zostala podzielona na:

1. testy jednostkowe - dla izolowanej weryfikacji komponentow,
2. testy integracyjne - dla sprawdzenia wspolpracy modulow i przeplywu danych.

Takie rozdzielenie pozwala szybciej diagnozowac bledy: testy jednostkowe lokalizuja problem na poziomie klasy/funkcji, a integracyjne wychwytuja bledy orkiestracji.

## 3. Organizacja testow w repozytorium

W projekcie zastosowano jawny podzial katalogow testowych:

- `tests/unit` - testy jednostkowe,
- `tests/integration` - testy integracyjne,
- `tests/e2e` - przestrzen dla scenariuszy end-to-end (poza glownym zakresem tego podrozdzialu).

Przykladowe testy jednostkowe obejmuja m.in. adaptery i obiekty domenowe (`test_openai_adapter.py`, `test_anthropic_adapter.py`, `test_entities.py`, `test_value_objects.py`) oraz komponenty analityczne (`test_tree_sitter_call_graph_analyzer.py`, `test_llm_impact_analyzer.py`).

Przykladowe testy integracyjne obejmuja pelniejsze przeplywy aplikacyjne (`test_full_pr_review_flow.py`, `test_rag_retrieval_flow.py`, `test_pr_review_with_ci.py`, `test_external_api_integration.py`).

## 4. Narzedzia i konfiguracja testowania

## 4.1. Framework i biblioteki

Konfiguracja developerska projektu (`.[dev]`) obejmuje:

- `pytest` - glowny framework testowy,
- `pytest-asyncio` - testowanie kodu asynchronicznego,
- `pytest-cov` - analiza pokrycia kodu,
- `pytest-mock` - wygodne mockowanie zaleznosci.

## 4.2. Konfiguracja pytest

W `pyproject.toml` zdefiniowano m.in.:

- `testpaths = ["tests"]`,
- wzorce wykrywania testow (`test_*.py`, `Test*`, `test_*`),
- tryb asynchroniczny `asyncio_mode = "auto"`,
- raportowanie pokrycia: terminal (`term-missing`), HTML oraz XML.

To zapewnia jednorodne uruchamianie testow i wspolny standard raportowania.

## 5. Testy jednostkowe

## 5.1. Zakres odpowiedzialnosci

Testy jednostkowe koncentruja sie na pojedynczych komponentach i ich kontraktach. Obejmuja w szczegolnosci:

- logike domenowa (encje, value objects),
- zachowanie pojedynczych adapterow infrastrukturalnych,
- mechanizmy mapowania i walidacji danych,
- funkcje pomocnicze i reguly klasyfikacji.

## 5.2. Izolacja zaleznosci

W testach jednostkowych zewnetrzne systemy (API VCS, LLM, operacje I/O) sa izolowane przez mocki/stuby. Pozwala to:

- utrzymac deterministycznosc wynikow,
- skrocic czas wykonywania testow,
- testowac scenariusze bledne trudne do odtworzenia na realnych integracjach.

## 5.3. Korzysci praktyczne

Testy jednostkowe stanowia pierwsza linie obrony przed regresja i sa uruchamiane jako najtanszy kosztowo etap walidacji zmian.

## 6. Testy integracyjne

## 6.1. Zakres odpowiedzialnosci

Testy integracyjne weryfikuja wspolprace modulow i przeplywy danych miedzy warstwami systemu. Koncentruja sie na scenariuszach takich jak:

- pelny przeplyw review dla PR,
- integracja review z danymi CI,
- przeplyw retrieval w warstwie RAG,
- wspolpraca orkiestracji aplikacyjnej z adapterami.

## 6.2. Charakter integracji

W zaleznosci od scenariusza testy integracyjne lacza komponenty wewnetrzne z kontrolowanym mockowaniem uslug zewnetrznych. Taki kompromis umozliwia:

- sprawdzanie faktycznej wspolpracy warstw,
- utrzymanie sensownego czasu wykonania,
- odtwarzalnosc wynikow bez pelnej zaleznosci od zewnetrznych API.

## 6.3. Przyklad rozbudowanego obszaru testowego

Dla obszaru Impact Analysis utrzymywana jest osobna dokumentacja statusu testow (`docs/IMPACT_ANALYSIS_TESTS_STATUS.md`), pokazujaca praktyke laczenia testow jednostkowych i integracyjnych oraz iteracyjnego usuwania bledow implementacyjnych.

## 7. Uruchamianie testow w workflow developerskim

W praktyce projekt wykorzystuje dwie warstwy uruchamiania testow:

1. bezposrednie komendy `pytest` (wszystkie testy lub wybrane katalogi),
2. cele `Makefile`, ktore standaryzuja wywolania.

Kluczowe cele Makefile:

- `make test` - pelny zestaw testow,
- `make test-unit` - tylko testy jednostkowe,
- `make test-integration` - tylko testy integracyjne,
- `make test-cov` - testy z raportem pokrycia,
- `make ci` - polaczenie quality gates i testow.

Takie podejscie upraszcza codzienny workflow i ogranicza ryzyko bledow proceduralnych.

## 8. Rola pokrycia kodu i raportowania

Raporty coverage (terminal/HTML/XML) pelnia role metryki pomocniczej:

- ulatwiaja identyfikacje nieprzetestowanych obszarow,
- wspieraja planowanie priorytetow testowych,
- dostarczaja artefaktow do analizy postepu jakosci.

Pokrycie nie jest traktowane jako cel sam w sobie, lecz jako wskaznik wspierajacy ocene ryzyka regresji.

## 8.1. Metryki ilosciowe (stan biezacy)

Na podstawie standardowych uruchomien testow w lokalnym srodowisku `venv` uzyskano nastepujace wartosci:

1. liczba testow jednostkowych: 151 (wynik `pytest tests/unit -q`),
2. liczba testow integracyjnych: 27 (wynik `pytest tests/integration -q`),
3. liczba testow w pelnym przebiegu: 198 passed, 4 skipped (wynik `pytest --cov=acr_system --cov-report=term-missing --cov-report=xml -q`; przebieg obejmuje rowniez testy spoza `tests/unit` i `tests/integration`, np. dodatkowe katalogi testowe),
4. liczba asercji w kodzie testow: 519 (zliczenie wystapien `assert`),
5. liczba asercji mockowych (`assert_called`, `assert_called_once`, `assert_awaited`, `assert_any_call`): 10,
6. globalne pokrycie kodu (pelny przebieg): 55%,
7. pokrycie linii: 2050 linii pokrytych z 3758 linii kwalifikowanych.

Wynik 55% pokrycia nalezy interpretowac jako poziom umiarkowany: kluczowe scenariusze review i integracji sa testowane, jednak istnieja obszary wymagajace dalszej rozbudowy testow (w szczegolnosci komponenty o pokryciu bliskim 0%).

## 9. Ograniczenia i ryzyka strategii testowej

1. Integracje z uslugami zewnetrznymi (LLM, VCS) sa wrazliwe na zmiennosc odpowiedzi API i limity uslug.
2. Nadmierne mockowanie moze ukrywac czesc problemow wystepujacych dopiero na realnych integracjach.
3. Utrzymanie wysokiej jakosci testow integracyjnych wymaga regularnej aktualizacji fixture i scenariuszy danych.

## 10. Wniosek pod podrozdzial

Strategia testowania w ACR opiera sie na komplementarnym wykorzystaniu testow jednostkowych i integracyjnych. Testy jednostkowe dostarczaja szybkiej, izolowanej walidacji komponentow, a testy integracyjne potwierdzaja poprawna wspolprace warstw i glowne przeplywy review. W polaczeniu z raportowaniem coverage i standaryzacja uruchamiania przez Makefile podejscie to wspiera stabilna implementacje oraz ogranicza ryzyko regresji funkcjonalnej.

## 11. Material zrodlowy wykorzystany do opracowania

- [pyproject.toml](pyproject.toml)
- [Makefile](Makefile)
- [README.md](README.md)
- [tests/unit](tests/unit)
- [tests/integration](tests/integration)
- [docs/IMPACT_ANALYSIS_TESTS_STATUS.md](docs/IMPACT_ANALYSIS_TESTS_STATUS.md)
