"""Pydantic 数据模型"""
from pydantic import BaseModel
from typing import Optional


class SnapshotCreate(BaseModel):
    name: Optional[str] = None
    drive: Optional[str] = "C:\\"
