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


def test_home_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")


def test_unknown_route_returns_not_found(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"
