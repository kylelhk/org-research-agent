import org_research_agent


def test_package_imports_and_has_version():
    # A minimal check that the package is installed and importable.
    assert org_research_agent.__version__ == "0.1.0"
