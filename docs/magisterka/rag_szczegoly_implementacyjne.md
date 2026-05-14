# RAG — szczegóły techniczne i implementacyjne

Celem tego dokumentu jest przedstawienie w sposób ściśle implementacyjny przyjętego w projekcie podejścia Retrieval-Augmented Generation (RAG), uzasadnienie decyzji projektowych oraz szczegółowy opis procesu chunkowania, indeksowania i wyszukiwania. Treść odnosi się do implementacji w repozytorium (zob. [acr_system/infrastructure/rag/faiss_store.py](acr_system/infrastructure/rag/faiss_store.py) i [acr_system/domain/entities/entities.py](acr_system/domain/entities/entities.py)).

## 1. Cel RAG w systemie

- Umożliwić LLM dostęp do kontekstu projektu (fragmenty kodu, historia PR, dokumentacja architektoniczna) bez wysyłania całego repozytorium do modelu.
- Zwiększyć trafność i precyzję wygenerowanych odpowiedzi (recall) dzięki dołączeniu relewantnych fragmentów (chunks) do promptu.
- Zachować rozdział odpowiedzialności: indeksowanie i wyszukiwanie (infrastructure/rag) pozostaje niezależne od warstwy LLM (infrastructure/llm).

Decyzja: zastosowano FAISS do przechowywania wektorów przy jednoczesnym zapisie pełnych metadanych w `documents.json` — odseparowanie indeksu wektorowego od metadanych ułatwia aktualizacje i audyt.

## 2. Główne wymagania niefunkcjonalne wpływające na wybory

- Latency: odpowiedź użytkownika musi mieścić się w budżecie 200–1000 ms na etap retrieval (bez czasu wywołania LLM).
- Skala: indeks może rosnąć do setek tysięcy dokumentów; musi być możliwe przyrostowe indeksowanie (upsert) i częściowa rekonstrukcja.
- Koszt: embeddings są kosztowne; batchowanie i redukcja liczby wezwań są krytyczne.
- Poprawność: poprawne mapowanie chunk → źródło (plik, PR, komentarz) dla odtwarzalności i publikacji referencji.

## 3. Główne decyzje projektowe — podsumowanie i uzasadnienia

- Indeks: FAISS (lokalny plik `index.faiss`) — wybrano ze względu na wydajność i dojrzałość. Alternatywy (Pinecone, Milvus) rozważono, ale FAISS daje pełną kontrolę nad formatem i kosztami przy pracy offline.
- Format przechowywanych dokumentów: `documents.json` z pełnymi metadanymi (filename, repo, pr_number, hunk_id, file_path, start_line, end_line, chunk_hash). Umożliwia spójność i łatwe updaty.
- Model embeddings: domyślnie `sentence-transformers/all-MiniLM-L6-v2` (rozmiar wektora 384) — kompromis pomiędzy kosztami obliczeniowymi a jakością dla tekstu naturalnego. Dla kodu lub krytycznych zapytań rozważane są większe lub specjalizowane modele (code-search, OpenAI code embeddings).
- Chunking: hybrydowe podejście — preferencyjne chunkowanie na poziomie funkcji/metod (Tree-sitter extraction), fallback sliding-window po liniach dla plików bez funkcji.
- Retrieval workflow: embed query → faiss.search(top_k*overfetch) → filter by metadata → rerank (optional) → return top_k. Rerank może wykorzystywać cross-encoder lub lekki scoring via cosine.

Decyzje znajdują uzasadnienie w wymaganiach: funkcja jako unit chunku daje semantyczne spójne fragmenty, redukuje długi context dla LLM, ułatwia mapowanie sugestii do konkretnych miejsc w kodzie.

## 4. Chunking — szczegóły implementacyjne i algorytmy

Główne cele chunkowania:
- maksymalna semantyczna koherencja (nie przecinać funkcji w losowych miejscach),
- ograniczenie rozmiaru chunku do rozsądnego limitu tokenów dla embeddings i promptów,
- możliwość stopniowego łączenia kontekstu (scaffoldowanie: hunk + surrounding function + RAG docs).

### 4.1. Priorytety i warunki brzegowe

- Preferuj ekstrakcję `FunctionNode` (patrz `acr_system/domain/entities/entities.py`) przy pomocy `TreeSitterAdapter`.
- Jeśli plik nie zawiera funkcji (np. README, config), użyj semantycznego chunkowania tekstowego (sentence splitter + sliding window).
- Nie indeksuj binarek ani plików większych niż `MAX_SIZE_BYTES` (domyślnie 1MB) — zamiast tego indeksuj fragmenty kluczowe.
- Filtrowanie sekretów: przed embeddingiem stosuj regex i heurystyki (klucze API, długie Base64) i nie indeksuj wykrytych sekretów.

### 4.2. Parametry chunkowania (zalecane wartości)

- Preferowany chunk: function-level (cała funkcja).
- Fallback chunk: sliding window po liniach lub tokenach.
- Chunk size (tokens): 150–500 tokenów (ok. 800–3000 znaków) — mniejsze dla kodu (150–300), większe dla dokumentacji (300–500).
- Overlap: 10–30% (zwykle 50–150 tokenów) — umożliwia zachowanie kontekstu między sąsiednimi chunkami.
- Maksymalna długość przed truncate: 25_000 znaków (bezpieczna wartość przed fragmentacją i embeddingiem).

Uzasadnienie: krótsze chunk'i dla kodu pozwalają lepiej lokalizować odpowiedzi oraz ograniczają koszt embeddings; overlap redukuje utratę kontekstu na granicach chunków.

### 4.3. Algorytm chunkowania (pseudokod)

1. Jeśli `TreeSitterAdapter` rozpozna funkcje → dla każdej funkcji:
   - jeśli `line_count(function) <= MAX_TOKEN_EQUIV` → utwórz chunk z pełną funkcją,
   - jeśli function zbyt długa → podziel funkcję używając sliding-window po liniach z overlap,
   - nadaj metadane: `chunk_id = sha256(repo + file_path + start_line + end_line)`, `start_line`, `end_line`, `language`, `function_name`.
2. Dla plików bez funkcji:
   - podziel tekst sentence-splitterem,
   - łącz zdania do chunków do limitu tokenów, z overlap,
   - nadaj metadane `section_id` lub `paragraph_index`.
3. Przed wysłaniem do embeddingów: filtrowanie (sekrety), deduplikacja (content hash), batchowanie (batch_size 64–256 w zależności od pamięci i modelu).

Pseudokod (zwięzły):

```python
for file in files_to_index:
    try:
        functions = tree_sitter.extract_functions(file)
        if functions:
            for fn in functions:
                if fn.line_count <= MAX_LINES:
                    chunks.append(make_chunk(fn))
                else:
                    chunks.extend(sliding_window(fn.body, size=CHUNK_TOKENS, overlap=OVERLAP))
        else:
            chunks.extend(text_chunking(file.content, size=CHUNK_TOKENS, overlap=OVERLAP))
    except ParseError:
        chunks.extend(line_based_chunking(file.content))

# dedupe
chunks = dedupe_by_hash(chunks)
# batch embed
for batch in chunk_batches(chunks, BATCH_SIZE):
    embeddings = embed(batch)
    faiss.add(embeddings)
    persist_meta(batch)
```

### 4.4. Hashing i deduplikacja

- `chunk_hash = sha256(normalize_whitespace(content))` — służy wykrywaniu identycznych fragmentów powtarzających się między PR/commitami.
- Jeśli hash istnieje w `documents.json` → update metadanych (dodaj źródło) zamiast ponownie indeksować embedding.

## 5. Metadaty i schema zapisów

Każdy zapisany `document` w `documents.json` powinien zawierać (przykład pól):

- `doc_id` (UUID lub unikalny sha)
- `chunk_id` (sha256 repo+file+start+end)
- `filename` / `file_path`
- `repo`
- `pr_number` (opcjonalnie)
- `hunk_id` (opcjonalnie)
- `function_name` (jeśli dotyczy)
- `start_line`, `end_line`
- `language`
- `content` (tekst chunku, oczyszczony z sekretów)
- `chunk_hash`
- `embedding_model`
- `embedding_dim`
- `created_at`
- `source` ("pr_diff" | "pr_comment" | "documentation" | "architecture")
- `unique_key` (np. "repo:pr:chunk_hash")

Plik `documents.json` to pojedyncze źródło prawdy metadanych; indeks FAISS odnosi się tylko do kolejności wektorów — mapowanie index_id -> doc_id jest przechowywane w `documents.json`.

## 6. Indeks FAISS — wybór typu i tuning

Rozważane opcje:
- `IndexFlatL2` / `IndexFlatIP` — prosty, bezapproxymacji, dobre dla niewielkich zbiorów, wysoki koszt pamięciowy.
- `IndexIVFFlat` — przydatny przy setkach tysięcy punktów (wymaga treningu: `nlist`), szybkie zapytania, konieczny retraining przy istotnych zmianach w danych.
- `IndexHNSWFlat` — dobry wybór dla dynamicznych zbiorów z częstymi upsertami; świetny tradeoff latency/quality.

W projekcie rekomendacja (implementacyjna):
- Dla początkowych rozmiarów (do ~200k) używać HNSW (`IndexHNSWFlat`) lub `IndexIVFFlat` z `nlist` dobranym eksperymentalnie.
- HNSW parametry: `ef_construction=200`, `M=32`, `ef_search` konfigurowalne (np. 64–256) dla leczenia quality vs latency.
- Jeśli używamy cosinusowych podobieństw, normalizujemy wektory i używamy `IndexFlatIP` lub odpowiednio skonfigurowanego HNSW.

Uzasadnienie: HNSW dobrze nadaje się do systemów wymagających online updates (dodawanie/usuwanie wektorów), a IVF zapewnia szybkie wyszukiwanie na bardzo dużych zbiorach przy batchowym trybie.

## 7. Operacje indeksowania: batchowanie, upsert, usuwanie

- Batchowanie: embedy generujemy w batchach (`BATCH_SIZE` domyślnie 64) by amortyzować koszt modelu.
- Upsert: jeżeli `chunk_hash` znany → update metadanych, nie generujemy nowego wektora; jeśli chcesz odświeżyć embedding (nowy model) → oznacz chunk do reembedu.
- Usuwanie: usuwaj z `documents.json` i z indeksu FAISS (jeśli index nie wspiera removal, rebuild partial lub użyj HNSW z flagą usuwania), lub oznacz tombstone i ignoruj przy zapytaniu.
- Rebuild: po znaczących zmianach (zmiana modelu embedding) wykonaj pełne reindexowanie: ekstrakcja → embedding → nowy indeks → atomowe podstawienie pliku `index.faiss`.

## 8. Retrieval: strategia, filtracja i reranking

1. Przyjmij query → wygeneruj embedding query (ten sam model i preprocessing co dokumenty).
2. `faiss.search(k * overfetch)` — overfetch = 3..10 pozwala uwzględnić fałszywe negatywy ANN.
3. Na wynikach zastosuj metadata-filter (np. `repo == requested_repo` lub `source == "pr_history"`).
4. Przelicz similarity (distance -> score) i wykonaj reranking:
   - szybki rerank: normalizacja i sortowanie po cosine score,
   - dokładny rerank: cross-encoder lub LLM re-ranking (droższe) dla top-N (np. N=20).
5. Zwrot do use-case: `top_k_final` fragmentów (zawierających `content`, `metadata`) do dołączenia do promptu.

Dla aplikacji o niskich kosztach rekomendowany tryb: cosine + metadata filtering + lekki rerank.
Dla najwyższej trafności: cross-encoder dla top-20.

## 9. Miary jakości i walidacja

- Recall@k: odtwarzalność oczekiwanych fragmentów w top-k (testy automatyczne z query/ground-truth).
- MRR (Mean Reciprocal Rank) i Precision@k.
- Human-in-the-loop eval: ocena czy zwrócone fragmenty poprawnie uzasadniają komentarz LLM.
- Testy regresyjne: po re-build indeksu porównanie statystyk (recall/precision) z baseline.

W repozytorium warto dodać zestaw testowych zapytań i ground-truth (kontrolowana próbka PR) do klastra testowego.

## 10. Performance engineering i koszty

- Mierzyć: time_to_embed_per_batch, time_to_search, mean_latency_search, memory_footprint_index.
- Przyrostowe indexy: stosować HNSW dla dynamicznych zmian; IVF dla ustabilizowanych, batchowych datasetów.
- Cache wyników retrieval dla identycznych zapytań (TTL krótki), co obniża liczbę wywołań LLM.
- Jeśli używasz zewnętrznego providera embeddings (OpenAI), batchować i korzystać z asynchronicznych limitów (rate limit handling).

## 11. Bezpieczeństwo i prywatność

- Nie indeksować credentials i sekretów (filtr pre-indexing).
- Access control: kto ma dostęp do `faiss_index` i `documents.json` (przechowywać w bezpiecznym storage, ograniczyć ACL).
- Logging: nie logować pełnych contentów chunków przy poziomach logowania produkcyjnych.

## 12. Testy i walidacja integracyjna

- Unit testy dla chunkera: wejścia z funkcjami, duże funkcje, text files, pliki binarne.
- Integration tests: indeksowanie sample repo → query → assert recall@k >= threshold.
- End-to-end: symulowany PR → pipeline (extract → embed → index → retrieve → LLM) z mockami providerów.

## 13. Skalowanie i architektura operacyjna

- Dla małych zespołów: lokalny FAISS + cron reindexing, backup `documents.json`.
- Dla większych: przenieść indeks do dedykowanego serwisu (Milvus/Pinecone) i użyć FAISS do offline rebuilding i eksperymentów.
- Rozdzielenie usług: ekstrakcja/chunking → kolejka (Rabbit/Kafka) → worker embedding → worker indexing.

## 14. Checklista implementacyjna (konkretne pliki / miejsca w kodzie)

- [x] chunking: `TreeSitterAdapter` (ekstrakcja funkcji)
- [x] indeksacja: `acr_system/infrastructure/rag/faiss_store.py`
- [x] metadane: `faiss_index/documents.json`
- [x] retrieval pipeline: `FAISSStore.search_similar()`
- [x] integracja z UseCase: `ProcessPullRequestUseCase` (przekazanie kontekstu do LLM)

---

Plik utworzony: [docs/magisterka/rag_szczegoly_implementacyjne.md](docs/magisterka/rag_szczegoly_implementacyjne.md)

Jeżeli chcesz, mogę teraz:
- dodać automatyczne benchmarki (skrypt `benchmarks/rag_bench.py`) i przykładowe wyniki,
- wygenerować pydantic-validators dla metadanych i przykładowe testy jednostkowe dla chunkera,
- przygotować krótki eksperyment porównawczy (HNSW vs IVF) na subsetcie twojego `faiss_index/documents.json`.
