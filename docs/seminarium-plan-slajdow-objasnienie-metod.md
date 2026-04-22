# Plan slajdów — „Objaśnienie zastosowanych metod” (ok. 40% prezentacji)

Założenia:
- Temat pracy: **Narzędzie do automatycznej analizy kodu** (ACR: automatyczne code review + analiza wpływu zmian).
- Cała prezentacja: ~35 min.
- Ta część: ~40% czasu ⇒ **ok. 14 min**.
- Styl slajdów: 3–5 punktów na slajd + krótki „talk track” (co powiedzieć w 1–2 min).
- Bazuje na: `docs/seminarium-objasnienie-metod.md` (metody uziemione w kodzie repo).

---

## Cel tej sekcji (1 zdanie)

Pokazać, **jakimi metodami** (prompting, RAG, CI/statyka, AST, polityki publikacji, ewaluacja) zbudowane jest narzędzie i **dlaczego** ten pipeline jest praktyczny.

---

## Proponowany układ: 9 slajdów / ~14 min

### Slajd M1 (1:10) — „Co znaczy metoda w tej pracy?”
- Metoda = pipeline end-to-end, nie „jeden model”.
- LLM jako generator/translator + mechanizmy uziemienia.
- Cel: komentarze weryfikowalne w danych wejściowych.

Talk track:
- Krótko ustawiasz ramę: to jest narzędzie inżynierskie do analizy kodu w workflow PR.

---

### Slajd M2 (1:20) — „Architektura jako metoda: Clean + Hexagonal”
- Porty/adaptery: VCS, LLM, RAG, CI.
- Use-case orchestration: review / publish / index-history / evaluate.
- Dzięki temu łatwo zrobić ablacje (bez RAG / bez CI).

Talk track:
- Podkreśl, że architektura jest narzędziem kontroli złożoności i testowalności.

---

### Slajd M3 (1:40) — „Pipeline ACR: od PR do komentarzy”
- Wejście: webhook lub CLI.
- Pobranie PR + diff hunki + konfiguracja `.acr-config.yml`.
- Budowa kontekstu (RAG + surrounding code + historia).
- CI issues → normalizacja.
- LLM → JSON komentarze → publikacja.

Talk track:
- Przejście: „Teraz rozbiję pipeline na metody składowe”.

---

### Slajd M4 (1:40) — „Prompting: jak steruję LLM, żeby był ‘review-friendly’”
- Stały szablon promptu: reguły + diff + kontekst + CI.
- Format odpowiedzi: JSON (linia/severity/wiadomość/sugestia).
- Zasada: evidence-based + zakaz spekulacji + hierarchia źródeł.

Talk track:
- Podaj 1–2 przykłady: dlaczego JSON jest kluczowy (inline comments) i czemu ograniczasz ‘może/rozważ’.

---

### Slajd M5 (1:50) — „RAG: skąd biorę wiedzę o repo”
- FAISS + embeddingi (MiniLM) + indeks trwały.
- Źródła: dokumentacja + historia PR (diff i wątki dyskusji).
- Retrieval: top_k + over-fetch + filtr metadanych.
- Skoring: $1/(1+d)$.

Talk track:
- Powiedz, że RAG rozwiązuje „problem kontekstu” w code review i zmniejsza ogólniki.

---

### Slajd M6 (1:20) — „Surrounding code: najtańszy kontekst semantyczny”
- Okno linii wokół hunku (`RAG_SURROUNDING_LINES`).
- Weryfikacja brakujących importów/symboli w realnym pliku.
- Wyższy priorytet niż historia PR.

Talk track:
- Zaznacz, że to celowo proste, ale mocno ogranicza fałszywe uwagi.

---

### Slajd M7 (1:40) — „AST / tree-sitter: struktura zamiast surowego diffu”
- Ekstrakcja funkcji/klas/importów.
- ‘Changed functions’ przez overlap zakresów linii.
- Strategy+Registry dla wielu języków.

Talk track:
- Motywacja: model lepiej ocenia zmianę, gdy widzi funkcję/metodę, nie tylko patch.

---

### Slajd M8 (1:40) — „CI/statyka: precyzyjny sygnał + LLM jako parser”
- Fetch wyników narzędzi CI (różne formaty).
- Normalizacja do `ParsedCIIssue` (plik/linia/severity).
- Filtrowanie do zmienionych linii/hunków.
- Efekt: komentarze ‘audytowalne’ („bo CI mówi X”).

Talk track:
- Podkreśl różnicę: LLM nie wymyśla — „tłumaczy” sygnał narzędziowy na review.

---

### Slajd M9 (1:20) — „Ewaluacja i kontrola szumu (publish policy)”
- Publish policy z configu: minimalna severity / filtry.
- Tryb `evaluate`: metryki tekstowe + koszt (czas/tokeny) + best semantic match.
- Uczciwe ograniczenia: metryki tekstowe ≠ poprawność merytoryczna.

Talk track:
- Domknij klamrą: metody są dobrane pod realny workflow i kontrolę ryzyka.

---

## Bufor i przejścia

- Bufor ~0:40 na pytanie lub doprecyzowanie w środku (np. po M5 RAG).
- Naturalne przejście do kolejnej sekcji prezentacji („Otrzymane wyniki / demo narzędzia”):
  - „Skoro wiemy, jak działa pipeline, pokażę jak wygląda wynik na PR i jakie komentarze publikuje”.

---

## Checklist do przygotowania slajdów (praktyczne)

- Na 1 slajdzie (M3 lub M5) pokaż 1 diagram: pipeline lub RAG.
- Na 1 slajdzie (M4 lub M8) pokaż 1 mini-przykład formatu JSON komentarza.
- Nie wchodź w detale implementacyjne (nazwy klas) na slajdach — zostaw to w narracji.
