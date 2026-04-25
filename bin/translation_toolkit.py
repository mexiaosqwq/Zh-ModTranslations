#!/usr/bin/env python3
"""
Minecraft Mod 翻译工具包 v9.2
核心功能：JSON处理、差异提取、格式验证、JAR提取、物品查询
扩展功能：make-pending / sync-lang / import-rp
"""

import json
import re
import zipfile
import shutil
import argparse
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

ENC = "utf-8"

# 常量定义
DEFAULT_LANGS_ROOT = "workdir/langs"
DEFAULT_PACK_ROOT = f"{DEFAULT_LANGS_ROOT}/Minecraft-Mod-Language-Modpack-Converted-1.20.1"
DEFAULT_PACK_VERSION = "1.20.1"  # 默认版本，当无法检测到版本时使用


def detect_mod_version_from_jar(jar_name: str) -> Optional[str]:
    """
    从 JAR 文件名中提取 Minecraft 版本号
    支持格式：mod-1.20.1-x.x.x.jar, mod-1.21.1-x.x.x.jar 等
    返回主版本号（如 1.20.1, 1.21.1），如果无法提取则返回 None
    """
    # 匹配 1.xx.x 格式的版本号
    pattern = r'1\.(20|21)\.\d+'
    match = re.search(pattern, jar_name)
    if match:
        return match.group(0)
    return None


def get_pack_root(version: str, langs_root: str = DEFAULT_LANGS_ROOT) -> Path:
    """
    根据版本号获取对应的参考包路径
    如果找不到对应版本的参考包，返回默认版本的参考包
    """
    pack_path = Path(langs_root) / f"Minecraft-Mod-Language-Modpack-Converted-{version}"
    if pack_path.exists() and pack_path.is_dir():
        return pack_path
    # 回退到默认版本
    return Path(DEFAULT_PACK_ROOT)


# 版本到资源包路径的映射
VERSION_RP_PATHS = {
    "1.20.1": "workdir/versions/1.20.1/resourcepacks/模组汉化.zip",
    "1.21.1": "workdir/versions/1.21.1生物农业/resourcepacks/模组汉化.zip",
}


def get_auto_rp_path(modid: str, mods_root: str = "mods") -> Optional[Path]:
    """
    根据模组 ID 自动检测版本并返回对应的资源包路径
    """
    mods_dir = Path(mods_root)
    if not mods_dir.exists():
        return None

    # 查找匹配 modid 的 JAR 文件
    jar_files = list(mods_dir.glob(f"*{modid}*.jar"))
    if not jar_files:
        return None

    # 从 JAR 文件名检测版本
    for jar_file in jar_files:
        version = detect_mod_version_from_jar(jar_file.name)
        if version and version in VERSION_RP_PATHS:
            return Path(VERSION_RP_PATHS[version]).expanduser()

    return None


def log(msg: str):
    """打印日志"""
    print(f"[TK] {msg}")


def err(msg: str) -> int:
    """打印错误并返回错误码"""
    print(f"[TK] Error: {msg}", file=sys.stderr)
    return 1


def read_json(path: Path) -> Optional[dict]:
    """读取JSON文件"""
    try:
        data = json.loads(path.read_text(encoding=ENC))
        if not isinstance(data, dict):
            err(f"JSON 顶层不是对象: {path} (类型: {type(data).__name__})")
            return None
        return data
    except Exception as e:
        err(f"无法读取JSON {path}: {e}")
        return None


def write_json(path: Path, data: dict, indent: int = 2, backup: bool = True) -> bool:
    """写入JSON文件，可选备份"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            backup_dir = path.parent / ".backup"
            backup_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(path, backup_dir / f"{path.stem}_{ts}.bak")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding=ENC)
        return True
    except Exception as e:
        err(f"无法写入 {path}: {e}")
        return False


# ==================== 内部工具函数（新增） ====================

def extract_jar_json(jar_path: Path, output_dir: Path) -> Tuple[int, List[str]]:
    """从JAR提取 data/ 与 assets/ 下的所有 .json 文件到 output_dir，返回(数量, 列表)"""
    if not jar_path.exists():
        raise FileNotFoundError(str(jar_path))

    extracted: List[str] = []
    with zipfile.ZipFile(jar_path, "r") as z:
        files = [n for n in z.namelist() if n.startswith(("data/", "assets/")) and n.endswith(".json")]
        total = len(files)

        for i, name in enumerate(files, 1):
            if i % 100 == 0 or i == total:
                print(f"  进度: {i}/{total}", end="\r")
            try:
                # Zip Slip 防护：确保目标路径在输出目录内
                target = (output_dir / name).resolve()
                if not str(target).startswith(str(output_dir.resolve())):
                    print(f"\n  警告: 跳过潜在路径穿越: {name}")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                extracted.append(name)
            except Exception as e:
                print(f"\n  警告: 提取失败 {name}: {e}")

    print(f"\n  完成! 提取了 {len(extracted)} 个文件到 {output_dir}")
    return len(extracted), extracted


def diff_missing(en_data: Dict, zh_data: Dict) -> Dict:
    """返回 en 中有但 zh 中没有的条目（值取 en）"""
    return {k: v for k, v in en_data.items() if k not in zh_data}


def find_modid_candidates(extract_dir: Path) -> List[Path]:
    """在提取目录中找 assets/*/lang/en_us.json"""
    return sorted(extract_dir.glob("assets/*/lang/en_us.json"))


def get_modid_from_en_path(en_path: Path) -> str:
    """从 .../assets/<modid>/lang/en_us.json 解析 modid"""
    parts = en_path.parts
    if "assets" in parts:
        idx = parts.index("assets")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "unknown"


def zip_dir_to(zip_path: Path, src_dir: Path) -> None:
    """把目录整体重打包成 zip（避免追加导致重复条目）"""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src_dir.rglob("*")):
            if p.is_dir():
                continue
            arc = p.relative_to(src_dir).as_posix()
            z.write(p, arc)


# ==================== 命令处理 ====================

def cmd_extract_jar(args) -> int:
    """从JAR文件提取数据"""
    jar_path = Path(args.jar)
    output_dir = Path(args.output)

    if not jar_path.exists():
        return err(f"JAR文件不存在: {jar_path}")

    log(f"正在提取 {jar_path.name}...")
    try:
        extract_jar_json(jar_path, output_dir)
        return 0
    except Exception as e:
        return err(f"提取失败: {e}")


def cmd_diff(args) -> int:
    """提取缺失翻译：英文中有但中文中没有的条目"""
    en_path = Path(args.en)
    zh_path = Path(args.zh) if args.zh else None

    en_data = read_json(en_path)
    if en_data is None:
        return 1

    zh_data = read_json(zh_path) if zh_path and zh_path.exists() else {}

    missing = diff_missing(en_data, zh_data)

    if args.output:
        out_path = Path(args.output)
        if not write_json(out_path, missing):
            return 1
        log(f"已提取 {len(missing)} 条未翻译条目到 {out_path}")
    else:
        print(json.dumps(missing, ensure_ascii=False, indent=2))

    return 0


def cmd_validate(args) -> int:
    """验证JSON格式"""
    path = Path(args.file)
    data = read_json(path)

    if data is None:
        return err(f"无效的JSON文件: {path}")

    log(f"验证通过: {path} ({len(data)} 条目)")
    return 0


def cmd_search(args) -> int:
    """搜索语言文件内容"""
    # 如果指定了版本和 modid，自动构建参考包路径
    if args.version and args.modid:
        pack_root = get_pack_root(args.version, args.langs_root if hasattr(args, 'langs_root') else DEFAULT_LANGS_ROOT)
        path = pack_root / "assets" / args.modid / "lang" / "zh_cn.json"
        log(f"使用参考包: {path}")
    else:
        path = Path(args.file)

    data = read_json(path)
    if data is None:
        return 1

    needle = args.keyword.lower()
    results = []

    for key, value in data.items():
        val_str = str(value)
        match_key = needle in key.lower()
        match_val = needle in val_str.lower()

        if args.scope == "key" and match_key:
            results.append((key, value))
        elif args.scope == "value" and match_val:
            results.append((key, value))
        elif args.scope == "both" and (match_key or match_val):
            results.append((key, value, match_key, match_val))

    if not results:
        log(f"未找到匹配: '{args.keyword}'")
        return 0

    for item in results:
        if args.scope == "both":
            key, val, mk, mv = item
            tags = []
            if mk:
                tags.append("键")
            if mv:
                tags.append("值")
            print(f"{key} [{','.join(tags)}]")
        else:
            key, val = item
            print(f"{key}")
        print(f"  -> {str(val)[:100]}")
        print()

    log(f"找到 {len(results)} 个匹配")
    return 0


def cmd_clean(args) -> int:
    """清洗并格式化JSON"""
    path = Path(args.file)
    data = read_json(path)
    if data is None:
        return 1

    if write_json(path, data, indent=args.indent, backup=not args.no_backup):
        log(f"已清洗: {path}")
        return 0
    return 1


def cmd_query(args) -> int:
    """查询物品信息（配方、战利品、进度等）"""
    data_dir = Path(args.data)
    item_id = args.item

    if not data_dir.exists():
        return err(f"数据目录不存在: {data_dir}")

    log(f"查询: {item_id}")
    found = False

    # 1. 查询配方
    recipes_dir = data_dir / "recipes"
    if recipes_dir.exists():
        recipes = []
        for f in recipes_dir.rglob("*.json"):
            try:
                content = f.read_text(encoding=ENC)
                if item_id in content:
                    recipe_name = f.stem
                    recipe_data = json.loads(content)
                    recipes.append((recipe_name, recipe_data))
            except:
                pass

        if recipes:
            found = True
            print(f"\n[配方] 找到 {len(recipes)} 个相关配方:")
            for name, data in recipes[:5]:
                rtype = data.get("type", "unknown").split(":")[-1]
                print(f"  - {name} ({rtype})")
            if len(recipes) > 5:
                print(f"  ... 还有 {len(recipes) - 5} 个")

    # 2. 查询战利品表
    loot_dir = data_dir / "loot_tables"
    if loot_dir.exists():
        loot_sources = []
        for f in loot_dir.rglob("*.json"):
            try:
                content = f.read_text(encoding=ENC)
                if item_id in content:
                    loot_sources.append(f.stem)
            except:
                pass

        if loot_sources:
            found = True
            print(f"\n[战利品] 出现在 {len(loot_sources)} 个战利品表:")
            for src in loot_sources[:5]:
                print(f"  - {src}")
            if len(loot_sources) > 5:
                print(f"  ... 还有 {len(loot_sources) - 5} 个")

    # 3. 查询进度
    adv_dir = data_dir / "advancements"
    if adv_dir.exists():
        advancements = []
        for f in adv_dir.rglob("*.json"):
            try:
                content = f.read_text(encoding=ENC)
                if item_id in content:
                    advancements.append(f.stem)
            except:
                pass

        if advancements:
            found = True
            print(f"\n[进度] 出现在 {len(advancements)} 个进度:")
            for adv in advancements[:5]:
                print(f"  - {adv}")
            if len(advancements) > 5:
                print(f"  ... 还有 {len(advancements) - 5} 个")

    # 4. 查询纹理（注意：extract-jar 不提 png，本功能仅对你手动准备的 textures/ 目录有效）
    textures_dir = data_dir / "textures"
    if textures_dir.exists():
        textures = []
        for f in textures_dir.rglob("*.png"):
            if item_id.split(":")[-1] in f.stem:
                textures.append(f.relative_to(textures_dir))

        if textures:
            found = True
            print(f"\n[纹理] 找到 {len(textures)} 个相关纹理:")
            for tex in textures[:5]:
                print(f"  - {tex}")
            if len(textures) > 5:
                print(f"  ... 还有 {len(textures) - 5} 个")

    if not found:
        print(f"\n  未找到 {item_id} 的相关信息")

    return 0


def cmd_list(args) -> int:
    """列出模组数据结构"""
    data_dir = Path(args.data)

    if not data_dir.exists():
        return err(f"数据目录不存在: {data_dir}")

    log(f"数据结构: {data_dir}")

    for subdir in ["recipes", "loot_tables", "advancements", "tags", "lang", "textures"]:
        path = data_dir / subdir
        if path.exists():
            count = len(list(path.rglob("*.json" if subdir != "textures" else "*.png")))
            print(f"  {subdir}/: {count} 个文件")

    return 0


# ==================== 新增命令：make-pending / sync-lang / import-rp ====================

def cmd_make_pending(args) -> int:
    """
    一键生成真正缺失的 pending_translation/<modid>.json：
    en_us - official zh_cn - pack zh_cn
    """
    jar_path = Path(args.jar)
    if not jar_path.exists():
        return err(f"JAR文件不存在: {jar_path}")

    log(f"正在处理 {jar_path.name}...")
    modid, count, err_msg = _process_single_jar(jar_path, args)

    if err_msg:
        return err(f"处理失败: {err_msg}")

    log(f"成功: modid={modid}, pending={count} keys")
    return 0


def cmd_sync_lang(args) -> int:
    """
    pending_translation/<modid>.json -> langs/<modid>/zh_cn.json
    - 以 pending 的键集合为准
    - 保留已有翻译（输出文件中同 key 的值优先）
    - 可选 clean + validate
    """
    langs_root = Path(args.langs_root)
    pending_path = Path(args.pending) if args.pending else (langs_root / "pending_translation" / f"{args.modid}.json")
    out_path = Path(args.output) if args.output else (langs_root / args.modid / "zh_cn.json")

    pending_data = read_json(pending_path)
    if pending_data is None:
        return 1

    out_data = read_json(out_path) if out_path.exists() else {}
    if out_path.exists() and out_data is None:
        return 1

    merged = {}
    for k, v in pending_data.items():
        if k in out_data and isinstance(out_data[k], str) and out_data[k].strip():
            merged[k] = out_data[k]
        else:
            merged[k] = v

    if not write_json(out_path, merged, indent=2, backup=not args.no_backup):
        return 1

    # clean + validate
    if not args.no_clean:
        rc = cmd_clean(argparse.Namespace(file=str(out_path), indent=2, no_backup=args.no_backup))
        if rc != 0:
            return rc

    if not args.no_validate:
        rc = cmd_validate(argparse.Namespace(file=str(out_path)))
        if rc != 0:
            return rc

    log(f"pending: {pending_path} ({len(pending_data)} keys)")
    log(f"output : {out_path} ({len(merged)} keys)")
    return 0


def cmd_import_rp(args) -> int:
    """
    把 langs/<modid>/zh_cn.json 导入资源包 zip：
    - 先备份
    - 验证输入 JSON
    - 解压到临时目录
    - 覆盖 assets/<modid>/lang/zh_cn.json
    - 整体重打包替换（避免重复条目）
    """
    # 自动检测资源包路径（当 rp 未指定且未禁用自动检测时）
    if not args.rp and not args.no_auto_path:
        rp = get_auto_rp_path(args.modid, args.mods_root)
        if rp is None:
            return err(f"无法自动检测资源包路径，请手动指定 rp 参数")
        log(f"自动检测资源包路径: {rp}")
    elif args.rp:
        rp = Path(args.rp).expanduser()
    else:
        return err(f"未指定资源包路径，请使用 rp 参数或移除 --no-auto-path")

    if not rp.exists():
        return err(f"资源包不存在: {rp}")

    zh_path = Path(args.input).expanduser() if args.input else (Path(args.langs_root) / args.modid / "zh_cn.json")
    if not zh_path.exists():
        return err(f"语言文件不存在: {zh_path}")

    # 验证输入 JSON
    zh_data = read_json(zh_path)
    if zh_data is None:
        return err(f"语言文件无效: {zh_path}")

    # backup
    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = rp.with_suffix(rp.suffix + f".{ts}.bak")
        try:
            shutil.copy2(rp, backup)
            log(f"已备份: {backup}")
        except Exception as e:
            return err(f"备份失败: {e}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        try:
            with zipfile.ZipFile(rp, "r") as z:
                z.extractall(td)
        except Exception as e:
            return err(f"解压资源包失败: {e}")

        target = td / "assets" / args.modid / "lang" / "zh_cn.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(zh_path, target)
        except Exception as e:
            return err(f"复制语言文件失败: {e}")

        new_zip = rp.with_suffix(rp.suffix + ".new")
        try:
            if new_zip.exists():
                new_zip.unlink()
            zip_dir_to(new_zip, td)
            new_zip.replace(rp)
        except Exception as e:
            return err(f"重打包失败: {e}")

    log(f"已导入: {zh_path} -> assets/{args.modid}/lang/zh_cn.json")
    log(f"资源包更新完成: {rp}")
    return 0


# ==================== 批量命令 ====================

def _process_single_jar(jar_path: Path, args) -> Tuple[str, int, str]:
    """
    处理单个 JAR 的核心逻辑（被 cmd_make_pending 和 cmd_batch_make_pending 共用）
    返回 (modid, pending_keys_count, error_message)
    成功时 error_message 为空
    """
    jarstem = args.jarname or jar_path.stem
    output_dir = Path(args.output) if args.output else Path(args.data_root) / jarstem

    # 自动检测版本并选择参考包
    if args.pack_root == DEFAULT_PACK_ROOT:
        detected_version = detect_mod_version_from_jar(jar_path.name)
        if detected_version:
            pack_root = get_pack_root(detected_version, args.langs_root)
        else:
            pack_root = Path(DEFAULT_PACK_ROOT)
    else:
        pack_root = Path(args.pack_root)

    # 1) extract
    if not args.skip_extract:
        try:
            extract_jar_json(jar_path, output_dir)
        except Exception as e:
            return ("", 0, f"提取失败: {e}")

    # 2) detect modid
    candidates = find_modid_candidates(output_dir)
    if not candidates:
        return ("", 0, f"未找到 assets/*/lang/en_us.json")

    if args.modid:
        en_path = output_dir / "assets" / args.modid / "lang" / "en_us.json"
        if not en_path.exists():
            modid_list = [f"  - modid={get_modid_from_en_path(p)}" for p in candidates]
            return ("", 0, f"指定 --modid 但 en_us.json 不存在\n候选:\n" + "\n".join(modid_list))
        modid = args.modid
    else:
        if len(candidates) > 1:
            modid_list = [f"  - modid={get_modid_from_en_path(p)}" for p in candidates]
            return ("", 0, f"发现多个 en_us.json，请用 --modid 指定:\n" + "\n".join(modid_list))
        en_path = candidates[0]
        modid = get_modid_from_en_path(en_path)

    official_zh = output_dir / "assets" / modid / "lang" / "zh_cn.json"
    pack_zh = pack_root / "assets" / modid / "lang" / "zh_cn.json"

    en_data = read_json(en_path)
    if en_data is None:
        return (modid, 0, f"en_us.json 无效")

    official_data = read_json(official_zh) if official_zh.exists() else {}
    if official_zh.exists() and official_data is None:
        return (modid, 0, f"官方 zh_cn.json 无效")

    pack_data = read_json(pack_zh) if pack_zh.exists() else {}
    if pack_zh.exists() and pack_data is None:
        return (modid, 0, f"参考包 zh_cn.json 无效")

    # diff
    step1 = diff_missing(en_data, official_data)
    final = diff_missing(step1, pack_data)

    # 过滤不翻译键
    final = {k: v for k, v in final.items() if not k.endswith('.author')}

    # 写入 pending
    langs_root = Path(args.langs_root)
    pending_dir = langs_root / "pending_translation"
    pending_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.pending_out) if args.pending_out else (pending_dir / f"{modid}.json")

    if not write_json(out_path, final, indent=2, backup=not args.no_backup):
        return (modid, len(final), f"写入 pending 文件失败")

    return (modid, len(final), "")


def cmd_batch_make_pending(args) -> int:
    """批量一键生成真正缺失：扫描 mods/ 目录下所有 JAR"""
    mods_dir = Path(args.mods_root)
    if not mods_dir.exists():
        return err(f"mods 目录不存在: {mods_dir}")

    jars = sorted(mods_dir.glob("*.jar"))
    if not jars:
        return err(f"mods 目录下没有找到 .jar 文件: {mods_dir}")

    # 解析 --modids 过滤
    filter_modids = set()
    if args.modids:
        filter_modids = set(m.strip() for m in args.modids.split(",") if m.strip())

    log(f"找到 {len(jars)} 个 JAR 文件，开始批量处理...")
    results = []
    total_ok = 0
    total_fail = 0

    for jar_path in jars:
        # 如果指定了 modid 过滤器，尝试从文件名猜测
        if filter_modids:
            matched = False
            for fm in filter_modids:
                if fm.lower() in jar_path.stem.lower():
                    matched = True
                    break
            if not matched:
                log(f"跳过 {jar_path.name}（不匹配 --modids 过滤器）")
                continue

        print(f"\n{'='*50}")
        log(f"正在处理: {jar_path.name}")
        modid, count, err_msg = _process_single_jar(jar_path, args)

        if err_msg:
            print(f"  [失败] {err_msg}")
            results.append((jar_path.name, modid or "?", 0, err_msg))
            total_fail += 1
        else:
            print(f"  [成功] modid={modid}, pending={count} keys")
            results.append((jar_path.name, modid, count, ""))
            total_ok += 1

    # 汇总报告
    print(f"\n{'='*50}")
    log(f"批量处理完成: 成功 {total_ok}, 失败 {total_fail}, 总计 {total_ok + total_fail}")
    if total_fail > 0:
        print(f"\n失败列表:")
        for name, mid, cnt, msg in results:
            if msg:
                print(f"  ✗ {name} (modid={mid})")
                print(f"    原因: {msg}")
    if total_ok > 0:
        print(f"\n成功列表:")
        for name, mid, cnt, msg in results:
            if not msg:
                print(f"  ✓ {name} → modid={mid}, {cnt} keys")

    return 1 if total_fail > 0 else 0


def cmd_batch_sync_lang(args) -> int:
    """批量同步 pending 文件到工作目录"""
    langs_root = Path(args.langs_root)
    pending_dir = langs_root / "pending_translation"
    if not pending_dir.exists():
        return err(f"pending 目录不存在: {pending_dir}")

    pending_files = sorted(pending_dir.glob("*.json"))
    if not pending_files:
        return err(f"pending 目录下没有 .json 文件: {pending_dir}")

    log(f"找到 {len(pending_files)} 个 pending 文件，开始批量同步...")
    total_ok = 0
    total_fail = 0

    for pf in pending_files:
        modid = pf.stem
        print(f"\n{'='*50}")
        log(f"正在同步: {modid}")

        # 构造 sync-lang 的 args（复用 cmd_sync_lang 逻辑）
        sync_args = argparse.Namespace(
            modid=modid,
            langs_root=args.langs_root,
            pending=str(pf),
            output=str(langs_root / modid / "zh_cn.json"),
            no_clean=args.no_clean,
            no_validate=args.no_validate,
            no_backup=args.no_backup,
        )
        rc = cmd_sync_lang(sync_args)

        if rc == 0:
            log(f"同步成功: {modid}")
            total_ok += 1
        else:
            log(f"同步失败: {modid} (返回码 {rc})")
            total_fail += 1

    print(f"\n{'='*50}")
    log(f"批量同步完成: 成功 {total_ok}, 失败 {total_fail}, 总计 {total_ok + total_fail}")
    return 1 if total_fail > 0 else 0


# ==================== 主程序 ====================

def main():
    parser = argparse.ArgumentParser(
        prog="translation_toolkit.py",
        description="Minecraft Mod 翻译工具包 v9.2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 提取JAR数据（只提取 json）
  python3 bin/translation_toolkit.py extract-jar workdir/mods/spawn.jar -o workdir/data/spawn/

  # 提取未翻译条目（en 有，zh 没有）
  python3 bin/translation_toolkit.py diff workdir/data/spawn/assets/spawn/lang/en_us.json workdir/data/spawn/assets/spawn/lang/zh_cn.json -o to_translate.json

  # 一键生成真正缺失（扣掉官方+参考包）
  python3 bin/translation_toolkit.py make-pending workdir/mods/spawn.jar

  # 同步 pending 到最终文件（保留已有翻译）并 clean/validate
  python3 bin/translation_toolkit.py sync-lang spawn

  # 导入资源包 zip（安全重打包）
  python3 bin/translation_toolkit.py import-rp "~/.../resourcepacks/模组汉化5.0.zip" spawn

  # 批量 make-pending（扫描 workdir/mods/ 下所有 JAR）
  python3 bin/translation_toolkit.py batch-make-pending

  # 批量 sync-lang（同步所有 pending 文件）
  python3 bin/translation_toolkit.py batch-sync-lang

  # 查询物品信息（注意传 data/<jar>/data/<namespace>/）
  python3 bin/translation_toolkit.py query workdir/data/spawn/data/spawn/ spawn:angler_fish
        """
    )
    sub = parser.add_subparsers(dest="cmd", help="可用命令")

    # extract-jar
    p_extract = sub.add_parser("extract-jar", help="从JAR提取数据（仅 json）")
    p_extract.add_argument("jar", help="JAR文件路径")
    p_extract.add_argument("-o", "--output", required=True, help="输出目录")

    # diff
    p_diff = sub.add_parser("diff", help="提取未翻译条目（en 有 zh 没有）")
    p_diff.add_argument("en", help="英文文件路径")
    p_diff.add_argument("zh", nargs="?", help="中文文件路径（可选）")
    p_diff.add_argument("-o", "--output", help="输出文件路径")

    # validate
    p_val = sub.add_parser("validate", help="验证JSON格式")
    p_val.add_argument("file", help="JSON文件路径")

    # search
    p_search = sub.add_parser("search", help="搜索语言文件")
    p_search.add_argument("file", nargs="?", help="JSON文件路径（若指定 --version 和 --modid 则可省略）")
    p_search.add_argument("keyword", help="搜索关键词")
    p_search.add_argument("--scope", choices=["key", "value", "both"], default="both", help="搜索范围")
    p_search.add_argument("--version", help="参考包版本（如 1.20.1, 1.21.1），与 --modid 配合使用")
    p_search.add_argument("--modid", help="模组 ID（与 --version 配合使用自动选择参考包）")
    p_search.add_argument("--langs-root", default=DEFAULT_LANGS_ROOT, help="langs 根目录（用于查找参考包）")

    # clean
    p_clean = sub.add_parser("clean", help="清洗并格式化JSON")
    p_clean.add_argument("file", help="JSON文件路径")
    p_clean.add_argument("--indent", type=int, default=2, help="缩进空格数")
    p_clean.add_argument("--no-backup", action="store_true", help="不创建备份")

    # query
    p_query = sub.add_parser("query", help="查询物品信息（配方、战利品、进度等）")
    p_query.add_argument("data", help="数据目录路径（如 data/<jar>/data/<namespace>/）")
    p_query.add_argument("item", help="物品ID（如 spawn:angler_fish）")

    # list
    p_list = sub.add_parser("list", help="列出模组数据结构")
    p_list.add_argument("data", help="数据目录路径")

    # make-pending (NEW)
    p_mp = sub.add_parser("make-pending", help="提取JAR并生成真正缺失的 pending_translation/<modid>.json")
    p_mp.add_argument("jar", help="JAR文件路径（mods/*.jar）")
    p_mp.add_argument("-o", "--output", help="提取输出目录（默认 data/<jarstem>/）")
    p_mp.add_argument("--data-root", default="workdir/data", help="默认提取根目录（当未指定 -o 时使用）")
    p_mp.add_argument("--jarname", default=None, help="自定义 jarstem（默认 jar 文件名去 .jar）")
    p_mp.add_argument("--modid", default=None, help="当存在多个 assets/*/lang/en_us.json 时手动指定")
    p_mp.add_argument("--pack-root", default=DEFAULT_PACK_ROOT,
                      help="参考汉化包根目录")
    p_mp.add_argument("--langs-root", default=DEFAULT_LANGS_ROOT, help="langs 根目录（用于输出 pending_translation）")
    p_mp.add_argument("--pending-out", default=None, help="pending 输出路径（默认 langs/pending_translation/<modid>.json）")
    p_mp.add_argument("--skip-extract", action="store_true", help="跳过提取，直接使用已存在的输出目录")
    p_mp.add_argument("--no-backup", action="store_true", help="写入 pending 时不创建备份")

    # sync-lang (NEW)
    p_sl = sub.add_parser("sync-lang", help="将 pending 同步到 langs/<modid>/zh_cn.json（保留已有翻译）")
    p_sl.add_argument("modid", help="modid")
    p_sl.add_argument("--langs-root", default=DEFAULT_LANGS_ROOT, help="langs 根目录")
    p_sl.add_argument("--pending", default=None, help="pending 路径（默认 langs/pending_translation/<modid>.json）")
    p_sl.add_argument("--output", default=None, help="输出路径（默认 langs/<modid>/zh_cn.json）")
    p_sl.add_argument("--no-clean", action="store_true", help="同步后不执行 clean")
    p_sl.add_argument("--no-validate", action="store_true", help="同步后不执行 validate")
    p_sl.add_argument("--no-backup", action="store_true", help="写入输出时不创建备份")

    # import-rp (NEW)
    p_ir = sub.add_parser("import-rp", help="把 langs/<modid>/zh_cn.json 安全导入资源包 zip（备份+重打包）")
    p_ir.add_argument("rp", nargs="?", help="资源包 zip 路径（未指定时自动检测）")
    p_ir.add_argument("modid", help="modid")
    p_ir.add_argument("--langs-root", default=DEFAULT_LANGS_ROOT, help="langs 根目录（默认读取 langs/mods/<modid>/zh_cn.json）")
    p_ir.add_argument("--mods-root", default="mods", help="mods 根目录（用于自动检测版本）")
    p_ir.add_argument("--input", default=None, help="自定义导入文件路径（默认 langs/mods/<modid>/zh_cn.json）")
    p_ir.add_argument("--no-backup", action="store_true", help="不备份原资源包 zip")
    p_ir.add_argument("--no-auto-path", action="store_true", help="禁用自动路径检测（需手动指定 rp 参数）")

    # batch-make-pending (NEW)
    p_bmp = sub.add_parser("batch-make-pending", help="批量生成 pending：扫描 mods/ 下所有 JAR")
    p_bmp.add_argument("--mods-root", default="workdir/mods", help="mods 根目录（默认 workdir/mods）")
    p_bmp.add_argument("--data-root", default="workdir/data", help="默认提取根目录（默认 workdir/data）")
    p_bmp.add_argument("--modids", default=None, help="只处理指定 modid（逗号分隔）")
    p_bmp.add_argument("--pack-root", default=DEFAULT_PACK_ROOT, help="参考汉化包根目录")
    p_bmp.add_argument("--langs-root", default=DEFAULT_LANGS_ROOT, help="langs 根目录")
    p_bmp.add_argument("--pending-out", default=None, help="pending 输出路径（默认 langs/pending_translation/<modid>.json）")
    p_bmp.add_argument("--jarname", default=None, help="自定义 jarstem")
    p_bmp.add_argument("--skip-extract", action="store_true", help="跳过提取")
    p_bmp.add_argument("--no-backup", action="store_true", help="不创建备份")

    # batch-sync-lang (NEW)
    p_bsl = sub.add_parser("batch-sync-lang", help="批量同步 pending 文件到工作目录")
    p_bsl.add_argument("--langs-root", default=DEFAULT_LANGS_ROOT, help="langs 根目录")
    p_bsl.add_argument("--no-clean", action="store_true", help="同步后不执行 clean")
    p_bsl.add_argument("--no-validate", action="store_true", help="同步后不执行 validate")
    p_bsl.add_argument("--no-backup", action="store_true", help="不创建备份")

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return 1

    handlers = {
        "extract-jar": cmd_extract_jar,
        "diff": cmd_diff,
        "validate": cmd_validate,
        "search": cmd_search,
        "clean": cmd_clean,
        "query": cmd_query,
        "list": cmd_list,
        "make-pending": cmd_make_pending,
        "sync-lang": cmd_sync_lang,
        "import-rp": cmd_import_rp,
        "batch-make-pending": cmd_batch_make_pending,
        "batch-sync-lang": cmd_batch_sync_lang,
    }

    handler = handlers.get(args.cmd)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())