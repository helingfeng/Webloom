import pytest
from app.engine.parameters import (
    normalize_definitions,
    resolve_inputs,
    effective_start_url,
)
from app.engine.domains import normalize_domain


def test_defaults_are_typed_and_explicit_values_win():
    definitions = [
        {"name": "pages", "type": "number", "default": "3"},
        {"name": "enabled", "type": "boolean", "default": "false"},
        {"name": "optional", "type": "string", "required": False},
    ]
    assert resolve_inputs(definitions, {}) == {"pages": 3, "enabled": False}
    assert resolve_inputs(definitions, {"pages": 0, "enabled": True}) == {
        "pages": 0,
        "enabled": True,
    }
    assert (
        effective_start_url("https://old.test", {"url": "https://new.test"})
        == "https://new.test"
    )


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {"count": True},
        {"count": "1"},
        {"count": float("inf")},
        {"count": 1, "extra": 2},
    ],
)
def test_invalid_runtime_inputs_are_rejected(inputs):
    with pytest.raises(ValueError):
        resolve_inputs([{"name": "count", "type": "number", "required": True}], inputs)


@pytest.mark.parametrize(
    "definitions",
    [
        [{"name": "", "type": "string"}],
        [{"name": "a", "type": "string"}, {"name": " a ", "type": "string"}],
        [
            {"name": "Authorization", "type": "header"},
            {"name": "authorization", "type": "header"},
        ],
        [{"name": "bad header", "type": "header"}],
        [{"name": "enabled", "type": "boolean", "default": "no"}],
    ],
)
def test_ambiguous_definitions_are_rejected(definitions):
    with pytest.raises(ValueError):
        normalize_definitions(definitions)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HTTPS://Admin.Example.COM:8443/login", "admin.example.com"),
        ("*.example.com", "example.com"),
        (".EXAMPLE.com", "example.com"),
        ("[::1]", "::1"),
        ("", ""),
    ],
)
def test_domain_normalization(value, expected):
    assert normalize_domain(value) == expected


async def test_execution_snapshot_migration_preserves_old_records(
    db_engine, monkeypatch
):
    import app.database as database
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.execution import Execution

    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as db:
        record = Execution(
            target_type="script",
            target_id=1,
            mode="manual",
            inputs={},
            outputs={},
            logs="",
            status="success",
        )
        db.add(record)
        await db.commit()
        id = record.id
    async with db_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE executions DROP COLUMN script_snapshot"))
    monkeypatch.setattr(database, "engine", db_engine)
    await database.init_db()
    await database.init_db()
    async with maker() as db:
        record = await db.get(Execution, id)
        assert record.status == "success" and record.script_snapshot is None
