# Analiza problemu

## 1. Kontekst problemu

W nowoczesnym wytwarzaniu oprogramowania code review jest jednym z glownych mechanizmow kontroli jakosci, ale jego skutecznosc spada wraz ze wzrostem skali projektu, liczby zmian i zlozonosci domeny. Przeglad literatury oraz analiza obecnego projektu ACR wskazuja, ze glowny problem nie polega na braku narzedzi, lecz na braku spojnego systemu, ktory laczy:

- semantyczna analize zmian,
- kontekst architektoniczny i historyczny repozytorium,
- sygnaly z CI/CD,
- operacyjna integracje z codziennym workflow PR/MR.

W efekcie klasyczny review jest czasochlonny, nierowny jakosciowo i podatny na utrate krytycznego kontekstu.

## 2. Diagnoza stanu obecnego

### 2.1. Ograniczenia klasycznego code review

Na podstawie literatury i praktyki projektowej najwazniejsze ograniczenia to:

- duzy koszt czasowy i obciazenie recenzentow,
- zaleznosc jakosci komentarzy od doswiadczenia konkretnej osoby,
- niska powtarzalnosc i wysoka subiektywnosc informacji zwrotnej,
- trudnosc oceny skutkow ubocznych zmian miedzy plikami i modulami,
- skupienie na detalach lokalnych kosztem ryzyk architektonicznych.

Wniosek: recenzja manualna jest niezbedna, ale sama nie skaluje sie do realiow duzych i szybko zmieniajacych sie repozytoriow.

### 2.2. Ograniczenia automatyzacji przed era LLM

Statyczne analizatory i klasyczne ML dobrze wykrywaja czesc problemow regulowych, ale:

- maja ograniczona zdolnosc rozumienia intencji zmiany,
- slabo radza sobie z bogatym kontekstem projektowym,
- generuja sygnaly trudne komunikacyjnie dla dewelopera,
- nie domykaja procesu od wykrycia problemu do uzytecznej rekomendacji.

Wniosek: podejscia pre-LLM redukuja czesc szumu technicznego, lecz nie rozwiazuja problemu kontekstowej, operacyjnej recenzji.

### 2.3. Ograniczenia podejsc LLM-first

Literatura z obszaru ACR i analiza rozdzialow tex pokazuja, ze samo podlaczenie LLM nie wystarcza:

- wysoka wrazliwosc na konstrukcje promptu,
- ryzyko odpowiedzi ogolnikowych lub nietrafionych,
- mozliwosc regresji (sugestie pogarszajace poprawny kod),
- metryki tekstowe nie odzwierciedlaja w pelni jakosci merytorycznej,
- problemy z jakoscia danych uczacych i ryzykiem leakage.

Wniosek: LLM jest komponentem wysokiego potencjalu, ale wymaga warstwy uziemienia, kontroli i walidacji.

## 3. Problem glowny i problemy szczegolowe

### 3.1. Problem glowny

Jak zaprojektowac system automatycznego wsparcia code review, ktory zwieksza trafnosc i uzytecznosc komentarzy przy zachowaniu bezpieczenstwa procesu integracji kodu, a jednoczesnie pozostaje operacyjnie wdrazalny w workflow PR/MR?

### 3.2. Problemy szczegolowe

1. Jak redukowac ogolnikowosc komentarzy i zwiekszac ich actionability?
2. Jak dostarczac modelowi kontekst adekwatny do zmiany bez przeladowania promptu?
3. Jak laczyc sygnaly LLM i CI/statycznej analizy, aby poprawic weryfikowalnosc uwag?
4. Jak ograniczac niedeterministycznosc i ryzyko regresji?
5. Jak oceniac jakosc ACR metrykami blizszymi realnemu review niz sama zgodnosc leksykalna?
6. Jak utrzymac konfigurowalnosc per repozytorium bez zmian kodu bazowego systemu?

## 4. Luka badawcza

Analiza literatury i istniejacej praktyki wskazuje luke o charakterze systemowym:

- wiele prac optymalizuje pojedynczy komponent (prompting, fine-tuning, retrieval, detekcja),
- mniej prac pokazuje end-to-end pipeline osadzony w realnym PR/MR,
- rzadziej spotykane jest spojne polaczenie: retrieval kontekstu + generacja + walidacja + publikacja + feedback loop,
- nadal ograniczona jest liczba rozwiazan wieloplatformowych (GitHub i GitLab) z gotowa warstwa konfiguracyjna i testowa.

W praktyce oznacza to brak dojrzalych, latwo wdrazalnych rozwiazan, ktore jednoczesnie sa:

- kontekstowe,
- mierzalne,
- operacyjne,
- bezpieczne procesowo.

## 5. Uzasadnienie podejscia przyjetego w projekcie ACR

Projekt ACR odpowiada na zidentyfikowany problem przez podejscie hybrydowe:

- LLM jako warstwa semantyczna generacji komentarzy,
- RAG jako warstwa kontekstowa (dokumentacja, historia PR, surrounding code),
- CI adapters i parser issues jako warstwa sygnalow deterministycznych,
- AST i impact analysis jako warstwa zaleznosci miedzyplikowych,
- publish policy i human-in-the-loop jako warstwa kontroli ryzyka.

To podejscie jest zgodne z wnioskami ze zrodel tex: skuteczne ACR wymaga architektury systemowej, a nie pojedynczej techniki modelowej.

## 6. Granice problemu

### 6.1. Zakres objety analiza

- automatyczne wsparcie review dla PR/MR,
- komentarze inline i ogolne,
- integracja z GitHub i GitLab,
- analiza CI/CD, retrieval kontekstu i impact analysis,
- uruchomienie przez CLI oraz webhook API,
- ewaluacja eksperymentalna komentarzy i kosztow tokenowych.

### 6.2. Zakres poza analiza (na tym etapie)

- pelna automatyzacja decyzji merge bez udzialu czlowieka,
- gwarancja bezblednosci semantycznej odpowiedzi LLM,
- kompletny model threat protection dla wszystkich scenariuszy produkcyjnych,
- globalna standaryzacja metryk ACR niezaleznie od domeny projektu.

## 7. Kryteria sukcesu rozwiazania problemu

Rozwiazanie mozna uznac za trafne, jesli spelnia lacznie nastepujace warunki:

1. Komentarze sa merytorycznie trafne i odnosza sie do konkretnej zmiany.
2. Komentarze sa actionable, czyli zawieraja zrozumiale uzasadnienie i sugestie.
3. System redukuje ogolnikowosc przez kontekst repozytoryjny.
4. Sygnaly z CI i analizy statycznej sa mapowane na review w sposob weryfikowalny.
5. Proces nie eliminuje recenzenta, lecz wspiera decyzje human-in-the-loop.
6. Architektura jest modularna i konfigurowalna per projekt.
7. System dziala operacyjnie w PR/MR workflow (CLI/API, publikacja komentarzy, indeksacja historii).

## 8. Ryzyka i ograniczenia badawczo-implementacyjne

### 8.1. Ryzyka techniczne

- halucynacje LLM i niestabilnosc wynikow,
- zly dobor kontekstu retrieval (szum informacyjny),
- opoznienia i koszty inferencji przy duzych zmianach,
- niespojnosc miedzy sygnalami LLM i narzedzi statycznych.

### 8.2. Ryzyka metodyczne

- niedoskonalosc metryk tekstowych dla oceny review,
- potencjalny szum i stronniczosc danych historycznych,
- trudnosc porownan miedzy pracami przez roznice benchmarkow i protokolow.

### 8.3. Ryzyka wdrozeniowe

- bariery adopcji w zespolach (zaufanie do komentarzy AI),
- wymagania bezpieczenstwa webhook i zarzadzania sekretami,
- zaleznosc od dostepnosci API dostawcow zewnetrznych.

## 9. Wnioski dla dalszych podrozdzialow pracy

Analiza problemu prowadzi do jasnego kierunku dalszej czesci pracy:

- rozdzial architektoniczny powinien uzasadnic wybor podejscia hybrydowego,
- rozdzial implementacyjny powinien pokazac przeplyw end-to-end (PR/MR -> analiza -> komentarze -> publikacja),
- rozdzial ewaluacyjny powinien laczyc metryki automatyczne z ocena funkcjonalna i ryzykiem regresji,
- dyskusja powinna odroznic, co jest juz osiagniete, a co pozostaje otwartym problemem badawczym.

## 10. Syntetyczna teza pod podrozdzial

Problem automatyzacji code review nie polega na samym generowaniu komentarzy, lecz na zbudowaniu wiarygodnego i operacyjnego systemu wspierania decyzji recenzenckich, ktory integruje semantyke zmian, kontekst projektu i sygnaly weryfikacyjne w jednym, kontrolowalnym procesie.
