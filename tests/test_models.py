import pytest
from dailydevfinds.models import Candidate, Source


def test_candidate_normalized_url():
    candidate = Candidate(
        id="test-1",
        title="Test Tool",
        url="https://example.com/path/",
        source=Source.GITHUB,
        source_score=100,
    )
    assert candidate.normalized_url() == "https://example.com/path"


def test_candidate_normalized_url_no_trailing_slash():
    candidate = Candidate(
        id="test-2",
        title="Test Tool 2",
        url="https://example.com/path",
        source=Source.HACKERNEWS,
        source_score=50,
    )
    assert candidate.normalized_url() == "https://example.com/path"


def test_source_enum_values():
    assert Source.HACKERNEWS.value == "hackernews"
    assert Source.GITHUB.value == "github"
    assert Source.PRODUCTHUNT.value == "producthunt"
    assert Source.DEVTO.value == "devto"
    assert Source.REDDIT.value == "reddit"