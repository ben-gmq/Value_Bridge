"""The `vb-process-flow/2.0` file (design §7.2b, slice 1e-b spec §4 rule 1). One strict definition: the import
checks a file with it and the published JSON Schema is generated from it (`model_json_schema()`), so the two cannot
disagree (spec §2). Every object refuses unknown keys, so `edges` and `lanes` (D-38) and a 1.0 file are refused.
Performer and trigger kinds are code-defined vocabularies (services/bfc.PERFORMER_KINDS, services/trigger.KINDS),
not code_master lists; a party's kind is an EXTERNAL_ENTITY_KIND code, checked against the project's list at import."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from schemas.process_flow import TriggerKind

FORMAT = "vb-process-flow/2.0"
MAX_LIST = 100                     # triggers, inputs, outputs or external flows of one step
MAX_PARTIES = 200

Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,40}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Ref = Annotated[str, StringConstraints(max_length=200)]
DeRef = Annotated[str, StringConstraints(min_length=1, max_length=200)]     # `DE-nnnn`, or a data entity's name


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Parent(_Strict):
    hier_code: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    name: Name | None = None


class CodedPerformer(_Strict):
    kind: Literal["ORG_UNIT", "ORG_ROLE", "APPLICATION"]
    code: Annotated[str, StringConstraints(min_length=1, max_length=30)]


class AiPerformer(_Strict):
    kind: Literal["AI"]
    label: Name


class Trigger(_Strict):
    name: Name
    kind: TriggerKind


class ExternalFlow(_Strict):
    external: Key = Field(description="The `key` of an entry in `external_entities`.")
    direction: Literal["I", "O"]
    data_entity: DeRef | None = None


class ExternalEntity(_Strict):
    key: Key
    ext_number: Annotated[str, StringConstraints(max_length=20)] | None = None
    name: Name
    kind: Annotated[str, StringConstraints(max_length=40)] | None = None


class Step(_Strict):
    key: Key
    br_number: Annotated[str, StringConstraints(max_length=20)] | None = None
    hier_code: Annotated[str, StringConstraints(max_length=40)] | None = None
    row_version: Annotated[int, Field(ge=1)] | None = None
    name: Name
    description: Annotated[str, StringConstraints(max_length=4000)] | None = Field(None, description="Left out: kept as it is. \"\" or null: cleared (FI-8).")
    performer: Annotated[CodedPerformer | AiPerformer, Field(discriminator="kind")] | None = Field(
        None, description="Left out, or an unknown code: kept as it is. null: cleared (FI-2).")
    triggers: Annotated[list[Trigger], Field(max_length=MAX_LIST)] | None = Field(
        None, description="Left out or null: kept as they are. [] means none (FI-1).")
    inputs: Annotated[list[DeRef], Field(max_length=MAX_LIST)] | None = Field(
        None, description="Left out or null: kept as they are. [] means none (FI-1).")
    outputs: Annotated[list[DeRef], Field(max_length=MAX_LIST)] | None = Field(
        None, description="Left out or null: kept as they are. [] means none (FI-1).")
    external_flows: Annotated[list[ExternalFlow], Field(max_length=MAX_LIST)] | None = Field(
        None, description="Left out or null: kept as they are. An import never removes an external flow.")
    source_ref: Ref | None = None


class FlowFile(_Strict):
    model_config = ConfigDict(extra="forbid", title="vb-process-flow/2.0")

    format: Literal["vb-process-flow/2.0"]
    parent: Parent
    mode: Literal["merge", "replace"] = "merge"
    external_entities: Annotated[list[ExternalEntity], Field(max_length=MAX_PARTIES)] = []
    # A node holds at most 99 children (bfc.MAX_SIBLINGS), so a file never needs more steps (§7.12a limits).
    steps: Annotated[list[Step], Field(min_length=1, max_length=99)]


def json_schema() -> dict:
    return FlowFile.model_json_schema()
