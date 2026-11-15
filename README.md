[![CI](https://github.com/ileanabeuka/csv-processor/actions/workflows/ci.yml/badge.svg)](https://github.com/ileanabeuka/csv-processor/actions/workflows/ci.yml)

# Procesor CSV

**Versiune:** 0.1.0

Proiect individual la disciplina Metode avansate de programare, anul universitar 2026-2027.

## Autor

- **Nume:** Beuka Ileana
- **Grupa:** 1.1
- **Tema:** Tema 8 – Procesor CSV

## Descriere

Aplicația este un serviciu web care primește tabele în format CSV simplu, cu antet pe primul rând și câmpuri separate prin virgule. Aplicația păstrează tabelele în memoria procesului și permite interogarea lor cât timp rulează; datele se pierd la repornire. Serviciul deduce automat dacă o coloană conține numere finite sau text, oferind funcții de filtrare, sortare și calculare de agregări (`sum`, `avg`, `min`, `max`, `count`).

## Tehnologii

Python 3.13 cu Flask

## Rulare

### Imaginea publicată

Imaginea corespunzătoare release-ului `0.1.0` poate fi descărcată folosind tagul `0.1.0`:

```
docker pull ghcr.io/ileanabeuka/csv-processor:0.1.0
docker run -d -p 8080:8080 --name csv-processor ghcr.io/ileanabeuka/csv-processor:0.1.0
```

La publicarea unui tag de versiune, workflow-ul publică imaginea cu același tag. Versiunea aplicației este afișată de ruta `/version`.

La fiecare push pe `main` care trece testele, workflow-ul actualizează tagul `latest`:

```
docker pull ghcr.io/ileanabeuka/csv-processor:latest
docker run -d -p 8080:8080 --name csv-processor ghcr.io/ileanabeuka/csv-processor:latest
```

### Construire locală

```
docker build -t map-proiect .
docker run -d -p 8080:8080 map-proiect
```

Aplicatia asculta pe portul 8080. Verificati:

```
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/version
```

## Testare

Rulare teste cu generare raport de acoperire

```
pip install -r requirements.txt pytest pytest-cov
python -m pytest --cov=src --cov-fail-under=50 --cov-report=term-missing --cov-report=xml:coverage/coverage.xml --cov-report=html:coverage/htmlcov
```

Raportul HTML se deschide din `coverage/htmlcov/index.html`.

## Rutele implementate

| Ruta | Metoda | Descriere |
|---|---|---|
| `/health` | GET | Starea serviciului |
| `/version` | GET | Versiunea si commit-ul din care a fost construita imaginea |
| `/` | GET | Pagina de prezentare |
| `/reset` | POST | Goleste datele din memorie |
| `/datasets` | POST | Incarca un set de date. Corp: `{"name", "content"}`, unde content este CSV cu antet pe primul rand |
| `/datasets/{id}/columns` | GET | Intoarce `[{"name","type"}]`, unde type este numeric sau text |
| `/datasets/{id}/rows` | GET | Parametri optionali: filter (forma column:value), sort (nume de coloana), dir (asc/desc, implicit asc) |
| `/datasets/{id}/aggregate` | GET | Parametri obligatorii column si op, unde op este sum, avg, min, max sau count. Intoarce `{"column", "op", "value"}` |
| `/datasets/{id}` | DELETE | Sterge setul de date |

## Decizii de implementare

- Păstrarea valorilor extrase ca șiruri de caractere și deducerea dinamică a tipului coloanei. O coloană este numerică dacă toate valorile sale pot fi convertite în numere; în caz contrar, este tratată ca text. La sortare, tipul stabilește ordinea numerică sau alfabetică. Operațiile `sum` și `avg` sunt disponibile doar pentru coloane numerice. Păstrarea valorilor originale evită modificarea datelor la încărcare și permite tratarea coloanelor cu conținut mixt ca text.

- Stocarea datelor în memoria procesului, într-un obiect `Store` cu identificatori numerici, fără utilizarea unei baze de date. Această soluție evită configurarea unui sistem de stocare extern și păstrează implementarea simplă; datele sunt disponibile cât timp rulează aplicația, dar se pierd la repornirea acesteia.

- Utilizarea `Decimal` în calculele numerice, pentru a reduce erorile de reprezentare care pot apărea la calculele cu `float`.

## Exemple comenzi de testare manuală

Porniți imaginea publicată sau construiți-o local, conform secțiunii [Rulare](#rulare). Exemplele de mai jos presupun că serviciul rulează pe portul 8080.

Resetați memoria înaintea testelor — 204.

```
curl.exe -i -X POST http://localhost:8080/reset
```

1. un tabel cu o coloană curat numerică și una stricată de o singură celulă

```
curl.exe -i -H "Content-Type: application/json" -d '{"name":"stoc","content":"produs,cantitate,pret\nciocan,10,25.5\ncui,9,0.5\nbanda,n/a,1.25"}' http://localhost:8080/datasets
```

2. "cantitate" trebuie să iasă text, din cauza lui n/a; "pret" rămâne numeric

```
curl.exe -i http://localhost:8080/datasets/1/columns
```

3. sortare pe o coloană text: "10" vine înaintea lui "9", pentru că se compară alfabetic

```
curl.exe -i "http://localhost:8080/datasets/1/rows?sort=cantitate"
```

4. sumă pe o coloană text — 400

```
curl.exe -i "http://localhost:8080/datasets/1/aggregate?column=cantitate&op=sum"
```

5. un rând cu mai puține câmpuri decât antetul — 400, spunând la ce rând s-a oprit

```
curl.exe -i -H "Content-Type: application/json" -d '{"name":"stricat","content":"a,b\n1,2\n3"}' http://localhost:8080/datasets
```

6. filtrare după o valoare a unei coloane

```
curl.exe -i "http://localhost:8080/datasets/1/rows?filter=produs%3Acui"
```

7. verificarea paginii de prezentare

```
curl.exe -i http://localhost:8080/
```

8. verificarea stării serviciului

```
curl.exe -i http://localhost:8080/health
```

9. verificarea versiunii și a commit-ului din care a fost construită imaginea

```
curl.exe -i http://localhost:8080/version
```

10. un tabel cu antet, dar fără rânduri de date — 201, id-ul 2

```
curl.exe -i -H "Content-Type: application/json" -d '{"name":"gol","content":"produs,cantitate,pret"}' http://localhost:8080/datasets
```

11. verificarea coloanelor tabelului creat fără rânduri

```
curl.exe -i http://localhost:8080/datasets/2/columns
```

12. verificarea rândurilor tabelului creat fără rânduri

```
curl.exe -i http://localhost:8080/datasets/2/rows
```

13. solicitarea unui dataset inexistent — 404

```
curl.exe -i http://localhost:8080/datasets/999/columns
```

14. ștergerea primului set de date — 204

```
curl.exe -i -X DELETE http://localhost:8080/datasets/1
```

15. verificarea că datasetul șters nu mai există — 404

```
curl.exe -i http://localhost:8080/datasets/1/columns
```

Opriți și ștergeți containerul după terminarea testelor.