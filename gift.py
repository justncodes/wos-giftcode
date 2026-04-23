#!/usr/bin/env python3
"""
Gift Code Management Script for Whiteout Survival
Manages player IDs (from player_ids.csv) and gift codes, with batch redemption capabilities
"""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional


CONFIG_FILE = Path(__file__).parent / "cdk.json"
PLAYER_IDS_FILE = Path(__file__).parent / "player_ids.csv"
CACHE_FILE = Path(__file__).parent / "redeem_cache.json"

# Try to import redeem_codes for nickname fetching
REDEEM_CODES_AVAILABLE = False
try:
    # Suppress argparse errors when importing redeem_codes
    _old_argv = sys.argv.copy()
    sys.argv = ['redeem_codes.py', '--code', 'DUMMY', '--csv', str(PLAYER_IDS_FILE)]
    import redeem_codes
    sys.argv = _old_argv
    REDEEM_CODES_AVAILABLE = True
except SystemExit:
    # argparse calls sys.exit on error, catch it
    sys.argv = _old_argv
    pass
except Exception as e:
    sys.argv = _old_argv
    pass


TERMINAL_CACHE_STATUSES = {"success", "already_redeemed", "same_type_exchange"}
STOP_ALL_CODE_STATUSES = {"expired", "claim_limit_reached"}


def empty_cache() -> Dict[str, dict]:
    return {
        "__meta__": {"baseline_seeded": False},
        "codes": {},
    }


def normalize_cache(data: object) -> Dict[str, dict]:
    if isinstance(data, dict) and "codes" in data and "__meta__" in data:
        return data
    if isinstance(data, dict):
        return {
            "__meta__": {"baseline_seeded": True, "migrated_legacy": True},
            "codes": data,
        }
    return empty_cache()


def get_nickname(player_id: str) -> Optional[str]:
    """Get nickname for a player ID using redeem_codes API"""
    if not REDEEM_CODES_AVAILABLE:
        return None
    
    try:
        result = redeem_codes.get_nickname(player_id)
        if isinstance(result, tuple):
            # get_nickname returns a tuple (dict, retry_queue)
            result = result[0]
        if isinstance(result, dict) and result.get("msg") == "Success":
            return result.get("nickname", "Unknown")
        return None
    except Exception as e:
        return None


def load_player_ids() -> List[str]:
    """Load player IDs from CSV file"""
    if PLAYER_IDS_FILE.exists():
        with open(PLAYER_IDS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                return sorted(content.split(','))
    return []


def save_player_ids(player_ids: List[str]) -> None:
    """Save player IDs to CSV file"""
    with open(PLAYER_IDS_FILE, 'w', encoding='utf-8') as f:
        f.write(','.join(player_ids))


def load_cdks() -> List[str]:
    """Load CDKs from configuration file"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get("cdks", [])
    return []


def save_cdks(cdks: List[str]) -> None:
    """Save CDKs to configuration file"""
    config = {"cdks": cdks}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def load_cache() -> Dict[str, Dict[str, dict]]:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = normalize_cache(json.load(f))
        return ensure_baseline_cache_seeded(cache)
    return ensure_baseline_cache_seeded(empty_cache())


def save_cache(cache: Dict[str, Dict[str, dict]]) -> None:
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def ensure_baseline_cache_seeded(cache: Dict[str, Dict[str, dict]]) -> Dict[str, Dict[str, dict]]:
    meta = cache.setdefault("__meta__", {})
    code_buckets = cache.setdefault("codes", {})
    if meta.get("baseline_seeded"):
        return cache

    player_ids = load_player_ids()
    cdks = load_cdks()
    for code in cdks:
        code_bucket = code_buckets.setdefault(code, {})
        for player_id in player_ids:
            code_bucket.setdefault(
                player_id,
                {
                    "status": "already_redeemed",
                    "raw_msg": "BASELINE_CACHE_SEEDED",
                    "friendly_msg": "Seeded from existing configuration",
                    "nickname": None,
                    "is_final": True,
                },
            )

    meta["baseline_seeded"] = True
    meta["baseline_player_count"] = len(player_ids)
    meta["baseline_cdk_count"] = len(cdks)
    save_cache(cache)
    return cache


def get_cached_entry(cache: Dict[str, Dict[str, dict]], code: str, player_id: str) -> Optional[dict]:
    return cache.get("codes", {}).get(code, {}).get(player_id)


def update_cache_entry(cache: Dict[str, Dict[str, dict]], code: str, player_id: str, result: dict) -> None:
    code_bucket = cache.setdefault("codes", {}).setdefault(code, {})
    code_bucket[player_id] = {
        "status": result.get("status", "failed"),
        "raw_msg": result.get("raw_msg"),
        "friendly_msg": result.get("friendly_msg"),
        "nickname": result.get("nickname"),
        "is_final": result.get("is_final", False),
    }


def redeem_code_for_ids(code: str, player_ids: List[str]) -> Optional[dict]:
    if not REDEEM_CODES_AVAILABLE:
        return None
    try:
        return redeem_codes.run_redemption_for_ids(player_ids, code)
    except Exception:
        return None


def validate_cdk_with_sample_id(code: str) -> (bool, str):
    """Validate a CDK by trying to redeem it with one sample player ID."""
    player_ids = load_player_ids()
    if not player_ids:
        return False, "没有可用于校验的ID，请先添加至少一个ID"

    sample_id = random.choice(player_ids)
    redemption_result = redeem_code_for_ids(code, [sample_id])
    if not redemption_result:
        return False, "校验异常: 无法调用 redeem_codes 接口"

    sample_result = redemption_result.get("results", {}).get(sample_id)
    if not sample_result:
        return False, f"校验异常: 未拿到测试ID {sample_id} 的结果"

    status = sample_result.get("status")
    friendly_msg = sample_result.get("friendly_msg") or sample_result.get("raw_msg") or "Unknown"

    if status in TERMINAL_CACHE_STATUSES:
        return True, f"校验通过（测试ID: {sample_id}, 结果: {friendly_msg}）"
    if status in STOP_ALL_CODE_STATUSES:
        return False, f"校验失败（测试ID: {sample_id}, 结果: {friendly_msg}）"
    return False, f"校验结果不明确（测试ID: {sample_id}, 结果: {friendly_msg}）"


def add_id(player_id: str) -> None:
    """Add a new player ID (with deduplication)"""
    nickname = get_nickname(player_id)
    if not nickname:
        print(f"[错误] ID {player_id} 校验失败，无法获取昵称")
        return

    player_ids = load_player_ids()
    if player_id in player_ids:
        print(f"[重复] ID {player_id} 已存在")
        return
    player_ids.append(player_id)
    player_ids = sorted(player_ids)
    save_player_ids(player_ids)
    print(f"[成功] 已添加 ID: {player_id} ({nickname})")


def delete_id(player_id: str) -> None:
    """Delete a player ID"""
    player_ids = load_player_ids()
    if player_id not in player_ids:
        print(f"[错误] ID {player_id} 不存在")
        return
    player_ids.remove(player_id)
    save_player_ids(player_ids)

    cache = load_cache()
    for code_bucket in cache.get("codes", {}).values():
        code_bucket.pop(player_id, None)
    save_cache(cache)

    print(f"[成功] 已删除 ID: {player_id}")


def add_cdk(code: str) -> None:
    """Add a permanent CDK"""
    cdks = load_cdks()
    if code in cdks:
        print(f"[重复] CDK {code} 已存在")
        return

    ok, reason = validate_cdk_with_sample_id(code)
    if not ok:
        print(f"[错误] CDK {code} 未通过可领取性校验: {reason}")
        return

    cdks.append(code)
    save_cdks(cdks)
    print(f"[成功] 已添加 CDK: {code} ({reason})")


def delete_cdk(code: str) -> None:
    """Delete a CDK"""
    cdks = load_cdks()
    if code not in cdks:
        print(f"[错误] CDK {code} 不存在")
        return
    cdks.remove(code)
    save_cdks(cdks)

    cache = load_cache()
    cache.get("codes", {}).pop(code, None)
    save_cache(cache)

    print(f"[成功] 已删除 CDK: {code}")


def _redeem_cdks(cdk_list: List[str], ids: List[str]) -> None:
    """Internal function to redeem a list of CDKs for given IDs with cache"""
    if not ids:
        print("[错误] 没有配置任何 ID")
        return
    
    if not cdk_list:
        print("[错误] 没有指定任何 CDK")
        return
    
    cache = load_cache()
    success_count = 0
    fail_count = 0
    skipped_count = 0
    
    for cdk in cdk_list:
        pending_ids = []
        for player_id in ids:
            cached_entry = get_cached_entry(cache, cdk, player_id)
            if cached_entry and cached_entry.get("status") in TERMINAL_CACHE_STATUSES:
                skipped_count += 1
                continue
            pending_ids.append(player_id)

        if not pending_ids:
            print(f"\n{'='*60}")
            print(f"[跳过] CDK: {cdk}，所有 ID 都已有完成缓存")
            print(f"{'='*60}")
            continue

        print(f"\n{'='*60}")
        print(f"[领取] CDK: {cdk}，待处理 ID {len(pending_ids)}/{len(ids)}")
        print(f"{'='*60}")

        result = redeem_code_for_ids(cdk, pending_ids)
        if not result:
            fail_count += 1
            print(f"[错误] CDK {cdk} 调用 redeem_codes 接口失败")
            continue

        code_failed = False
        for player_id, player_result in result.get("results", {}).items():
            update_cache_entry(cache, cdk, player_id, player_result)
            status = player_result.get("status")
            if status in TERMINAL_CACHE_STATUSES:
                success_count += 1
            elif status in STOP_ALL_CODE_STATUSES:
                fail_count += 1
                code_failed = True
            elif status == "retry":
                fail_count += 1
            elif status == "failed":
                fail_count += 1

        save_cache(cache)

        if code_failed:
            print(f"[停止] CDK {cdk} 已出现全局终止状态: {result.get('stop_reason')}")
        else:
            print(f"[完成] CDK {cdk} 本轮处理完成")
    
    print(f"\n{'='*60}")
    print(f"[完成] 成功: {success_count}, 失败: {fail_count}, 跳过: {skipped_count}")
    print(f"{'='*60}")


def get_all() -> None:
    """Redeem all CDKs for all player IDs"""
    player_ids = load_player_ids()
    cdks = load_cdks()
    
    if not player_ids:
        print("[错误] 没有配置任何 ID")
        return
    
    if not cdks:
        print("[错误] 没有配置任何 CDK")
        return
    
    print(f"[开始] 准备为 {len(player_ids)} 个 ID 领取 {len(cdks)} 个 CDK")
    print(f"IDs: {', '.join(player_ids)}")
    print(f"CDKs: {', '.join(cdks)}")
    print()
    
    _redeem_cdks(cdks, player_ids)


def redeem_code(code: str) -> None:
    """Redeem a single CDK for all player IDs"""
    player_ids = load_player_ids()
    
    if not player_ids:
        print("[错误] 没有配置任何 ID")
        return
    
    print(f"[开始] 准备为 {len(player_ids)} 个 ID 领取 CDK: {code}")
    print(f"IDs: {', '.join(player_ids)}")
    print()
    
    _redeem_cdks([code], player_ids)


def list_all() -> None:
    """List all configured IDs and CDKs"""
    player_ids = load_player_ids()
    cdks = load_cdks()
    cache = load_cache()
    cache_meta = cache.get("__meta__", {})
    
    print("\n[当前配置]")
    print(f"{'─'*60}")
    
    if player_ids:
        print(f"\n玩家 IDs ({len(player_ids)} 个) - 来自 player_ids.csv:")
        for player_id in player_ids:
            nickname = get_nickname(player_id)
            if nickname:
                print(f"  • {player_id} ({nickname})")
            else:
                print(f"  • {player_id}")
    else:
        print("\n玩家 IDs (来自 player_ids.csv): 无")
    
    if cdks:
        print(f"\n常驻 CDKs ({len(cdks)} 个):")
        for cdk in cdks:
            print(f"  • {cdk}")
    else:
        print("\n常驻 CDKs: 无")

    print(f"\n缓存文件: {CACHE_FILE.name}")
    print(f"基线缓存已初始化: {'是' if cache_meta.get('baseline_seeded') else '否'}")
    
    print(f"{'─'*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='礼物代码管理脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python gift.py --add 123456789          # 添加玩家ID到 player_ids.csv
  python gift.py --remove 123456789       # 删除玩家ID
  python gift.py --addcdk FM666           # 添加常驻CDK
  python gift.py --removecdk FM666        # 删除常驻CDK
  python gift.py --list                   # 列出所有配置（包括昵称）
  python gift.py --get                    # 为所有ID领取所有CDK
  python gift.py --code FM666             # 为所有ID领取单个CDK (不加入常驻列表)
        '''
    )
    
    parser.add_argument('--add', type=str, nargs='+', help='添加一个或多个玩家ID')
    parser.add_argument('--remove', type=str, nargs='+', dest='remove_id', help='删除一个或多个玩家ID')
    parser.add_argument('--addcdk', type=str, nargs='+', help='添加一个或多个常驻CDK')
    parser.add_argument('--removecdk', type=str, nargs='+', dest='remove_cdk', help='删除一个或多个常驻CDK')
    parser.add_argument('--list', action='store_true', help='列出所有配置')
    parser.add_argument('--get', action='store_true', help='为所有ID领取所有CDK')
    parser.add_argument('--code', type=str, help='为所有ID领取单个CDK (不加入常驻列表)')
    
    args = parser.parse_args()
    
    if args.add:
        for player_id in args.add:
            add_id(player_id)
    elif args.remove_id:
        for player_id in args.remove_id:
            delete_id(player_id)
    elif args.addcdk:
        for cdk in args.addcdk:
            add_cdk(cdk)
    elif args.remove_cdk:
        for cdk in args.remove_cdk:
            delete_cdk(cdk)
    elif args.list:
        list_all()
    elif args.get:
        get_all()
    elif args.code:
        redeem_code(args.code)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()