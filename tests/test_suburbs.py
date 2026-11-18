"""Tests for choosing a run's suburbs. Every place and point here is made up."""

import pytest

from org_research_agent.suburbs import (
    Place,
    PlaceSearchError,
    build_selection,
    choose_suburbs,
    locate_suburb,
    parse_others,
    suburb_key,
    tidy_name,
)

USUAL = ("Victoria Park", "East Victoria Park")
CENTRE = (-31.980, 115.902)
PLACES = {
    "victoria park": Place("Victoria Park", (-31.972, 115.895)),
    "east victoria park": Place("East Victoria Park", (-31.988, 115.903)),
    "bentley": Place("Bentley", (-32.008, 115.906)),
    "carlisle": Place("Carlisle", (-31.980, 115.917)),
}


def fake_locate(name):
    return PLACES.get(name.lower())


def no_pause(seconds):
    pass


class FakeWindow:
    """Plays back answers, and records the messages it was asked to show."""

    def __init__(self, answers, confirms=()):
        self.answers = list(answers)
        self.confirms = list(confirms)
        self.warnings = []
        self.questions = []
        self.asked = 0

    def ask(self):
        self.asked += 1
        return self.answers.pop(0)

    def warn(self, message):
        self.warnings.append(message)

    def confirm(self, message):
        self.questions.append(message)
        return self.confirms.pop(0)

    def busy(self, busy):
        pass


def choose(window, locate=fake_locate):
    return choose_suburbs(USUAL, CENTRE, window, locate, no_pause)


def test_others_split_on_commas_with_or_without_spaces():
    assert parse_others("Bentley,Carlisle") == ["Bentley", "Carlisle"]
    assert parse_others(" Bentley ,  St   James,,bentley ") == ["Bentley", "St James"]
    assert parse_others("") == []


def test_both_usual_suburbs_keep_the_usual_map_centre():
    selection = choose(FakeWindow([(list(USUAL), "")]))
    assert selection.suburbs == USUAL
    assert selection.centres == (CENTRE,)
    assert selection.is_usual and selection.includes_usual


def test_cancel_returns_nothing():
    assert choose(FakeWindow([None])) is None


def test_one_usual_suburb_uses_its_own_centre():
    selection = choose(FakeWindow([(["East Victoria Park"], "")]))
    assert selection.suburbs == ("East Victoria Park",)
    assert selection.centres == (PLACES["east victoria park"].centre,)
    assert selection.includes_usual and not selection.is_usual


def test_typed_suburbs_are_added_with_their_own_map_centres():
    selection = choose(FakeWindow([(list(USUAL), "bentley,Carlisle")]))
    assert selection.suburbs == (*USUAL, "Bentley", "Carlisle")
    assert selection.centres == (CENTRE, PLACES["bentley"].centre, PLACES["carlisle"].centre)
    assert not selection.is_usual


def test_only_typed_suburbs_leave_out_the_usual_area():
    selection = choose(FakeWindow([([], "Bentley")]))
    assert selection.suburbs == ("Bentley",)
    assert selection.centres == (PLACES["bentley"].centre,)
    assert not selection.includes_usual


def test_typing_a_usual_suburb_asks_to_change_it_and_shows_the_window_again():
    window = FakeWindow([(list(USUAL), "victoria park,Bentley"), (list(USUAL), "Bentley")])
    selection = choose(window)
    assert window.asked == 2
    assert "Victoria Park is already in the tickboxes" in window.warnings[0]
    assert selection.suburbs == (*USUAL, "Bentley")


def test_nothing_chosen_asks_again():
    window = FakeWindow([([], "  "), (["Victoria Park"], "")])
    assert choose(window).suburbs == ("Victoria Park",)
    assert window.warnings == ["Please tick a suburb or type one in Others."]


def test_a_suburb_not_in_perth_can_still_be_searched_after_a_warning():
    window = FakeWindow([(list(USUAL), "Bentlee")], confirms=[True])
    selection = choose(window)
    assert "Bentlee wasn't found in Perth" in window.questions[0]
    assert selection.suburbs == (*USUAL, "Bentlee")
    assert selection.centres == (CENTRE,)
    assert selection.not_found == ("Bentlee",)


def test_saying_no_to_an_unknown_suburb_shows_the_window_again():
    window = FakeWindow([(list(USUAL), "Bentlee"), (list(USUAL), "Bentley")], confirms=[False])
    assert choose(window).suburbs == (*USUAL, "Bentley")
    assert window.asked == 2


def test_no_internet_asks_before_searching_unchecked_suburbs():
    def offline(name):
        raise PlaceSearchError("offline")

    window = FakeWindow([(list(USUAL), "Bentley")], confirms=[True])
    selection = choose(window, locate=offline)
    assert "couldn't be checked just now" in window.questions[0]
    assert selection.suburbs == (*USUAL, "Bentley")


def test_a_usual_suburb_not_found_falls_back_to_the_usual_centre():
    selection = build_selection(USUAL, CENTRE, ["Victoria Park"], [], lambda n: None, no_pause)
    assert selection.centres == (CENTRE,)


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ([{"name": "Bentley", "lat": "-32.008", "lon": "115.906"}], "Bentley"),
        # The same name outside Perth isn't accepted.
        ([{"name": "Bentley", "lat": "-17.9", "lon": "122.2"}], None),
        # A different place that only looks similar isn't accepted.
        ([{"name": "Bentley Park", "lat": "-32.0", "lon": "115.9"}], None),
        ([], None),
    ],
)
def test_locate_accepts_only_the_same_name_inside_perth(results, expected):
    place = locate_suburb("bentley", fetch=lambda name: results)
    assert (place.name if place else None) == expected


# Typed names: short forms, punctuation, and extras.


@pytest.mark.parametrize(
    ("typed", "tidied"),
    [
        ("st. james", "St James"),
        ("Saint James", "St James"),
        ("mt lawley", "Mount Lawley"),
        ("MT. LAWLEY", "Mount Lawley"),
        ("Nth Perth", "North Perth"),
        ("s perth", "South Perth"),
        ("e vic park", "East Victoria Park"),
        ("o\u2019connor", "O'Connor"),
        ("McKenzie", "McKenzie"),
        ("Perth", "Perth"),
    ],
)
def test_typed_names_are_tidied_to_the_official_form(typed, tidied):
    assert tidy_name(typed) == tidied


def test_keys_ignore_case_full_stops_apostrophes_and_short_forms():
    assert suburb_key("St. James") == suburb_key("saint james") == suburb_key("ST JAMES")
    assert suburb_key("OConnor") == suburb_key("O'Connor")
    assert suburb_key("Vic Park") == suburb_key("Victoria Park")
    assert suburb_key("Bentley") != suburb_key("Bentley Park")


def test_others_drop_states_postcodes_and_repeats_and_accept_other_separators():
    typed = "Subiaco, St. James; Bentley WA 6102/ wa ,6000, st james\nMt Lawley,"
    assert parse_others(typed) == ["Subiaco", "St James", "Bentley", "Mount Lawley"]


def test_a_short_form_of_a_usual_suburb_asks_to_use_the_tickbox():
    window = FakeWindow([(["Victoria Park"], "E Vic Park"), (list(USUAL), "")])
    choose(window)
    assert "East Victoria Park is already in the tickboxes" in window.warnings[0]


def test_many_typed_suburbs_ask_first():
    many = ",".join(["Bentley", "Carlisle", "A", "B", "C", "D"])
    window = FakeWindow([(list(USUAL), many), (list(USUAL), "Bentley")], confirms=[False])
    assert choose(window).suburbs == (*USUAL, "Bentley")
    assert "You've added 6 suburbs" in window.questions[0]


def test_two_typed_names_for_one_place_are_kept_once():
    places = {"mount lawley": Place("Mount Lawley", (-31.93, 115.87))}
    window = FakeWindow([(list(USUAL), "Mount Lawley,Mt. Lawley")])
    selection = choose(window, locate=lambda name: places.get(name.lower()))
    assert selection.suburbs == (*USUAL, "Mount Lawley")


def test_locate_matches_the_official_name_from_a_short_form():
    results = [{"name": "St James", "lat": "-32.003", "lon": "115.911"}]
    place = locate_suburb("st. james", fetch=lambda name: results)
    assert place.name == "St James"


def test_each_map_centre_is_labelled_with_its_suburbs():
    usual = build_selection(USUAL, CENTRE, list(USUAL), [PLACES["bentley"]], fake_locate)
    assert usual.centre_labels == ("Victoria Park and East Victoria Park", "Bentley")
    one = build_selection(USUAL, CENTRE, ["Victoria Park"], [], fake_locate, no_pause)
    assert one.centre_labels == ("Victoria Park",)
