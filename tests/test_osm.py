from org_research_agent.organisation import UNKNOWN
from org_research_agent.osm import build_query, parse_elements

ELEMENTS = [
    {"tags": {"name": "Example Dental", "amenity": "dentist", "addr:suburb": "Testville"}},
    {
        "tags": {
            "name": "Sample Physio",
            "healthcare": "physiotherapist",
            "website": "https://a.test",
        }
    },
    {"tags": {"name": "sample physio", "healthcare": "physiotherapist"}},  # Duplicate name.
    {"tags": {"amenity": "pharmacy"}},  # No name.
    {"tags": {"name": "Demo Chemist", "amenity": "pharmacy", "contact:website": "https://b.test"}},
]


def test_query_contains_point_and_radius():
    query = build_query(-1.5, 2.5, 3000)
    assert "around:3000,-1.5,2.5" in query
    assert "dentist" in query and "physiotherapist" in query


def test_parse_skips_unnamed_and_duplicates():
    names = [org.name for org in parse_elements(ELEMENTS)]
    assert names == ["Demo Chemist", "Example Dental", "Sample Physio"]


def test_parse_maps_types_suburb_and_website():
    orgs = {org.name: org for org in parse_elements(ELEMENTS)}
    assert orgs["Example Dental"].type == "dental practice"
    assert orgs["Example Dental"].suburb == "Testville"
    assert orgs["Sample Physio"].type == "physiotherapy"
    assert orgs["Sample Physio"].website == "https://a.test"
    assert orgs["Demo Chemist"].website == "https://b.test"
    assert orgs["Demo Chemist"].suburb == UNKNOWN
