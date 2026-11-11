"""Tests for finding websites by search. All names and sites are made up."""

import urllib.error

import pytest

from org_research_agent.organisation import Organisation
from org_research_agent.website_lookup import (
    CHECKED,
    FOUND,
    NOT_FOUND,
    SAVED,
    WebsiteLookupError,
    brave_search,
    distinctive_words,
    find_website,
    find_websites,
    is_directory,
    is_own_site,
    mentions_area,
    names_organisation,
)

PLACES = ("Testvale", "East Testvale", "Example Road", "Perth")
PAGES = {
    "https://alphadental.test/": "Page title: Alpha Dental Studio\n12 Example Road, Testvale WA.",
    "https://other-alpha.test/": "Page title: Alpha Dental\nAlpha Dental Studio, Melbourne.",
    "https://unrelated.test/": "Page title: Plumbing\nA plumbing business in Testvale.",
    "https://listings.test/": "Page title: Businesses in Testvale\nAlpha Dental, Beta Physio.",
}


@pytest.fixture(autouse=True)
def in_temp_folder(tmp_path, monkeypatch):
    # The default saved-websites file is relative, so keep it out of the real config folder.
    monkeypatch.chdir(tmp_path)


def read(url):
    return PAGES.get(url, "")


def no_pause(seconds):
    pass


def test_distinctive_words_skip_common_ones():
    assert distinctive_words("Alpha Dental Centre") == ["alpha"]
    assert distinctive_words("Testvale Medical Centre & After Hours GP") == ["testvale"]
    assert distinctive_words("Medical Centre") == ["medical", "centre"]


def test_name_must_appear_on_the_page():
    assert names_organisation("Welcome to ALPHA dental", "Alpha Dental Centre")
    assert not names_organisation("Welcome to Beta Dental", "Alpha Dental Centre")
    # Most of a long name is enough.
    assert names_organisation("Green Hill Park physio", "Green Hill Park Bay Physiotherapy")
    assert not names_organisation("Green physio", "Green Hill Park Bay Physiotherapy")


def test_area_must_be_mentioned_as_whole_words():
    assert mentions_area("Find us at 12 Example Road", PLACES)
    assert mentions_area("Based in East Testvale.", PLACES)
    assert not mentions_area("Testvaleside Clinic, Sydney", PLACES)


def test_directories_and_social_media_are_skipped():
    assert is_directory("https://www.facebook.com/alphadental")
    assert is_directory("https://www.hotdoc.com.au/medical-centres/testvale-WA-6100/alpha")
    assert not is_directory("https://alphadental.test/about")


def test_a_working_listed_website_is_kept_without_searching():
    def no_search(query, key):
        raise AssertionError("No search needed.")

    org = Organisation("Alpha Dental", website="https://alphadental.test/contact")
    result = find_website(org, PLACES, "key", search=no_search, read=read)
    assert result.outcome == CHECKED
    assert result.organisation.website == "https://alphadental.test/contact"
    assert result.searches == 0


def test_search_finds_the_site_that_names_the_practice_locally():
    queries = []

    def search(query, key):
        queries.append(query)
        return [
            "https://www.facebook.com/alpha",
            "https://other-alpha.test/home",
            "https://unrelated.test/",
            "https://alphadental.test/services/fillings",
        ]

    org = Organisation("Alpha Dental", suburb="Testvale", website="https://broken.test/")
    result = find_website(org, PLACES, "key", search=search, read=read)
    assert result.outcome == FOUND
    assert result.organisation.website == "https://alphadental.test/"
    assert queries == ['"Alpha Dental" Testvale WA']


def test_nothing_is_guessed_when_no_page_confirms():
    org = Organisation("Alpha Dental")
    result = find_website(org, PLACES, "key", search=lambda q, k: ["https://other-alpha.test/"],
                          read=read)  # fmt: skip
    assert result.outcome == NOT_FOUND
    assert result.organisation.website == ""


def test_only_result_addresses_are_kept(monkeypatch):
    body = (
        b'{"web": {"results": [{"url": "https://alphadental.test/", "title": "Alpha",'
        b' "description": "Dr Jane Example is our dentist"}, {"title": "no url"}]}}'
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, *args):
            return body

    seen = {}

    def fake_urlopen(request, timeout):
        seen["headers"] = dict(request.header_items())
        seen["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert brave_search("Alpha Dental", "secret") == ["https://alphadental.test/"]
    assert seen["headers"]["X-subscription-token"] == "secret"
    assert "country=AU" in seen["url"]


def test_no_key_stops_the_lookup(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with pytest.raises(WebsiteLookupError, match="No search API key"):
        find_websites([Organisation("Alpha Dental")], PLACES)


def test_a_refused_key_stops_the_lookup():
    def refused(query, key):
        raise urllib.error.HTTPError("https://api.test", 401, "Unauthorized", {}, None)

    with pytest.raises(WebsiteLookupError, match="refused the API key"):
        find_websites([Organisation("Alpha Dental")], PLACES, "bad", search=refused, read=read,
                      pause=no_pause)  # fmt: skip


def test_a_failed_search_is_retried_once_then_skipped():
    calls = []

    def flaky(query, key):
        calls.append(query)
        raise urllib.error.URLError("timeout")

    results = find_websites([Organisation("Alpha Dental")], PLACES, "key", search=flaky,
                            read=read, pause=no_pause)  # fmt: skip
    assert len(calls) == 2
    assert results[0].outcome == NOT_FOUND


def test_a_retried_search_can_succeed():
    calls = []

    def flaky(query, key):
        calls.append(query)
        if len(calls) == 1:
            raise urllib.error.URLError("timeout")
        return ["https://alphadental.test/"]

    results = find_websites([Organisation("Alpha Dental")], PLACES, "key", search=flaky,
                            read=read, pause=no_pause)  # fmt: skip
    assert results[0].outcome == FOUND


def test_a_page_listing_many_businesses_is_not_accepted():
    org = Organisation("Alpha Dental", suburb="Testvale")
    result = find_website(org, PLACES, "key", search=lambda q, k: ["https://listings.test/"],
                          read=read)  # fmt: skip
    assert result.outcome == NOT_FOUND


def test_own_site_needs_the_name_in_the_title_or_address():
    assert is_own_site("Alpha Dental Studio", "https://smile.test/", "Alpha Dental", PLACES)
    assert is_own_site("Welcome", "https://www.alphadental.test/", "Alpha Dental", PLACES)
    assert not is_own_site("Businesses in Testvale", "https://list.test/", "Alpha Dental", PLACES)


def test_a_name_of_place_words_must_be_in_the_address():
    name = "Testvale Dental Centre"
    assert is_own_site("Dentist", "https://testvaledental.test/", name, PLACES)
    assert not is_own_site("Dentist Testvale", "https://smiles.test/", name, PLACES)


def test_a_found_website_is_saved_and_reused_without_searching(tmp_path):
    saved = tmp_path / "found.json"
    org = Organisation("Alpha Dental", suburb="Testvale")
    first = find_websites([org], PLACES, "key", search=lambda q, k: ["https://alphadental.test/x"],
                          read=read, pause=no_pause, saved_path=saved)  # fmt: skip
    assert first[0].outcome == FOUND
    assert "https://alphadental.test/" in saved.read_text()

    def no_search(query, key):
        raise AssertionError("The saved website should be reused.")

    second = find_websites([org], PLACES, "key", search=no_search, read=read, pause=no_pause,
                           saved_path=saved)  # fmt: skip
    assert second[0].outcome == SAVED
    assert second[0].organisation.website == "https://alphadental.test/"
    assert second[0].searches == 0


def test_a_saved_website_that_stopped_working_is_searched_again(tmp_path):
    saved = tmp_path / "found.json"
    saved.write_text('{"alpha dental": {"website": "https://gone.test/"}}')
    searched = []

    def search(query, key):
        searched.append(query)
        return ["https://alphadental.test/"]

    results = find_websites([Organisation("Alpha Dental")], PLACES, "key", search=search,
                            read=read, pause=no_pause, saved_path=saved)  # fmt: skip
    assert searched and results[0].outcome == FOUND
    assert "gone.test" not in saved.read_text()


def test_a_damaged_saved_file_is_ignored(tmp_path):
    saved = tmp_path / "found.json"
    saved.write_text("not json")
    results = find_websites([Organisation("Alpha Dental")], PLACES, "key",
                            search=lambda q, k: ["https://alphadental.test/"], read=read,
                            pause=no_pause, saved_path=saved)  # fmt: skip
    assert results[0].outcome == FOUND
