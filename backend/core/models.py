"""Shared validation model bases without HTTP or persistence dependencies."""

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FiniteStrict(Strict):
    model_config = ConfigDict(allow_inf_nan=False)
