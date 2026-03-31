from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    code: str | None = Field(default=None, max_length=30)
    name: str = Field(min_length=2, max_length=120)
    entry_kind: str = Field(default="expense", max_length=20)
    report_group: str | None = Field(default=None, max_length=120)
    report_subgroup: str | None = Field(default=None, max_length=120)
    is_financial_expense: bool = False
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryRead(CategoryBase):
    id: str
    company_id: str
    entry_count: int = 0

    model_config = {"from_attributes": True}


class CategoryGroupOption(BaseModel):
    name: str
    entry_kind: str


class CategorySubgroupOption(BaseModel):
    name: str
    entry_kind: str
    report_group: str


class CategoryLookups(BaseModel):
    group_options: list[CategoryGroupOption]
    subgroup_options: list[CategorySubgroupOption]
