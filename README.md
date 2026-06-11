# Local Skills Manager

一个简单的本地可视化工具：

1. 配置一个存放所有 Skills 项目的中央目录。
2. 只读取中央目录下的一级文件夹，不扫描项目内部。
3. 在浏览器中勾选项目，将完整文件夹软链接到 Codex 或 Claude Code。

默认目标目录：

```text
Codex        ~/.codex/skills
Claude Code  ~/.claude/skills
```

## 安装与启动

要求 Python 3.10 或更高版本。

```bash
python3 -m pip install -e .
skills-manager serve
```

浏览器会自动打开：

```text
http://127.0.0.1:8765
```

也可以不自动打开浏览器：

```bash
skills-manager serve --no-browser
```

默认使用以下状态文件：

```text
~/skills-manager-state.json
```

其中保存中央目录路径和由 Manager 创建的软链接记录。也可以在页面中切换到其他
状态文件。

首次打开后，填写中央目录，例如：

```text
~/Documents/skills-library
```

页面会列出其中所有一级文件夹，并为 Codex、Claude Code 分别显示一个开关。

## 行为与安全边界

- 启用项目时，仅创建目录软链接，不复制文件。
- 目标位置存在同名文件、目录或其他软链接时，显示冲突且不会覆盖。
- 停用时，只删除由 Manager 记录、且仍指向对应中央项目的软链接。
- Manager 不读取一级项目文件夹内部的内容。
- 切换中央目录前，需要先停用当前目录中的所有项目。
- 默认状态文件为 `~/skills-manager-state.json`，可通过页面或 `--state-file` 覆盖。

## 命令行辅助操作

```bash
skills-manager init ~/Documents/skills-library
skills-manager list
skills-manager status
skills-manager enable Idea-Copilot --agent codex
skills-manager disable Idea-Copilot --agent codex
```

需要使用其他状态文件时，在子命令前传入：

```bash
skills-manager --state-file /path/to/state.json status
```

## 开发验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
