# Local Skills Manager

一个简单的本地可视化工具：

1. 配置一个存放所有 Skills 项目的中央目录。
2. 首页读取中央目录下的一级文件夹，展开项目时按需查找其中的 `SKILL.md`。
3. 在浏览器中勾选项目，将完整文件夹软链接到 Codex 或 Claude Code。
4. 为项目添加标签，并通过项目名、标签或已展开的 Skill 搜索筛选。
5. 进入批量选择模式，为多个项目统一添加或移除标签。
6. 从项目卡片或 Skill 列表直接在系统文件管理器中打开对应文件夹。

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

更新项目代码后，需要停止并重新运行 `skills-manager serve`，后端接口才会加载新版本。

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

页面会将其中所有一级文件夹显示为项目卡片，并为 Codex、Claude Code 分别显示一个
开关。展开卡片后，可以查看项目中包含的 Skills，并通过标签选择器编辑项目标签：
已有标签可以直接点击添加，当前标签可以单独移除，也可以创建新标签。
点击筛选栏右侧的“批量选择”后，项目卡片才会显示复选框；选择多个项目后，可以
一次添加或移除多个标签，且不会覆盖各项目原有的其他标签。
项目标题和每个 Skill 行均提供打开对应文件夹的按钮。

## 行为与安全边界

- 启用项目时，仅创建目录软链接，不复制文件。
- 目标位置存在同名文件、目录或其他软链接时，显示冲突且不会覆盖。
- 停用时，只删除由 Manager 记录、且仍指向对应中央项目的软链接。
- 首页不会扫描项目内部；展开项目时只查找 `SKILL.md` 路径，不读取文件内容。
- 切换中央目录前，需要先停用当前目录中的所有项目。
- 默认状态文件为 `~/skills-manager-state.json`，可通过页面或 `--state-file` 覆盖。
- 项目标签保存在状态文件中，切换中央目录时会清空原目录的标签。
- 打开文件夹功能只允许打开当前中央目录中的项目或已扫描到的 Skill 目录。

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
