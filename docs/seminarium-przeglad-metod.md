# Przegląd metod rozwiązania zadania (seminarium) — ACR: automatyczne code review z LLM + RAG

Poniższe punkty są przygotowane jako „wkład do slajdów” dla podpunktu **Przegląd metod rozwiązania zadania** w prezentacji wyników (rezultaty własne). Materiał bazuje na rozdziale literaturowym (m.in. `2-literatura/*`) oraz założeniach/projekcie systemu ACR (m.in. `gen-general/architektura-systemu.md`, `gen-general/kontekst-pracy.md`).

---

## Slajd: Co dokładnie rozwiązuję? (zadanie + wejścia/wyjścia)

- **Zadanie:** automatyczny (pomocniczy) przegląd kodu w ramach PR/MR.
- **Wejście:** diff + metadane PR/MR (tytuł/opis) + kontekst repo (dokumentacja, standardy, historia review) + sygnały z CI/CD.
- **Wyjście:** ustrukturyzowane komentarze review (inline do plików/linie), z priorytetem/uzasadnieniem i sugestią.
- **Ograniczenia praktyczne:** koszt czasowy, ryzyko regresji (złe sugestie), ograniczony kontekst, wymóg integracji z workflow.

---

## Slajd: „Spektrum” metod automatyzacji code review (od klasyki do SOTA)

### 1) Klasyczny (ludzki) code review — punkt odniesienia
- Zalety: bogate rozumienie kontekstu, odpowiedzialność i ocena „biznesowa”.
- Wady: czas, zmienność jakości, wąskie gardła, problem kontekstu przy dużych repo.

### 2) Narzędzia regułowe i statyczna analiza (SAST, linters, rule engines)
- Co robią dobrze: wysoka precyzja dla znanych klas problemów, niski koszt, świetna automatyzacja w CI.
- Co robią słabo: ograniczona „wyjaśnialność” i dopasowanie do lokalnych standardów; często raporty są mało „review-friendly”.
- Typowa rola w systemie: **pierwsza linia obrony** + źródło sygnału dla kolejnych etapów.

### 3) Klasyczne ML (przed erą LLM)
- Typowe zastosowania: detekcja smells, predykcja naruszeń wytycznych.
- Zalety: uczy się z danych, bywa skuteczne dla problemów „wzorcowych”.
- Wady: potrzeba danych, trudniejsza interpretacja, degradacja przy driftcie projektu, ograniczenia semantyczne.

### 4) LLM jako generator komentarzy (prompt-based / in-context learning)
- Sterowanie: prompt (instrukcja + format odpowiedzi + przykłady few-shot).
- Zalety: szybkie iteracje, brak infrastruktury treningowej, łatwa integracja.
- Wady: **prompt brittleness**, wahania jakości, ryzyko halucynacji i regresji; bardzo wrażliwe na jakość i selekcję kontekstu.

### 5) Fine-tuning (w tym PEFT: LoRA/QLoRA/prefix-tuning)
- Cel: dopasować styl/strukturę komentarzy do domeny code review.
- Zalety: stabilniejsza forma, potencjalnie lepsza „actionability”.
- Wady: koszty danych i procesu uczenia, ryzyko uczenia się „szumu” (niepożądanych komentarzy), utrzymanie modeli.

### 6) Metody hybrydowe: RAG + statyka + struktura kodu (AST) + logika
- Intuicja: LLM jest dobry w **komunikacji i uzasadnieniu**, ale potrzebuje uziemienia w faktach.
- Składniki hybrydy:
  - **RAG**: dostarcza kontekst repo (dokumentacja, standardy, ADRy, wcześniejsze review).
  - **Analiza statyczna/CI**: dostarcza precyzyjny sygnał (warning/error) i ogranicza przestrzeń „fantazji” modelu.
  - **AST / Tree-sitter**: daje kontekst strukturalny (np. „enclosing method”), lepszy niż surowy diff.
  - (opcjonalnie) reguły/elementy symboliczne: spójność, audytowalność.

---

## Slajd: Dlaczego w praktyce wygrywa podejście hybrydowe (LLM + RAG + CI)

- **Największy koszt review to kontekst**: rozumienie intencji zmiany i standardów projektu.
- „LLM-only” generuje komentarze, ale bez kontekstu łatwo o ogólniki i błędy merytoryczne.
- „Static-only” jest precyzyjne, ale słabo tłumaczy i nie umie oceniać „projektowo” (np. architektura, uzasadnienie).
- Hybryda pozwala:
  - utrzymać **weryfikowalność** (komentarz oparty o CI issue / fragment dokumentacji),
  - ograniczyć **ryzyko regresji** przez walidacje (testy/CI) i human-in-the-loop,
  - zwiększyć **użyteczność** (komentarz: co, gdzie, dlaczego, jak poprawić).

---

## Slajd: Metoda docelowa w mojej pracy — pipeline ACR (end-to-end)

To jest syntetyczny opis metody, którą implementuję jako rezultat własny.

1) **Integracja z VCS (GitHub/GitLab)**
- Pobranie PR/MR: diff, lista plików, metadane, historia.
- Publikacja komentarzy jako inline review.

2) **Dobór strategii (konfigurowalność per repo i per typ pliku)**
- Dobór modelu LLM w zależności od języka/ścieżki pliku.
- Dobór RAG (włącz/wyłącz, `top_k`, źródła dokumentów).

3) **Budowa kontekstu (RAG + „twarde” artefakty repo)**
- Query z tytułu/opisu PR/MR.
- Retrieval top-k fragmentów dokumentacji/standardów/ADR.
- Dodatkowo: podobne historyczne review (opcjonalnie: podobne PR).

4) **Kontekst strukturalny z AST (Tree-sitter)**
- Ekstrakcja funkcji/fragmentów „otaczających” zmiany (LLM widzi funkcję, nie tylko diff).
- Ograniczenie ilości, by nie przepełniać promptu (np. top-5 największych zmian).

5) **Integracja z CI/CD i statycznymi analizatorami**
- Fetch wyników (checks, artefakty, logi) i identyfikacja issues.
- (Praktyczny trik) Parsowanie surowych logów narzędzi przez LLM do ujednoliconej postaci issue (plik/linia/severity).
- Dołożenie issues jako „dowodów” w kontekście dla głównego review.

6) **Generowanie komentarzy przez LLM + kontrola jakości**
- Prompt template + format odpowiedzi.
- Ranking po severity; deduplikacja.
- **Human-in-the-loop:** eskalacja, gdy krytycznych uwag jest dużo lub gdy ryzyko jest wysokie.

7) **Obsługa dużych PR (chunking)**
- Dzielenie diffa na chunki; generacja per chunk; agregacja i deduplikacja.

---

## Slajd: Alternatywy i kompromisy (co porównuję / co uzasadniam)

### Prompting vs fine-tuning
- Prompting: szybki start i iteracje; mniejszy koszt; większa wrażliwość.
- Fine-tuning/PEFT: potencjalnie stabilniej i „bardziej po repo”; ale koszt danych i utrzymania.
- Wniosek praktyczny: **na etapie narzędzia inżynierskiego** rozsądne jest zacząć od prompting + hybrydy (RAG/CI), a fine-tuning traktować jako kolejny krok, jeśli pojawi się powtarzalny zestaw błędów/stylów.

### RAG: BM25 vs embeddingi (FAISS)
- BM25: dobre baseline, prostota, czasem konkurencyjne.
- Embeddingi + FAISS: lepsze dopasowanie semantyczne, ale większa złożoność i ryzyko nietrafionego kontekstu.
- Wniosek: potrzebna konfiguracja (`top_k`, deduplikacja, filtrowanie źródeł) i testy regresji jakości.

### Diff-only vs AST-enriched
- Diff-only: mało tokenów, ale słaby kontekst.
- AST (enclosing method / extracted functions): lepsze rozumienie roli zmiany.
- Wniosek: AST jest „tanim” sposobem na semantyczny kontekst bez wrzucania całego repo.

### LLM-only vs LLM + statyka
- LLM-only: ryzyko halucynacji/ogólników.
- LLM + statyka: precyzyjny sygnał + lepsze uzasadnienie i audytowalność.

---

## Slajd: Jak opisuję „metody” w kategoriach eksperymentu (ablacje)

Jeśli chcesz, żeby „Przegląd metod” łączył się płynnie z wynikami, warto nazwać warianty, które później pokażesz w wynikach:

- **Wariant A (baseline):** bez LLM (tylko CI/statyka raportowana klasycznie).
- **Wariant B:** LLM + prompting, bez RAG (diff + instrukcja).
- **Wariant C (docelowy):** LLM + prompting + RAG + CI issues + AST.

Co porównywać:
- czas odpowiedzi i koszt,
- trafność i konkretność (relevance/actionability),
- ryzyko regresji (czy sugestie psują poprawny kod),
- „audytowalność” (czy da się wskazać, skąd wziął się komentarz: doc/CI).

---

## Slajd: ściąga — 1 zdanie na metodę (do szybkiej narracji)

- **Statyczna analiza:** szybka i precyzyjna detekcja znanych problemów, ale słaba komunikacja i kontekst.
- **Klasyczne ML:** uczy się wzorców z danych, lecz jest wrażliwe na drift i ograniczone semantycznie.
- **Prompting (LLM):** szybkie prototypowanie i komentarze w języku naturalnym, ale ryzyko niestabilności.
- **Fine-tuning (PEFT):** stabilniejszy styl i dopasowanie do domeny, kosztem danych i utrzymania.
- **RAG:** uziemienie w repo (standardy/dokumentacja/historia), jeśli retrieval jest selektywny.
- **Hybryda LLM+RAG+CI+AST:** praktyczny kompromis: kontekst + weryfikowalność + integracja w workflow.
