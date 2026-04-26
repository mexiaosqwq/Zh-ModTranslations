# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Minecraft 模组汉化资源包仓库（1.20.1+ / 1.21.1+ NeoForge）。

## 仓库结构

```
Zh-ModTranslations/
├── assets/<modid>/lang/zh_cn.json   # 翻译输出文件（git 跟踪）
├── pack.mcmeta                       # 资源包定义 (pack_format: 32)
├── .github/workflows/
│   ├── claude.yml                    # @claude 触发：Issues/PR 评论交互
│   └── claude-code-review.yml        # PR 打开/同步时自动 Code Review
│
└── 汉化/ (gitignored)                # 翻译工作流（本地专用）
    ├── CLAUDE.md                     # 完整汉化工作指南
    ├── mods/                         # 待翻译的模组 JAR
    ├── langs/                        # 参考包
    ├── data/                         # 提取的原始语言文件
    └── bin/translation_toolkit.py    # 翻译工具 v11.0
```

## 翻译文件规范

- 每个模组一个 `zh_cn.json`，路径 `assets/<modid>/lang/zh_cn.json`
- JSON 格式：扁平键值对，`{ "key.mod.x": "译名" }`
- 译名需与 MC百科/Modrinth 确认一致
- 已汉化 21 个模组，详见 README.md

## GitHub Actions

- **claude.yml** — 在 Issue/PR 评论中 `@claude` 时触发，Claude 可执行任务
- **claude-code-review.yml** — 每次 PR 打开或同步时自动审查代码质量

> **注意**：`汉化/` 目录包含大型二进制文件（JAR）和私有工作数据，不纳入 Git。
> 需要翻译工具链请联系仓库维护者获取，或直接编辑 `assets/<modid>/lang/zh_cn.json` 参与翻译改进。

## 常用命令

```bash
# 单模组翻译流程
# ① 查询模组背景（使用 Skill 工具：skill="mc-search", args="search <模组名> -n 3"）
python3 汉化/bin/translation_toolkit.py make-pending 汉化/mods/<mod>.jar --modid <modid>
python3 汉化/bin/translation_toolkit.py sync-lang <modid>
# → AI 翻译完成后 → 人工审校：
#   审校清单：
#   [ ] 译名语义正确，贴合模组上下文
#   [ ] 与 MC百科/Modrinth 等源确认物品/方块名称
#   [ ] 格式符（%s, %d, §a, \n 等）完整保留
#   [ ] 术语与同系列模组一致
#   [ ] 无遗漏或多余键
python3 汉化/bin/translation_toolkit.py import-rp <资源包路径> <modid>

# 批量处理
python3 汉化/bin/translation_toolkit.py batch-make-pending
python3 汉化/bin/translation_toolkit.py batch-sync-lang

# Git 操作
git add assets/<modid>/lang/zh_cn.json pack.mcmeta  # 只提交翻译文件
git commit -m "feat: 添加/更新 <模组名> 汉化"
```

## Git 注意事项

- 只提交 `assets/` 和 `pack.mcmeta`，不提交 `汉化/` 目录（已在 `.gitignore` 中排除）
- 提交时不要带上 `.claude/`、`runs/`、`__pycache__/` 等
