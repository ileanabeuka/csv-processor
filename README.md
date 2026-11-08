[![CI](https://github.com/ileanabeuka/csv-processor/actions/workflows/ci.yml/badge.svg)](https://github.com/ileanabeuka/csv-processor/actions/workflows/ci.yml)

# Procesor CSV

Proiect individual la disciplina Metode avansate de programare, anul universitar 2026-2027.

## Autor

- **Nume:** Beuka Ileana
- **Grupa:** 1.1
- **Tema:** Tema 8 – Procesor CSV

## Descriere

Aplicatia este un serviciu web care primeste tabele in format CSV, le pastreaza in memorie si permite interogarea lor. Serviciul deduce automat daca o coloana contine numere sau text, oferind functii de filtrare, sortare si calculare de statistici.

## Tehnologii

Python 3.13 cu Flask

## Rulare

```
docker build -t map-proiect .
docker run -d -p 8080:8080 map-proiect
```

Aplicatia asculta pe portul 8080. Verificati:

```
curl http://localhost:8080/health
curl http://localhost:8080/version
```

## Testare

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