from abc import ABC, abstractmethod
from typing import Any, List
from pydantic import BaseModel


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]


class BaseTool(ABC):
    @abstractmethod
    def get_info(self) -> ToolInfo:
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass