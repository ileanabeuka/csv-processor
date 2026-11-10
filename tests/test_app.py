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


def test_create_dataset_treats_quotes_as_literal_characters(client):
    response = client.post(
        "/datasets",
        json={
            "name": "quoted",
            "content": 'name,notes\n"Ana","likes apples"',
        },
    )

    assert response.status_code == 201
    assert store.datasets[1]["rows"] == [{"name": '"Ana"', "notes": '"likes apples"'}]


def test_create_dataset_splits_commas_even_inside_quotes(client):
    response = client.post(
        "/datasets",
        json={
            "name": "comma",
            "content": 'name,first,second\nAna,"mere, pere"',
        },
    )

    assert response.status_code == 201
    assert store.datasets[1]["rows"] == [
        {"name": "Ana", "first": '"mere', "second": ' pere"'}
    ]


def test_create_dataset_uses_comma_as_the_separator(client):
    response = client.post(
        "/datasets",
        json={"name": "semicolon", "content": "name;age\nAna;20"},
    )

    assert response.status_code == 201
    assert store.datasets[1]["columns"] == ["name;age"]
    assert store.datasets[1]["rows"] == [{"name;age": "Ana;20"}]


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


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("sum", 33), ("avg", 11.0), ("min", 3.0), ("max", 20.0), ("count", 3)],
)
def test_aggregate_numeric_column(client, operation, expected):
    created = client.post(
        "/datasets",
        json={"name": "numbers", "content": "value\n20\n3\n10"},
    )
    dataset_id = created.get_json()["id"]

    response = client.get(
        f"/datasets/{dataset_id}/aggregate?column=value&op={operation}"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "column": "value",
        "op": operation,
        "value": expected,
    }


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("min", "Ana"), ("max", "Mara")],
)
def test_aggregate_text_column(client, operation, expected):
    created = client.post(
        "/datasets",
        json={"name": "names", "content": "name\nMara\nAna\nIon"},
    )
    dataset_id = created.get_json()["id"]

    response = client.get(
        f"/datasets/{dataset_id}/aggregate?column=name&op={operation}"
    )

    assert response.status_code == 200
    assert response.get_json()["value"] == expected


def test_aggregate_count_ignores_empty_values(client):
    created = client.post(
        "/datasets",
        json={"name": "names", "content": "name\nAna\n\n   \nIon"},
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/aggregate?column=name&op=count"
    )

    assert response.status_code == 200
    assert response.get_json()["value"] == 2


def test_aggregate_sum_on_text_quantity_column_returns_bad_request(client):
    created = client.post(
        "/datasets",
        json={"name": "products", "content": "cantitate\nmult\nputin"},
    )
    dataset_id = created.get_json()["id"]

    response = client.get(
        f"/datasets/{dataset_id}/aggregate?column=cantitate&op=sum"
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "validation",
        "message": "numeric operations require a numeric column",
    }


@pytest.mark.parametrize(
    ("operation", "content", "expected"),
    [
        ("sum", "0.125", 0.13),
        ("sum", "-0.125", -0.13),
        ("avg", "0.125", 0.13),
        ("avg", "0.1\n0.2\n0.275", 0.19),
        ("min", "0.125\n0.2", 0.13),
        ("max", "0.124\n0.125", 0.13),
    ],
)
def test_aggregate_rounds_numeric_results_half_up(client, operation, content, expected):
    created = client.post(
        "/datasets",
        json={"name": "numbers", "content": f"value\n{content}"},
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/aggregate?column=value&op={operation}"
    )

    assert response.status_code == 200
    assert response.get_json()["value"] == expected


def test_aggregate_average_handles_large_finite_values(client):
    created = client.post(
        "/datasets",
        json={"name": "large numbers", "content": "value\n1e308\n1e308"},
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/aggregate?column=value&op=avg"
    )

    assert response.status_code == 200
    assert response.get_json()["value"] == 1e308


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("column=value", "column and op are required"),
        ("op=sum", "column and op are required"),
        ("column=missing&op=sum", "column does not exist"),
        ("column=value&op=median", "op must be"),
        ("column=name&op=sum", "numeric operations require a numeric column"),
        ("column=name&op=avg", "numeric operations require a numeric column"),
    ],
)
def test_aggregate_rejects_invalid_parameters(client, query, message):
    client.post(
        "/datasets",
        json={"name": "data", "content": "value,name\n1,Ana"},
    )

    response = client.get(f"/datasets/1/aggregate?{query}")

    assert response.status_code == 400
    assert message in response.get_json()["message"]


def test_aggregate_returns_validation_error_for_empty_column(client):
    created = client.post(
        "/datasets",
        json={"name": "empty", "content": "value\n"},
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/aggregate?column=value&op=sum"
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "cannot aggregate an empty column"


def test_aggregate_returns_validation_error_when_sum_exceeds_json_number_range(client):
    created = client.post(
        "/datasets",
        json={"name": "large numbers", "content": "value\n1e308\n1e308"},
    )

    response = client.get(
        f"/datasets/{created.get_json()['id']}/aggregate?column=value&op=sum"
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == (
        "aggregate result is outside the supported numeric range"
    )


def test_aggregate_returns_not_found_for_unknown_dataset(client):
    response = client.get("/datasets/42/aggregate?column=value&op=sum")

    assert response.status_code == 404
    assert response.get_json() == {
        "error": "not_found",
        "message": "dataset does not exist",
    }


def test_delete_dataset_removes_it(client):
    created = client.post(
        "/datasets",
        json={"name": "temporary", "content": "value\n1"},
    )
    dataset_id = created.get_json()["id"]

    response = client.delete(f"/datasets/{dataset_id}")

    assert response.status_code == 204
    assert dataset_id not in store.datasets
    assert client.get(f"/datasets/{dataset_id}/rows").status_code == 404


def test_delete_dataset_returns_not_found_for_unknown_id(client):
    response = client.delete("/datasets/42")

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
