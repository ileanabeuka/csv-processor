import math
import os
import time

from flask import Flask, jsonify, request

APP_NAME = "map-project"
APP_VERSION = "0.1.0"
MAX_DATASET_ROWS = 750

STARTED_AT = time.monotonic()

app = Flask(__name__)


class Store:
    """Holds the application data in memory.

    Everything is lost when the container restarts.
    Add your theme's structures here.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.next_id = 1
        self.datasets = {}


store = Store()


def numeric_value(value):
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def column_type(dataset, column):
    values = [row[column] for row in dataset["rows"]]
    if values and all(numeric_value(value) is not None for value in values):
        return "numeric"
    return "text"


def get_dataset(dataset_id):
    dataset = store.datasets.get(dataset_id)
    if dataset is None:
        return None, (jsonify(error="not_found", message="dataset does not exist"), 404)
    return dataset, None


def filter_rows(dataset, rows, filter_expression):
    if filter_expression is None:
        return rows, None
    if ":" not in filter_expression:
        return None, (jsonify(error="validation", message="filter must use the column:value format"), 400)

    filter_column, filter_value = filter_expression.split(":", 1)
    if filter_column not in dataset["columns"]:
        return None, (jsonify(error="validation", message="filter column does not exist"), 400)

    return [row for row in rows if row[filter_column] == filter_value], None


def sort_rows(dataset, rows, sort_column, direction):
    if direction not in {"asc", "desc"}:
        return None, (jsonify(error="validation", message="dir must be asc or desc"), 400)
    if sort_column is None:
        return rows, None
    if sort_column not in dataset["columns"]:
        return None, (jsonify(error="validation", message="sort column does not exist"), 400)

    if column_type(dataset, sort_column) == "numeric":
        sort_key = lambda row: float(row[sort_column])
    else:
        sort_key = lambda row: row[sort_column].casefold()
    return sorted(rows, key=sort_key, reverse=direction == "desc"), None


@app.get("/health")
def health():
    return jsonify(
        status="ok",
        uptime_seconds=int(time.monotonic() - STARTED_AT),
    )


@app.get("/version")
def version():
    return jsonify(
        app=APP_NAME,
        version=APP_VERSION,
        commit=os.getenv("APP_COMMIT", "dev"),
        built_at=os.getenv("APP_BUILT_AT", "unknown"),
    )


@app.post("/reset")
def reset():
    store.reset()
    return "", 204


@app.post("/datasets")
def create_dataset():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="validation", message="expected a JSON object"), 400

    name = payload.get("name")
    content = payload.get("content")
    if not isinstance(name, str) or not name.strip():
        return jsonify(error="validation", message="name must be a non-empty string"), 400
    if not isinstance(content, str) or not content.strip():
        return jsonify(error="validation", message="content must be a non-empty CSV string"), 400

    lines = content.splitlines()
    if not lines:
        return jsonify(error="validation", message="CSV must contain a valid header row"), 400

    headers = lines[0].split(",")
    if any(not header.strip() for header in headers):
        return jsonify(error="validation", message="CSV must have non-empty column names in its first row"), 400
    if len(headers) != len(set(headers)):
        return jsonify(error="validation", message="CSV column names must be unique"), 400

    rows = []
    for row_number, line in enumerate(lines[1:], start=2):
        values = line.split(",")
        if len(values) != len(headers):
            return jsonify(
                error="validation",
                message=f"row {row_number} has {len(values)} fields; expected {len(headers)}",
            ), 400
        rows.append(dict(zip(headers, values)))

    if len(lines) > MAX_DATASET_ROWS:
        return jsonify(
            error="conflict",
            message=f"dataset cannot contain more than {MAX_DATASET_ROWS} rows including the header",
        ), 409

    dataset_id = store.next_id
    store.next_id += 1
    store.datasets[dataset_id] = {
        "id": dataset_id,
        "name": name.strip(),
        "columns": headers,
        "rows": rows,
    }
    return jsonify(id=dataset_id, name=name.strip()), 201


@app.get("/datasets/<int:dataset_id>/columns")
def list_columns(dataset_id):
    dataset, error = get_dataset(dataset_id)
    if error:
        return error

    return jsonify(
        [
            {"name": column, "type": column_type(dataset, column)}
            for column in dataset["columns"]
        ]
    )


@app.get("/datasets/<int:dataset_id>/rows")
def list_rows(dataset_id):
    dataset, error = get_dataset(dataset_id)
    if error:
        return error

    rows, error = filter_rows(dataset, dataset["rows"], request.args.get("filter"))
    if error:
        return error

    rows, error = sort_rows(
        dataset,
        rows,
        request.args.get("sort"),
        request.args.get("dir", "asc"),
    )
    if error:
        return error

    return jsonify(rows=rows)


@app.get("/")
def home():
    commit = os.getenv("APP_COMMIT", "dev")
    return f"""<!DOCTYPE html>
<html lang="ro"><head><meta charset="utf-8"><title>{APP_NAME}</title></head>
<body>
<h1>{APP_NAME}</h1>
<p>Autor: NUME PRENUME, grupa GRUPA</p>
<p>Tema: NUMARUL TEMEI</p>
<p>Versiune: {APP_VERSION}, commit {commit}</p>
</body></html>"""


@app.errorhandler(404)
def not_found(_):
    return jsonify(error="not_found", message="route does not exist"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
