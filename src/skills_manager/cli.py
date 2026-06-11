from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .core import (
    AGENT_LABELS,
    DEFAULT_STATE_FILE,
    SkillsManager,
    SkillsManagerError,
    StateStore,
)
from .web import serve


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="skills-manager",
        description="通过软链接将中央目录的一级文件夹启用到 Codex 或 Claude Code。",
    )
    result.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help="状态文件路径，默认使用 ~/skills-manager-state.json",
    )
    commands = result.add_subparsers(dest="command", required=True)

    web = commands.add_parser("serve", help="启动本地可视化管理页面")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true", help="启动时不自动打开浏览器")

    init = commands.add_parser("init", help="配置 Skills 中央目录")
    init.add_argument("library", type=Path)

    commands.add_parser("list", help="列出中央目录中的一级文件夹")
    commands.add_parser("status", help="显示所有项目的启用状态")

    for name, help_text in [("enable", "启用项目"), ("disable", "停用项目")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("project")
        command.add_argument("--agent", choices=AGENT_LABELS, required=True)
    return result


def run(arguments: argparse.Namespace) -> int:
    if arguments.command == "serve":
        serve(
            state_file=arguments.state_file,
            host=arguments.host,
            port=arguments.port,
            open_browser=not arguments.no_browser,
        )
        return 0

    manager = SkillsManager(StateStore(arguments.state_file))
    if arguments.command == "init":
        print(f"Skills 中央目录已配置: {manager.set_library(arguments.library)}")
    elif arguments.command == "list":
        for project in manager.projects():
            print(project.name)
    elif arguments.command == "status":
        dashboard = manager.dashboard()
        if dashboard["error"]:
            raise SkillsManagerError(dashboard["error"])
        for project in dashboard["projects"]:
            states = "  ".join(
                f"{AGENT_LABELS[agent]}={project['agents'][agent]['state']}"
                for agent in AGENT_LABELS
            )
            print(f"{project['name']}: {states}")
    elif arguments.command == "enable":
        print(f"已启用: {manager.enable(arguments.project, arguments.agent)}")
    else:
        print(f"已停用: {manager.disable(arguments.project, arguments.agent)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except SkillsManagerError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"文件系统错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
