from pydantic import BaseModel, ConfigDict, Field

ENERGY_UNIT_PATTERN = r"^(l|kWh)$"


class CarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    plate: str | None = Field(default=None, max_length=20)
    start_odometer_km: int = Field(ge=0, le=5_000_000)
    energy_unit: str = Field(default="l", pattern=ENERGY_UNIT_PATTERN)


class CarUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    plate: str | None = Field(default=None, max_length=20)
    start_odometer_km: int = Field(ge=0, le=5_000_000)
    energy_unit: str = Field(default="l", pattern=ENERGY_UNIT_PATTERN)
    archived: bool = False


class CarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    plate: str | None
    start_odometer_km: int
    energy_unit: str
    archived: bool
    last_km: int
    open_trip_id: int | None
