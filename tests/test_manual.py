import pytest

from org_research_agent.manual import ManualListError, check_minimum, combine, load_manual
from org_research_agent.organisation import Organisation

TOML = """
[[organisation]]
name = "Made Up Clinic"
type = "GP clinic"
suburb = "Testville"
website = "https://madeup.test"

[[organisation]]
name = "Bare Minimum Practice"
"""


def write(tmp_path, text):
    path = tmp_path / "manual.toml"
    path.write_text(text)
    return path


def test_missing_file_means_empty_list(tmp_path):
    assert load_manual(tmp_path / "nope.toml") == []


def test_loads_entries_and_marks_source(tmp_path):
    orgs = load_manual(write(tmp_path, TOML))
    assert [org.name for org in orgs] == ["Made Up Clinic", "Bare Minimum Practice"]
    assert orgs[0].website == "https://madeup.test"
    assert orgs[1].type == "unknown"
    assert all(org.source == "manual" for org in orgs)


def test_entry_without_name_is_rejected(tmp_path):
    with pytest.raises(ManualListError, match="no name"):
        load_manual(write(tmp_path, '[[organisation]]\ntype = "x"'))


def test_invalid_toml_is_rejected(tmp_path):
    with pytest.raises(ManualListError, match="not valid TOML"):
        load_manual(write(tmp_path, "= broken"))


def test_combine_dedupes_and_manual_wins():
    osm = [Organisation("Alpha"), Organisation("Beta", suburb="Old")]
    manual = [Organisation("beta", suburb="New", source="manual"), Organisation("Gamma")]
    result = combine(osm, manual)
    assert [org.name for org in result] == ["Alpha", "beta", "Gamma"]
    assert result[1].suburb == "New"


def test_minimum_check():
    orgs = [Organisation(f"Org {i}") for i in range(3)]
    check_minimum(orgs, 3)
    with pytest.raises(ManualListError, match="minimum is 4"):
        check_minimum(orgs, 4)
