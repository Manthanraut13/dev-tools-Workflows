from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Source(StrEnum):
    HACKERNEWS = "hackernews"
    GITHUB = "github"
    PRODUCTHUNT = "producthunt"
    DEVTO = "devto"
    REDDIT = "reddit"


class Candidate(BaseModel):
    id: str = Field(..., description="Unique identifier (URL or source-specific ID)")
    title: str = Field(..., min_length=1, max_length=200)
    url: HttpUrl
    source: Source
    source_score: float = Field(..., ge=0, description="Source-specific score (stars, points, votes, etc.)")
    description: str | None = Field(None, max_length=500)
    github_url: HttpUrl | None = None
    author: str | None = None
    created_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)

    def normalized_url(self) -> str:
        return str(self.url).rstrip("/").lower()


class RankResult(BaseModel):
    pick_id: str = Field(..., description="ID of the chosen candidate")
    reason: str = Field(..., min_length=10, max_length=500, description="Why this was picked")
    runner_ups: list[str] = Field(..., min_length=2, max_length=2, description="IDs of 2 runner-up candidates")


class FactsBundle(BaseModel):
    name: str
    what_it_does: str
    key_features: list[str] = Field(default_factory=list)
    license: str | None = None
    pricing: str | None = None
    stars: int | None = None
    language: str | None = None
    website_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    raw_content: str = Field(..., description="Raw scraped content for LLM context")


class Post(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    hashtags: list[str] = Field(..., min_length=3, max_length=5)
    emoji_count: int = Field(..., ge=0, le=3)
    primary_link: HttpUrl
    github_link: HttpUrl | None = None
    image_path: str | None = None

    @field_validator("text")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        word_count = len(v.split())
        if word_count < 90:
            raise ValueError(f"Post must have at least 90 words, got {word_count}")
        if word_count > 150:
            raise ValueError(f"Post must have at most 150 words, got {word_count}")
        return v

    def full_text(self) -> str:
        tags = " ".join(f"#{tag}" for tag in self.hashtags)
        return f"{self.text}\n\n{tags}"


class EmailContent(BaseModel):
    subject: str
    html_body: str
    text_body: str
    image_cid: str
    image_path: str
    runner_ups_text: str
    reason: str
