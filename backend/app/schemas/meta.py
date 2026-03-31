from pydantic import BaseModel


class ModuleCard(BaseModel):
    key: str
    title: str
    description: str
    status: str


class DataSource(BaseModel):
    name: str
    purpose: str
    owner: str


class ProjectOverview(BaseModel):
    stack: list[str]
    modules: list[ModuleCard]
    data_sources: list[DataSource]


class InstanceInfo(BaseModel):
    app: str
    api: str
    app_mode: str
    auth_mode: str
    backup_mode: str
    database_backend: str
    mfa_required: bool
    purchase_planning_enabled: bool
    features: list[str]


class ClientErrorLogCreate(BaseModel):
    source: str
    message: str
    path: str | None = None
    method: str | None = None
    status_code: int | None = None
    request_url: str | None = None
    api_base: str | None = None
    details: str | None = None
    screen: str | None = None
    user_agent: str | None = None
