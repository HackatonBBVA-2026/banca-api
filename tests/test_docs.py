from pathlib import Path


def test_readme_and_env_example_exist():
    base_dir = Path(__file__).parent.parent
    readme_path = base_dir / "README.md"
    env_example_path = base_dir / ".env.example"

    assert readme_path.is_file(), "README.md must exist"
    assert env_example_path.is_file(), ".env.example must exist"


def test_env_example_contents():
    base_dir = Path(__file__).parent.parent
    content = (base_dir / ".env.example").read_text(encoding="utf-8")

    expected_vars = [
        "DATABASE_URL",
        "SEED_VALUE",
        "SIMULATION_ENABLED",
        "SIMULATION_INTERVAL_MIN",
        "SIMULATION_INTERVAL_MAX",
    ]
    for var in expected_vars:
        assert f"{var}=" in content, f"{var} should be defined in .env.example"


def test_readme_sections_and_keywords():
    base_dir = Path(__file__).parent.parent
    content = (base_dir / "README.md").read_text(encoding="utf-8")

    assert "banca-api: Simulador Transaccional y Billetera Digital" in content
    assert "SSE" in content or "Server-Sent Events" in content
    assert "./init.sh --bootstrap" in content
    assert "python -m src.seed --force" in content
    assert "EventSource" in content

    # All 10 tables documented
    tables = [
        "movimientos",
        "clientes",
        "cuentas",
        "tarjetas",
        "comercios",
        "pagos_programados",
        "beneficiarios",
        "tipo_cambio",
        "eventos_seguridad",
        "productos_referenciales",
    ]
    for table in tables:
        assert table in content, f"Table {table} must be documented in README.md"

    # Edge cases
    assert "duplicado" in content.lower()
    assert "revertid" in content.lower()
    assert "atípico" in content.lower() or "anómalo" in content.lower() or "atipico" in content.lower() or "anomalo" in content.lower()
