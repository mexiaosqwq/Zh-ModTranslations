# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Minecraft 模组汉化资源包仓库（1.20.1+ / 1.21.1+ NeoForge），已汉化 33 个模组、2630 条翻译。

## 仓库结构

```
Zh-ModTranslations/
├── assets/<modid>/lang/zh_cn.json   # 翻译输出（git 跟踪）
├── pack.mcmeta                       # 资源包定义 (pack_format: 32)
├── .github/workflows/
│   ├── claude.yml                    # @claude 触发：Issues/PR 评论交互
│   └── claude-code-review.yml        # PR 打开/同步时自动审查翻译质量
│
└── 汉化/ (gitignored)                # 翻译工作流（本地专用）
    ├── CLAUDE.md                     # ★ 唯一权威汉化指南，所有翻译问题查它
    ├── mods/                         # 待翻译模组 JAR
    ├── langs/                        # 参考包 + 工作文件 + mod_context.json
    ├── data/                         # 提取的原始语言文件
    └── bin/translation_toolkit.py    # 翻译工具 v12.0
```

> **翻译工作请直接查阅 `汉化/CLAUDE.md`**，它是唯一权威指南。本文件仅提供仓库基础设施参考。

## Git 规则

- 只提交 `assets/` 和 `pack.mcmeta`，不提交 `汉化/`（已在 `.gitignore` 排除）
- 不要带上 `.claude/`、`runs/`、`__pycache__/`
- Commit 格式：`feat: 添加/更新 <模组名> 汉化`

## GitHub Actions

- **claude.yml** — Issue/PR 评论中 `@claude` 时触发，Claude 可执行翻译任务
- **claude-code-review.yml** — PR 打开/同步时自动审查翻译质量（准确性、JSON 格式、键完整性、格式符、术语一致性）
