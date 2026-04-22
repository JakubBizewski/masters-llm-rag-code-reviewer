# Objaśnienie zastosowanych metod — seminarium dyplomowe (ACR: LLM + RAG + CI + AST)

Ten plik jest przygotowany jako **wkład do slajdów** dla podpunktu **„Objaśnienie zastosowanych metod”** w prezentacji: **Prezentacja wyników (rezultaty własne)**.

Materiał jest uziemiony w:
- implementacji w `acr_system/` (porty/adaptery, RAG, prompting, AST, CI, ewaluacja),
- opisie architektury w `docs/magisterka/architektura_ogolna_systemu_acr.md` oraz `architektura-systemu.md`,
- rozdziale metodycznym pracy: `src/5-1-prompt-based-cr.tex`, `src/5-3-rag-cr.tex`, `src/5-4-llm-and-static-cr.tex`, `src/5-5-eval.tex`,
- wcześniejszym slajdzie „Przegląd metod” w `docs/seminarium-przeglad-metod.md` (jako kontekst porównawczy).

---

## Slajd: Co znaczy „metoda” w tej pracy (perspektywa inżynierska)

- **Metoda = pipeline end-to-end**, a nie pojedynczy model: od eventu PR/MR → kontekst → generacja → publikacja → (opcjonalnie) ewaluacja.
- LLM pełni rolę **generatora i tłumacza** (komentarz + uzasadnienie), a nie „wyroczni”.
- Minimalizacja ryzyka halucynacji przez:
  - uziemienie w kontekście (RAG + surrounding code + CI),
  - wymuszenie formatu (JSON) i filtrację komentarzy,
  - ograniczenie zakresu: komentarze tylko dla problemów „weryfikowalnych” w danych wejściowych.

Notatki mówcy:
- W literaturze (prompting / RAG / hybrydy) dominuje teza, że **kluczowy jest dobór i dawkowanie kontekstu** oraz **kontrola jakości**, a nie tylko „moc modelu”.

---

## Slajd: Architektura jako metoda (Clean + Hexagonal + Use-case orchestration)

- System zaprojektowany w stylu **Clean Architecture + Ports & Adapters**:
  - domena definiuje porty: `VCSRepository`, `LLMProvider`, `EmbeddingStore`, `StaticAnalyzer`, itd.
  - infrastruktura dostarcza adaptery: GitHub/GitLab, OpenAI/Anthropic, FAISS, CI.
- Orkiestracja w warstwie aplikacji (use case’y): review, publikacja, indeksacja historii, ewaluacja.
- Zysk metodyczny: **testowalność**, wymienność dostawców oraz możliwość ablacji (np. review bez RAG / bez CI).

Referencje w repo:
- `docs/magisterka/architektura_ogolna_systemu_acr.md`
- `architektura-systemu.md`
- „rdzeń” przepływu: `acr_system/domain/services/services.py`

---

## Slajd: Pipeline ACR (end-to-end) — jak działa narzędzie

1) **Wejście**: PR/MR URL lub webhook.
2) **Pobranie danych** z VCS: metadane, zmienione pliki, diff hunki, gałąź/commit.
3) **Ładowanie polityk** z `.acr-config.yml` (reguły review, konfiguracja LLM/RAG, publish policy).
4) **Budowa kontekstu** per hunk: RAG + historia review + surrounding code.
5) **Sygnały CI** (jeśli dostępne): fetch i parsowanie do ujednoliconej listy issue.
6) **Generacja komentarzy** per hunk (LLM) + normalizacja/filtracja.
7) **Publikacja** komentarzy jako inline review + (best-effort) indeksacja historii PR do bazy RAG.

Referencje w repo:
- CLI: `acr_system/presentation/cli/main.py` (komendy `review`, `index-history`, `evaluate`)
- Webhook: `acr_system/presentation/api/webhook_handlers.py`
- Orkiestracja domenowa: `acr_system/domain/services/services.py`

Notatki mówcy:
- Kluczowa decyzja: **review jest wykonywany per hunk**, a nie na „całym PR naraz” → mniejsze prompty i lepsze kotwiczenie do linii.

---

## Slajd: Prompting (in-context learning) jako rdzeń generacji komentarzy

- Zastosowane podejście: **prompt-based / in-context learning** (bez fine-tuningu): model sterowany treścią promptu.
- Prompt ma stałą, powtarzalną strukturę:
  - reguły review,
  - unified diff,
  - top-k kontekstów (ograniczone do 3),
  - issues CI (jeśli są).
- Odpowiedź wymuszona schematem **JSON**: lista komentarzy (linia, severity, message, suggestion).
- Ograniczenie halucynacji:
  - instrukcja „**evidence-based**”,
  - lista **zakazanych fraz spekulatywnych**,
  - jawna **hierarchia źródeł** (surrounding code > diff > CI > historia).

Referencje w repo:
- Implementacja promptu i parsera JSON: `acr_system/infrastructure/llm/openai_adapter.py`
- Uzasadnienie literaturowe prompting: `src/5-1-prompt-based-cr.tex`

Notatki mówcy:
- W rozdziale pracy podkreślam: prompting jest szybki w iteracji, ale „kapryśny”, więc wymaga **szablonów + testów regresji**.

---

## Slajd: RAG (retrieval-augmented generation) — jak dostarczam kontekst projektowy

- Cel RAG: **uzupełnić diff** o wiedzę repozytorium i ograniczyć ogólniki.
- Backend: **FAISS** jako wektorowy indeks ANN + trwałość na dysku.
- Model embeddingowy (domyślnie): `sentence-transformers/all-MiniLM-L6-v2`.
- Trwałe artefakty indeksu: `faiss_index/index.faiss` + `faiss_index/documents.json`.
- Źródła wiedzy w indeksie:
  - dokumentacja/ADRy/architektura (source=`documentation`),
  - historia PR: diff-only (source=`pr_history_diff`),
  - historia PR: wątki dyskusji review (source=`pr_history_comment_thread`).

Retrieval (online) — kluczowe szczegóły:
- Query budowane z: ścieżka pliku + język + **pierwsze dodane linie** w hunku.
- `top_k` sterowane konfiguracją; zastosowany **over-fetch** (`top_k * 5`) → filtracja metadanych → ucięcie do `top_k`.
- Skoring: dystans L2 z FAISS mapowany do $score = 1/(1+d)$.

Referencje w repo:
- Implementacja: `acr_system/infrastructure/rag/faiss_store.py`
- Opis metody i pipeline: `docs/magisterka/projekt_warstwy_rag_repozytorium_wiedzy_embeddingi_pipeline_acr.md`
- Uzasadnienie literaturowe RAG/hybryd: `src/5-3-rag-cr.tex`, `src/5-4-llm-and-static-cr.tex`

---

## Slajd: Indeksacja historii PR jako „pamięć organizacyjna” (bez trenowania modelu)

- Metoda: buduję bazę wiedzy z przeszłych PR/MR:
  - jeśli brak dyskusji → dokument „diff-only”,
  - jeśli jest dyskusja → osobne dokumenty per wątek + odpowiedzi.
- Deduplikacja przez `unique_key` (repo + PR + rodzaj + identyfikator) → brak ponownego indeksowania.
- Ograniczenia kosztu: obcinanie bardzo długich treści przed embeddingiem.

Referencje w repo:
- Use case indeksacji: `acr_system/application/use_cases/index_pr_history.py`
- Implementacja indeksacji: `acr_system/infrastructure/rag/faiss_store.py`

Notatki mówcy:
- To jest pragmatyczna alternatywa dla fine-tuningu: „uczenie przez kontekst” zamiast uczenia wag.

---

## Slajd: Surrounding code — najprostszy, ale krytyczny kontekst semantyczny

- Oprócz RAG pobierany jest **kontekst otaczającego kodu** (fragment pliku wokół hunku).
- Okno kontekstu sterowane env `RAG_SURROUNDING_LINES` (domyślnie 200 linii).
- Cel: umożliwić weryfikację stwierdzeń typu „brakuje importu” / „zmienna nie istnieje” w realnym pliku, a nie tylko w diffie.

Referencje w repo:
- Budowa kontekstu: `acr_system/domain/services/services.py` (ContextBuilder)

---

## Slajd: AST / tree-sitter — kontekst strukturalny zamiast „surowego diffu”

- Zastosowany parser: **tree-sitter** (wielojęzykowy, odporny na błędy, szybki).
- Metoda: ekstrakcja struktur (funkcje/klasy/importy) oraz wybór **funkcji zmienionych** przez overlap z zakresem linii hunku.
- Rozszerzalność: wzorzec **Strategy + Registry** dla języków (Python/JS/TS/Go); dodanie języka bez modyfikacji adaptera.

Referencje w repo:
- Adapter AST: `acr_system/ast/tree_sitter_adapter.py`
- Strategie językowe: `acr_system/ast/strategies/`

Notatki mówcy:
- W pracy podkreślam, że AST jest „tańszym” sposobem na semantyczny kontekst niż wrzucanie całego repo do promptu.

---

## Slajd: Integracja z CI / statyczną analizą — źródło precyzyjnego sygnału

- Metoda hybrydowa: **LLM + statyka**.
- Źródło danych: adaptery CI (GitHub Checks / GitLab CI) pobierają wyniki narzędzi.
- Normalizacja: surowe logi mają różne formaty, więc stosuję krok „**LLM jako parser**” → `ParsedCIIssue` (plik/linia/severity/code/message).
- Selekcja: issues są filtrowane do tych, które dotyczą zmienionego pliku i (jeśli znany) linii w obrębie hunku.

Referencje w repo:
- Fetch CI: `acr_system/infrastructure/ci/github_checks_adapter.py`, `acr_system/infrastructure/ci/gitlab_ci_adapter.py`
- Parsowanie outputu CI: `acr_system/infrastructure/llm/openai_adapter.py` (metoda `parse_ci_output`)
- Uzasadnienie literaturowe hybrydy: `src/5-4-llm-and-static-cr.tex`

---

## Slajd: Kontrola jakości komentarzy (format, kotwiczenie do linii, filtracja)

- Wymuszenie struktury przez JSON → łatwiejsze mapowanie do inline review.
- Mechanizmy „higieny” odpowiedzi:
  - wyciąganie JSON z odpowiedzi tekstowej,
  - mapowanie severity do VO `Severity`,
  - normalizacja numeru linii do zakresu hunku,
  - heurystyka dokotwiczania komentarza do definicji w diffie (gdy model podał złą linię),
  - filtr odrzucający komentarze uznane za spekulatywne.

Referencje w repo:
- Parser i filtry: `acr_system/infrastructure/llm/openai_adapter.py`

---

## Slajd: Publish policy — metoda ograniczania „szumu” w realnym workflow

- Nawet jeśli model wygeneruje dużo uwag, publikacja do PR jest filtrowana przez politykę z `.acr-config.yml`.
- Przykładowe kryteria: minimalna severity, wykluczenia ścieżek, priorytety reguł.

Referencje w repo:
- Filtr przed publikacją: `acr_system/presentation/cli/main.py` (blok `filter_comments_for_publication`)
- Konfiguracja: `acr_system/infrastructure/config/yaml_config_loader.py` + modele config w `acr_system/infrastructure/config/project_config.py`

Notatki mówcy:
- To jest typowo „produktowa” decyzja: narzędzie ma pomagać, a nie zalewać PR komentarzami.

---

## Slajd: Impact analysis (opcjonalnie) — wykrywanie breaking changes

- Metoda (wariant rozszerzony):
  - statyczne szukanie miejsc użycia / call sites (heurystyki + grep + tree-sitter),
  - osobny prompt LLM do oceny ryzyka zmiany (breaking changes) i propozycji fix.
- Uruchamiane tylko, gdy w runtime dostępny jest i analyzer grafu wywołań, i analyzer impactu.

Referencje w repo:
- Call graph: `acr_system/infrastructure/analysis/tree_sitter_call_graph_analyzer.py`
- Impact prompt: `acr_system/infrastructure/analysis/llm_impact_analyzer.py`
- Status testów: `docs/IMPACT_ANALYSIS_TESTS_STATUS.md`

---

## Slajd: Ewaluacja eksperymentalna (offline) — jak mierzę jakość i koszt

- Scenariusz: `evaluate` indeksuje historię (okno czasowe), uruchamia review i zapisuje raport JSON.
- Pomiar kosztu:
  - czas etapów (indexing/review),
  - zużycie tokenów embedding/LLM (best-effort accounting).
- Porównanie do „referencji”: komentarze z dyskusji PR traktowane jako sygnał odniesienia.
- Metryki tekstowe (dla porównań ilościowych): EM, BLEU-4, ROUGE-L, METEOR (uprość.), opcjonalnie BERTScore.
- Dopasowanie generacji do referencji: **best semantic match** po podobieństwie embeddingów (cosine) — próba ograniczenia problemu parafrazy.

Referencje w repo:
- Use case ewaluacji: `acr_system/application/use_cases/evaluate_pull_request.py`
- Metryki: `acr_system/experimental/metrics.py`
- Uzasadnienie i ograniczenia metryk: `src/5-5-eval.tex`

Notatki mówcy:
- Podkreślam w prezentacji: metryki tekstowe są pomocne, ale nie gwarantują poprawności merytorycznej — docelowo liczy się „actionability” i ryzyko regresji.

---

## Slajd: Ograniczenia obecnej metody (uczciwie, ale konstruktywnie)

- Retrieval jest wektorowy (FAISS); brak dodatkowego rerankingu (np. BM25) w głównej ścieżce runtime.
- Dokumenty są indeksowane na poziomie „rekordu” (np. cały wątek dyskusji) + truncation; brak ogólnego chunkera semantycznego.
- Prompty są ograniczane (np. top-3 konteksty, limit znaków kontekstu), więc część wiedzy może nie wejść.
- CI parsing przez LLM jest skuteczny, ale wrażliwy na format logów i koszt.

Notatki mówcy:
- Te ograniczenia są dobrą podstawą do „Planu dalszej pracy” (reranking, lepsze chunking, testy regresji jakości, lepsza walidacja funkcjonalna).

---

## Slajd: Jak to spina się z „Przeglądem metod” (spójna narracja)

- W przeglądzie metod pokazuję spektrum (statyka → LLM → fine-tuning → hybrydy).
- W tym podpunkcie pokazuję, że w mojej implementacji **wygrywa hybryda**:
  - prompting jako trzon,
  - RAG jako kontekst repo,
  - CI/statyka jako precyzyjny sygnał,
  - AST/surrounding code jako kontekst semantyczny.

Referencja:
- `docs/seminarium-przeglad-metod.md`
