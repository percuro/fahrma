from datetime import date, datetime

from pydantic import BaseModel, Field

# One text, or one per language ({"de": "Gratis", "en": "Free"})
PlanName = str | dict[str, str]


class PlanInfo(BaseModel):
    id: str
    name: PlanName
    # None = unlimited
    members_per_group: int | None
    cars_per_group: int | None


class PlanUsage(BaseModel):
    members_per_group: int
    cars_per_group: int


class GroupPlanRead(PlanInfo):
    """The plan in force for a group, as its members see it."""

    # Last day of the group's own plan; None = no end (or the default plan)
    until: date | None = None
    usage: PlanUsage


class PlanUpdate(BaseModel):
    """Replaces a group's plan. plan null = the default plan."""

    plan: str | None = Field(default=None, max_length=32)
    # Last day the plan is valid, inclusive; null = until changed again
    until: date | None = None
    note: str | None = Field(default=None, max_length=200)


class GroupAdminRef(BaseModel):
    user_id: int
    display_name: str


class OperatorGroupRead(BaseModel):
    """What instance admins and the operator API see about a group: no entries, no amounts."""

    id: int
    name: str
    created_at: datetime
    # Latest change recorded in the group's audit log
    last_activity_at: datetime | None
    # The group's own plan as stored (may have run out, see effective_plan)
    plan: str | None
    plan_until: date | None
    plan_note: str | None
    effective_plan: str
    usage: PlanUsage
    admins: list[GroupAdminRef]


class BillingLink(BaseModel):
    url: str


class BillingTokenCheck(BaseModel):
    token: str = Field(min_length=1, max_length=1000)


class BillingUser(BaseModel):
    user_id: int
    display_name: str
    # Confirmed address, if any; for the invoice
    email: str | None
    locale: str | None


class BillingTokenRead(BaseModel):
    group: OperatorGroupRead
    user: BillingUser
    expires_at: datetime
