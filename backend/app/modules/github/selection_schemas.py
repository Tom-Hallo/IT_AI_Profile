from typing import Literal

from pydantic import BaseModel, Field

Scope = Literal["public", "private", "combined"]


class SelectionUpdate(BaseModel):
    scope: Scope
    repository_ids: list[int] = Field(default_factory=list, max_length=500)


class SelectionResponse(SelectionUpdate):
    pass


class RepoOption(BaseModel):
    id: int
    full_name: str
    private: bool
    html_url: str


class OptionsResponse(BaseModel):
    scope: Scope
    items: list[RepoOption]
    private_access_granted: bool
