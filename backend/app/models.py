"""Pydantic contracts shared by the API and domain services."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ResolutionStatus = Literal["resolved", "unresolved", "unsupported"]
InteractionStatus = Literal[
    "contraindicated",
    "caution",
    "not_listed",
    "unresolved",
    "unsupported",
    "system_error",
]
InputName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
DrugId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_-]+$"),
]


class WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResolveRequest(WriteModel):
    text: str | None = Field(default=None, max_length=4000)
    inputs: list[InputName] | None = Field(default=None, max_length=20)
    use_llm: bool = False

    @model_validator(mode="after")
    def require_input(self) -> "ResolveRequest":
        if not self.text and not self.inputs:
            raise ValueError("text または inputs が必要です")
        return self


class DrugCandidate(BaseModel):
    drug_id: str
    display_name: str
    generic_name: str | None
    category: Literal["prescription", "otc", "ingredient"]
    score: float = Field(ge=0, le=100)


class ResolutionItem(BaseModel):
    input_name: str
    normalized_input: str
    status: ResolutionStatus
    selected: DrugCandidate | None = None
    candidates: list[DrugCandidate] = Field(default_factory=list)
    llm_used: bool = False
    message: str | None = None


class ResolveResponse(BaseModel):
    items: list[ResolutionItem] = Field(default_factory=list)


class CheckItem(WriteModel):
    input_name: InputName
    drug_id: DrugId


class CheckRequest(WriteModel):
    items: list[CheckItem] = Field(min_length=1, max_length=20)
    target_id: DrugId = "clarithromycin"


class TargetDrug(BaseModel):
    id: str
    rank: int
    label: str
    group_label: str
    is_default: bool


class IngredientResult(BaseModel):
    drug_id: str
    generic_name: str
    status: InteractionStatus
    effect: str | None = None
    mechanism: str | None = None
    action: str | None = None
    evidence_url: str | None = None
    source_url: str | None = None
    source_section: str | None = None
    source_revision: str | None = None


class CheckResult(BaseModel):
    input_name: str
    drug_id: str
    display_name: str
    generic_name: str | None
    category: Literal["prescription", "otc", "ingredient"]
    ingredients: list[str]
    status: InteractionStatus
    effect: str
    mechanism: str
    action: str
    evidence_url: str | None = None
    source_url: str | None
    source_section: str | None = None
    source_revision: str | None
    dataset_updated_at: str
    ingredient_results: list[IngredientResult] = Field(default_factory=list)
    target_id: str = "clarithromycin"
    target_name: str = "クラリスロマイシン"


class CheckResponse(BaseModel):
    results: list[CheckResult]
    disclaimer: str
