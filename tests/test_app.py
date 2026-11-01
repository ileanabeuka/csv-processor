import pytest

from src.app import APP_NAME, app, store


@pytest.fixture
def client():
    app.config["TESTING"] = True
    store.reset()
    with app.test_client() as test_client:
        yield test_client


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body


def test_version_reads_environment(client, monkeypatch):
    monkeypatch.setenv("APP_COMMIT", "abc1234")
    body = client.get("/version").get_json()
    assert body["commit"] == "abc1234"
    assert body["app"] == APP_NAME
    assert body["version"]
    assert body["built_at"]


def test_reset_returns_no_content(client):
    assert client.post("/reset").status_code == 204


def test_reset_rejects_get(client):
    assert client.get("/reset").status_code == 405


def test_reset_clears_store(client):
    store.next_id = 42
    client.post("/reset")
    assert store.next_id == 1


def test_create_dataset_stores_csv(client):
    response = client.post(
        "/datasets",
        json={"name": "people", "content": "name,age\nAna,20\nIon,21"},
    )

    assert response.status_code == 201
    assert response.get_json() == {"id": 1, "name": "people"}
    assert store.datasets[1] == {
        "id": 1,
        "name": "people",
        "columns": ["name", "age"],
        "rows": [
            {"name": "Ana", "age": "20"},
            {"name": "Ion", "age": "21"},
        ],
    }


def test_create_dataset_accepts_header_with_trailing_newline(client):
    response = client.post(
        "/datasets",
        json={"name": "empty", "content": "produs,cantitate,pret\n"},
    )

    assert response.status_code == 201
    assert response.get_json() == {"id": 1, "name": "empty"}
    assert store.datasets[1]["rows"] == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("name,age\nAna", "row 2 has 1 fields; expected 2"),
        ("name,age\nAna,20,extra", "row 2 has 3 fields; expected 2"),
    ],
)
def test_create_dataset_rejects_rows_with_wrong_field_count(client, content, message):
    response = client.post("/datasets", json={"name": "people", "content": content})

    assert response.status_code == 400
    assert response.get_json() == {"error": "validation", "message": message}
    assert store.next_id == 1
    assert store.datasets == {}


def test_create_dataset_accepts_750_total_rows_including_header(client):
    content = "value\n" + "\n".join(str(value) for value in range(749))

    response = client.post("/datasets", json={"name": "maximum", "content": content})

    assert response.status_code == 201
    assert len(store.datasets[1]["rows"]) == 749


def test_create_dataset_rejects_more_than_750_total_rows(client):
    content = "value\n" + "\n".join(str(value) for value in range(750))

    response = client.post("/datasets", json={"name": "too large", "content": content})

    assert response.status_code == 409
    assert response.get_json()["error"] == "conflict"
    assert store.next_id == 1
    assert store.datasets == {}


def test_create_dataset_rejects_malformed_row_before_row_limit(client):
    content = "first,second\n" + "\n".join(f"{value},ok" for value in range(749))
    content += "\nmalformed"

    response = client.post("/datasets", json={"name": "invalid", "content": content})

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "validation",
        "message": "row 751 has 1 fields; expected 2",
    }
    assert store.next_id == 1
    assert store.datasets == {}


def test_list_columns_classifies_numeric_and_text_columns(client):
    created = client.post(
        "/datasets",
        json={
            "name": "people",
            "content": "name,age\nAna,20\nIon,21\nMara,",
        },
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/columns")

    assert response.status_code == 200
    assert response.get_json() == [
        {"name": "name", "type": "text"},
        {"name": "age", "type": "text"},
    ]


def test_list_columns_classifies_clean_numeric_column(client):
    created = client.post(
        "/datasets",
        json={"name": "numbers", "content": "age\n20\n21"},
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/columns")

    assert response.status_code == 200
    assert response.get_json() == [{"name": "age", "type": "numeric"}]


def test_list_columns_classifies_empty_dataset_column_as_text(client):
    created = client.post(
        "/datasets",
        json={"name": "empty", "content": "name,age"},
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/columns")

    assert response.status_code == 200
    assert response.get_json() == [
        {"name": "name", "type": "text"},
        {"name": "age", "type": "text"},
    ]


def test_list_columns_returns_not_found_for_unknown_dataset(client):
    response = client.get("/datasets/42/columns")

    assert response.status_code == 404
    assert response.get_json() == {
        "error": "not_found",
        "message": "dataset does not exist",
    }


def test_list_rows_returns_all_rows_in_original_order(client):
    created = client.post(
        "/datasets",
        json={"name": "people", "content": "name,age\nAna,20\nIon,3"},
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/rows")

    assert response.status_code == 200
    assert response.get_json() == {
        "rows": [
            {"name": "Ana", "age": "20"},
            {"name": "Ion", "age": "3"},
        ]
    }


@pytest.mark.parametrize(
    ("direction", "expected_ages"),
    [
        ("asc", ["3", "11", "20"]),
        ("desc", ["20", "11", "3"]),
    ],
)
def test_list_rows_sorts_numeric_column(client, direction, expected_ages):
    created = client.post(
        "/datasets",
        json={"name": "people", "content": "name,age\nAna,20\nIon,3\nMara,11"},
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/rows?sort=age&dir={direction}"
    )

    assert response.status_code == 200
    assert [row["age"] for row in response.get_json()["rows"]] == expected_ages


def test_list_rows_filters_and_sorts_rows(client):
    created = client.post(
        "/datasets",
        json={
            "name": "people",
            "content": "city,name,age\nIasi,Ion,3\nBucuresti,Mara,20\nBucuresti,Ana,11",
        },
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/rows?filter=city:Bucuresti&sort=age"
    )

    assert response.status_code == 200
    assert response.get_json()["rows"] == [
        {"city": "Bucuresti", "name": "Ana", "age": "11"},
        {"city": "Bucuresti", "name": "Mara", "age": "20"},
    ]


def test_list_rows_sorts_text_without_case_sensitivity(client):
    created = client.post(
        "/datasets",
        json={"name": "names", "content": "name\nmara\nAna\nion"},
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/rows?sort=name")

    assert response.status_code == 200
    assert [row["name"] for row in response.get_json()["rows"]] == ["Ana", "ion", "mara"]


def test_list_rows_sorts_decimal_values_numerically(client):
    created = client.post(
        "/datasets",
        json={"name": "decimal numbers", "content": "value\n10.25\n-2\n1.5"},
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/rows?sort=value")

    assert response.status_code == 200
    assert [row["value"] for row in response.get_json()["rows"]] == [
        "-2",
        "1.5",
        "10.25",
    ]


def test_list_rows_sorts_text_column_alphabetically_if_one_value_is_not_numeric(client):
    created = client.post(
        "/datasets",
        json={
            "name": "quantities",
            "content": "cantitate\n10\n9\nn/a",
        },
    )

    response = client.get(f"/datasets/{created.get_json()['id']}/rows?sort=cantitate")

    assert response.status_code == 200
    assert [row["cantitate"] for row in response.get_json()["rows"]] == ["10", "9", "n/a"]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("filter=invalid", "filter must use the column:value format"),
        ("filter=missing:value", "filter column does not exist"),
        ("sort=missing", "sort column does not exist"),
        ("dir=sideways", "dir must be asc or desc"),
    ],
)
def test_list_rows_rejects_invalid_query_parameters(client, query, message):
    created = client.post("/datasets", json={"name": "data", "content": "value\none"})

    response = client.get(f"/datasets/{created.get_json()['id']}/rows?{query}")

    assert response.status_code == 400
    assert response.get_json() == {"error": "validation", "message": message}


def test_list_rows_returns_not_found_for_unknown_dataset(client):
    response = client.get("/datasets/42/rows")

    assert response.status_code == 404
    assert response.get_json() == {
        "error": "not_found",
        "message": "dataset does not exist",
    }


def test_home_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")


def test_unknown_route_returns_not_found(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"
