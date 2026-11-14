from pathlib import Path


def test_dockerfile_contents():
    base_dir = Path(__file__).parent.parent
    dockerfile_path = base_dir / "Dockerfile"

    assert dockerfile_path.is_file(), "Dockerfile must exist"
    content = dockerfile_path.read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in content or "FROM python:3.12-slim" in content
    assert "WORKDIR /app" in content
    assert "requirements.txt" in content
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "/health" in content
    assert "mkdir -p /app/data" in content
    assert 'CMD ["uvicorn", "src.main:app"' in content


def test_dockerignore_contents():
    base_dir = Path(__file__).parent.parent
    dockerignore_path = base_dir / ".dockerignore"

    assert dockerignore_path.is_file(), ".dockerignore must exist"
    content = dockerignore_path.read_text(encoding="utf-8")

    assert ".git" in content
    assert ".venv" in content
    assert "__pycache__" in content
    assert "*.db*" in content
    assert "tests/" in content


def test_docker_compose_contents():
    base_dir = Path(__file__).parent.parent
    compose_path = base_dir / "docker-compose.yml"

    assert compose_path.is_file(), "docker-compose.yml must exist"
    content = compose_path.read_text(encoding="utf-8")

    assert "services:" in content
    assert "banca-api:" in content
    assert "8000:8000" in content
    assert "/app/data" in content
    assert "unless-stopped" in content
