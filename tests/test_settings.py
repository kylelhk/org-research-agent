import pytest

from org_research_agent.settings import SettingsError, load_settings

VALID = """
[area]
suburbs = ["Testville", "East Testville"]
radius_km = 3
min_organisations = 10

[fit]
types = ["type a", "type b"]
min_staff = 2

[prompts]
research = "Synthetic prompt for tests."
"""


def write(tmp_path, text):
    path = tmp_path / "settings.toml"
    path.write_text(text)
    return path


def test_loads_valid_settings(tmp_path):
    settings = load_settings(write(tmp_path, VALID))
    assert settings.area.suburbs == ("Testville", "East Testville")
    assert settings.area.radius_km == 3
    assert settings.fit.min_staff == 2
    assert settings.prompts.research == "Synthetic prompt for tests."


def test_optional_lists_default_to_empty(tmp_path):
    settings = load_settings(write(tmp_path, VALID))
    assert settings.area.nearby_suburbs == ()
    assert settings.area.allowed_terms == ()


def test_optional_lists_are_read(tmp_path):
    text = VALID.replace(
        "min_organisations = 10",
        'min_organisations = 10\nnearby_suburbs = ["Northtown"]\nallowed_terms = ["Main Road"]',
    )
    settings = load_settings(write(tmp_path, text))
    assert settings.area.nearby_suburbs == ("Northtown",)
    assert settings.area.allowed_terms == ("Main Road",)


def test_optional_list_must_hold_strings(tmp_path):
    text = VALID.replace("min_organisations = 10", "min_organisations = 10\nnearby_suburbs = [1]")
    with pytest.raises(SettingsError, match="nearby_suburbs"):
        load_settings(write(tmp_path, text))


def test_centre_is_optional(tmp_path):
    settings = load_settings(write(tmp_path, VALID))
    assert settings.area.centre_lat is None and settings.area.centre_lon is None


def test_centre_is_read(tmp_path):
    text = VALID.replace("radius_km = 3", "radius_km = 3\ncentre_lat = -1.5\ncentre_lon = 2.5")
    settings = load_settings(write(tmp_path, text))
    assert (settings.area.centre_lat, settings.area.centre_lon) == (-1.5, 2.5)


def test_centre_out_of_range_is_rejected(tmp_path):
    text = VALID.replace("radius_km = 3", "radius_km = 3\ncentre_lat = 95")
    with pytest.raises(SettingsError, match="centre_lat"):
        load_settings(write(tmp_path, text))


def test_missing_file_gives_helpful_error(tmp_path):
    with pytest.raises(SettingsError, match="not found"):
        load_settings(tmp_path / "nope.toml")


def test_invalid_toml(tmp_path):
    with pytest.raises(SettingsError, match="not valid TOML"):
        load_settings(write(tmp_path, "this is = = not toml"))


def test_missing_section(tmp_path):
    with pytest.raises(SettingsError, match=r"\[fit\]"):
        load_settings(write(tmp_path, VALID.replace("[fit]", "[other]")))


def test_missing_key(tmp_path):
    with pytest.raises(SettingsError, match="min_staff"):
        load_settings(write(tmp_path, VALID.replace("min_staff = 2", "")))


def test_placeholder_prompt_is_rejected(tmp_path):
    text = VALID.replace("Synthetic prompt for tests.", "REPLACE_IN_PRIVATE_FILE")
    with pytest.raises(SettingsError, match="placeholder"):
        load_settings(write(tmp_path, text))


def test_empty_type_list_is_rejected(tmp_path):
    text = VALID.replace('types = ["type a", "type b"]', "types = []")
    with pytest.raises(SettingsError, match="non-empty"):
        load_settings(write(tmp_path, text))


@pytest.mark.parametrize("bad", ["0", "-1", '"3"', "true"])
def test_radius_must_be_positive_number(tmp_path, bad):
    text = VALID.replace("radius_km = 3", f"radius_km = {bad}")
    with pytest.raises(SettingsError, match="positive number"):
        load_settings(write(tmp_path, text))


def test_example_file_is_refused():
    # The shipped example still has a placeholder prompt, so it must not load.
    with pytest.raises(SettingsError, match="placeholder"):
        load_settings("config/settings.example.toml")
