from __future__ import annotations

from sqlmodel import Session, select

from .models import Category, Keyword, KeywordGroup

DEFAULT_CATEGORIES = ["cs.RO", "cs.CV", "cs.LG", "cs.AI", "eess.SY"]

DEFAULT_KEYWORD_GROUPS = [
    {
        "name": "Embodied Intelligence",
        "weight": 3.0,
        "include": [
            "embodied intelligence",
            "embodied ai",
            "embodied agent",
            "embodied agents",
            "embodied learning",
            "embodiment",
        ],
        "exclude": ["disembodied"],
    },
    {
        "name": "Robotics Core",
        "weight": 2.5,
        "include": [
            "robotics",
            "robot",
            "robotic",
            "robot learning",
            "manipulation",
            "mobile manipulation",
            "dexterous",
            "humanoid",
            "locomotion",
            "navigation",
        ],
        "exclude": ["chatbot", "botnet", "web robot", "software robot"],
    },
    {
        "name": "VLA and Robot Foundation Models",
        "weight": 3.5,
        "include": [
            "vision-language-action",
            "vision language action",
            "vla",
            "robot foundation model",
            "robot policy",
            "action model",
            "generalist robot",
            "multimodal policy",
        ],
        "exclude": [],
    },
    {
        "name": "Datasets and Benchmarks",
        "weight": 2.2,
        "include": [
            "robot dataset",
            "robotics dataset",
            "embodied dataset",
            "benchmark",
            "evaluation suite",
            "simulation benchmark",
            "real-world dataset",
        ],
        "exclude": [],
    },
    {
        "name": "World Models and Data Loop",
        "weight": 2.8,
        "include": [
            "world model",
            "world models",
            "data engine",
            "data closed loop",
            "closed-loop data",
            "data flywheel",
            "synthetic data",
            "sim-to-real",
            "digital twin",
        ],
        "exclude": [],
    },
    {
        "name": "First Person and UMI",
        "weight": 3.0,
        "include": [
            "umi",
            "universal manipulation interface",
            "egocentric",
            "first-person",
            "first person",
            "wearable",
            "teleoperation",
            "imitation learning",
        ],
        "exclude": [],
    },
    {
        "name": "Robot Body and Hardware",
        "weight": 2.4,
        "include": [
            "robot body",
            "morphology",
            "gripper",
            "dexterous hand",
            "whole-body",
            "whole body",
            "bimanual",
            "end-effector",
        ],
        "exclude": [],
    },
]


def init_default_config(session: Session) -> None:
    for code in DEFAULT_CATEGORIES:
        existing = session.exec(select(Category).where(Category.code == code)).first()
        if existing is None:
            session.add(Category(code=code, enabled=True))

    for group_data in DEFAULT_KEYWORD_GROUPS:
        group = session.exec(select(KeywordGroup).where(KeywordGroup.name == group_data["name"])).first()
        if group is None:
            group = KeywordGroup(name=group_data["name"], weight=float(group_data["weight"]), enabled=True)
            session.add(group)
            session.flush()
        for kind in ("include", "exclude"):
            for value in group_data[kind]:
                existing = session.exec(
                    select(Keyword).where(
                        Keyword.group_id == group.id,
                        Keyword.kind == kind,
                        Keyword.value == value,
                    )
                ).first()
                if existing is None:
                    session.add(Keyword(group_id=group.id, kind=kind, value=value, enabled=True))

    session.commit()

