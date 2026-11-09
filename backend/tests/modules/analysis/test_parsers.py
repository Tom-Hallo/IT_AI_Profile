"""Tests for static manifest parsers across language ecosystems (PBI-012)."""

from app.modules.analysis.parsers import (
    parse_build_gradle,
    parse_cargo_toml,
    parse_dotnet_csproj,
    parse_go_mod,
    parse_package_json,
    parse_pipfile,
    parse_pom_xml,
    parse_pyproject_toml,
    parse_requirements_txt,
    parse_setup_cfg_or_py,
    verify_lockfile_health,
)


def test_python_requirements_parser():
    content = """
    # Core framework
    fastapi==0.110.0
    uvicorn[standard]>=0.28.0
    sqlalchemy>=2.0.0; python_version >= '3.10'
    -i https://pypi.org/simple
    --extra-index-url https://custom.repo/simple
    alembic~=1.13.1 # Database migrations
    pydantic>2.0,<=2.7.0
    """
    res = parse_requirements_txt(content, "requirements.txt")
    assert res.is_valid
    assert res.ecosystem == "Python"
    assert len(res.dependencies) == 5

    dep_fastapi = res.find_dependency("fastapi")
    assert dep_fastapi is not None
    assert dep_fastapi.version_spec == "==0.110.0"
    assert dep_fastapi.line_number == 3

    dep_alembic = res.find_dependency("alembic")
    assert dep_alembic is not None
    assert dep_alembic.version_spec == "~=1.13.1"


def test_python_pyproject_toml_parser():
    content = """
    [project]
    name = "my-service"
    version = "1.0.0"
    dependencies = [
        "fastapi>=0.100.0",
        "redis==5.0.0",
        "pydantic",
    ]

    [project.optional-dependencies]
    dev = [
        "pytest>=8.0.0",
        "ruff",
    ]
    """
    res = parse_pyproject_toml(content, "pyproject.toml")
    assert res.is_valid
    assert len(res.dependencies) == 5
    fastapi_dep = res.find_dependency("fastapi")
    assert fastapi_dep is not None
    assert fastapi_dep.version_spec == ">=0.100.0"
    pytest_dep = res.find_dependency("pytest")
    assert pytest_dep is not None
    assert pytest_dep.is_dev


def test_python_pipfile_parser():
    content = """
    [[source]]
    url = "https://pypi.org/simple"
    verify_ssl = true
    name = "pypi"

    [packages]
    django = "~=4.2"
    celery = "*"

    [dev-packages]
    pytest = ">=7.0"
    """
    res = parse_pipfile(content, "Pipfile")
    assert res.is_valid
    assert len(res.dependencies) == 3
    django_dep = res.find_dependency("django")
    assert django_dep is not None
    assert django_dep.version_spec == "~=4.2"
    assert not django_dep.is_dev


def test_untrusted_setup_py_never_executed():
    """Requirement 5.12: Untrusted code never being executed."""
    # Mã độc hại nếu chạy qua exec() sẽ tạo file hoặc ném RuntimeError
    malicious_setup = """
    import sys
    # Cố tình ném lỗi nếu ai đó cố execute setup.py
    if __name__ == '__main__':
        raise RuntimeError("UNTRUSTED CODE EXECUTED!")

    from setuptools import setup

    setup(
        name="unsafe-lib",
        install_requires=[
            "requests>=2.28.0",
            "flask>=3.0.0",
        ]
    )
    """
    # Parser tĩnh tuyệt đối không ném RuntimeError vì không hề chạy exec/eval
    res = parse_setup_cfg_or_py(malicious_setup, "setup.py")
    assert res.is_valid
    assert res.find_dependency("flask") is not None
    assert res.find_dependency("requests") is not None


def test_javascript_package_json_parser_and_conflicts():
    """Requirement 5.4 & 5.5: Frameworks, lockfiles and conflicting dependencies."""
    content = """{
        "name": "frontend-app",
        "version": "1.0.0",
        "workspaces": ["packages/*"],
        "dependencies": {
            "react": "^18.2.0",
            "react-dom": "^18.2.0",
            "axios": "^1.6.0"
        },
        "devDependencies": {
            "react": "^19.0.0-rc",
            "typescript": "^5.3.0",
            "vite": "^5.1.0"
        }
    }"""
    res = parse_package_json(content, "package.json")
    assert res.is_valid
    assert res.ecosystem == "JavaScript/TypeScript"
    assert res.metadata.get("is_monorepo") is True
    # Kiểm tra phát hiện xung đột phiên bản giữa prod và dev dependencies
    assert len(res.conflicting_dependencies) > 0
    assert "react" in res.conflicting_dependencies[0].lower()


def test_malformed_package_json_handled_safely():
    """Requirement 5.5: Corrupted or malformed manifests."""
    corrupted_json = (
        '{\n  "name": "broken-app",\n  "dependencies": { missing_quotes: 1\n'
    )
    res = parse_package_json(corrupted_json, "package.json")
    assert not res.is_valid
    assert "lỗi định dạng json" in res.error_message.lower()
    assert res.dependencies == []


def test_lockfile_health_verification():
    """Requirement 5.5: Missing or malformed lockfile."""
    # 1. Hợp lệ
    valid_lock = '{"name": "test", "lockfileVersion": 3, "packages": {}}'
    healthy, corrupted, err = verify_lockfile_health(valid_lock, "package-lock.json")
    assert healthy
    assert not corrupted

    # 2. Hỏng JSON
    corrupted_lock = '{"name": "test", "lockfileVersion": 3'
    healthy, corrupted, err = verify_lockfile_health(
        corrupted_lock, "package-lock.json"
    )
    assert not healthy
    assert corrupted
    assert "lỗi cú pháp" in err.lower()

    # 3. Rỗng
    empty_lock = "   "
    healthy, corrupted, err = verify_lockfile_health(empty_lock, "package-lock.json")
    assert not healthy
    assert corrupted


def test_jvm_pom_xml_and_gradle_parsers():
    pom_content = """<?xml version="1.0" encoding="UTF-8"?>
    <project xmlns="http://maven.apache.org/POM/4.0.0">
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-web</artifactId>
                <version>3.2.0</version>
            </dependency>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.10.0</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </project>
    """
    res_pom = parse_pom_xml(pom_content, "pom.xml")
    assert res_pom.is_valid
    assert len(res_pom.dependencies) == 2
    spring_dep = res_pom.find_dependency(
        "org.springframework.boot:spring-boot-starter-web"
    )
    assert spring_dep is not None
    assert spring_dep.version_spec == "3.2.0"
    assert not spring_dep.is_dev

    gradle_content = """
    plugins {
        id 'java'
    }
    dependencies {
        implementation 'org.springframework.boot:spring-boot-starter-data-jpa:3.2.0'
        testImplementation("org.junit.jupiter:junit-jupiter-api:5.10.0")
    }
    """
    res_gradle = parse_build_gradle(gradle_content, "build.gradle")
    assert res_gradle.is_valid
    assert len(res_gradle.dependencies) == 2


def test_dotnet_csproj_parser():
    csproj_content = """<Project Sdk="Microsoft.NET.Sdk.Web">
      <ItemGroup>
        <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="8.0.0" />
        <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer"
        Version="8.0.0" />
      </ItemGroup>
    </Project>
    """
    res = parse_dotnet_csproj(csproj_content, "Backend.csproj")
    assert res.is_valid
    assert len(res.dependencies) == 2
    assert res.find_dependency("Microsoft.AspNetCore.OpenApi") is not None


def test_go_mod_and_cargo_toml_parsers():
    go_mod = """
    module github.com/example/myapi

    go 1.22

    require (
        github.com/gin-gonic/gin v1.9.1
        github.com/google/uuid v1.6.0
    )
    """
    res_go = parse_go_mod(go_mod, "go.mod")
    assert res_go.is_valid
    assert len(res_go.dependencies) == 2
    assert res_go.find_dependency("github.com/gin-gonic/gin") is not None

    cargo_toml = """
    [package]
    name = "web_service"
    version = "0.1.0"

    [dependencies]
    actix-web = "4.4.0"
    tokio = { version = "1.35", features = ["full"] }
    serde = "1.0"
    """
    res_rust = parse_cargo_toml(cargo_toml, "Cargo.toml")
    assert res_rust.is_valid
    assert len(res_rust.dependencies) == 3
    assert res_rust.find_dependency("actix-web") is not None
