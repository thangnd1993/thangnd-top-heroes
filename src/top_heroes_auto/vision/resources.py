import sys
from pathlib import Path


def template_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / "templates"
    return Path(__file__).resolve().parents[3] / "assets" / "templates"


def idle_reward_template_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets" / "tasks" / "idle_reward"
    return Path(__file__).resolve().parents[3] / "assets" / "tasks" / "idle_reward"
