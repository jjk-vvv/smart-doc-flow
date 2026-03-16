from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jSettings":
        return cls(
            uri=str(os.getenv("MODULE4_NEO4J_URI", os.getenv("NEO4J_URI", "")) or "").strip(),
            username=str(os.getenv("MODULE4_NEO4J_USERNAME", os.getenv("NEO4J_USERNAME", "")) or "").strip(),
            password=str(os.getenv("MODULE4_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "")) or "").strip(),
            database=str(os.getenv("MODULE4_NEO4J_DATABASE", os.getenv("NEO4J_DATABASE", "neo4j")) or "neo4j").strip()
            or "neo4j",
        )

    def is_configured(self) -> bool:
        return bool(self.uri and self.username and self.password)

    def missing_fields(self) -> List[str]:
        missing: List[str] = []
        if not self.uri:
            missing.append("MODULE4_NEO4J_URI")
        if not self.username:
            missing.append("MODULE4_NEO4J_USERNAME")
        if not self.password:
            missing.append("MODULE4_NEO4J_PASSWORD")
        return missing

    def workspace_env(self) -> Dict[str, str]:
        values = {
            "NEO4J_URI": self.uri,
            "NEO4J_USERNAME": self.username,
            "NEO4J_PASSWORD": self.password,
            "NEO4J_DATABASE": self.database,
        }
        return {key: value for key, value in values.items() if value}
