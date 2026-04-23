#!/usr/bin/env python3
"""
Gift Code Management Script for Whiteout Survival
Manages player IDs (from player_ids.csv) and gift codes, with batch redemption capabilities
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


CONFIG_FILE = Path(__file__).parent / "cdk.json"
PLAYER_IDS_FILE = Path(__file__).parent / "player_ids.csv"

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


def validate_cdk_with_sample_id(code: str) -> (bool, str):
    """Validate a CDK by trying to redeem it with one sample player ID."""
    player_ids = load_player_ids()
    if not player_ids:
        return False, "没有可用于校验的ID，请先添加至少一个ID"

    sample_id = player_ids[0]
    temp_csv = Path(__file__).parent / "temp_validate_id.csv"

    try:
        with open(temp_csv, 'w', encoding='utf-8') as f:
            f.write(sample_id)

        cmd = [
            sys.executable,
            "redeem_codes.py",
            "--code", code,
            "--csv", str(temp_csv)
        ]
        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        output_lower = output.lower()

        # Positive signals: code is usable for at least one account.
        positive_markers = [
            "Successfully redeemed",
            "Already redeemed",
            "Successfully redeemed (same type)",
        ]
        if any(marker in output for marker in positive_markers):
            return True, f"校验通过（测试ID: {sample_id}）"

        # Negative signals: code is likely invalid/expired/exhausted.
        negative_markers = [
            "Code has expired",
            "Claim limit reached",
            "invalid code",
            "not found",
            "time error",
            "used",
        ]
        if any(marker.lower() in output_lower for marker in negative_markers):
            return False, f"校验失败，CDK可能无效或已过期（测试ID: {sample_id}）"

        if result.returncode != 0:
            return False, f"校验失败，redeem_codes.py 返回非0状态码: {result.returncode}"

        return False, f"校验结果不明确，暂不加入（测试ID: {sample_id}）"
    except Exception as e:
        return False, f"校验异常: {e}"
    finally:
        try:
            if temp_csv.exists():
                temp_csv.unlink()
        except Exception:
            pass


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
    print(f"[成功] 已删除 CDK: {code}")


def _redeem_cdks(cdk_list: List[str], ids: List[str]) -> None:
    """Internal function to redeem a list of CDKs for given IDs"""
    if not ids:
        print("[错误] 没有配置任何 ID")
        return
    
    if not cdk_list:
        print("[错误] 没有指定任何 CDK")
        return
    
    # Use player_ids.csv directly
    csv_path = PLAYER_IDS_FILE
    
    success_count = 0
    fail_count = 0
    
    for cdk in cdk_list:
        print(f"\n{'='*60}")
        print(f"[领取] CDK: {cdk}")
        print(f"{'='*60}")
        
        cmd = [
            sys.executable,
            "redeem_codes.py",
            "--code", cdk,
            "--csv", str(csv_path)
        ]
        
        try:
            result = subprocess.run(cmd, cwd=Path(__file__).parent)
            if result.returncode == 0:
                success_count += 1
                print(f"[成功] CDK {cdk} 领取完成")
            else:
                fail_count += 1
                print(f"[失败] CDK {cdk} 领取失败")
        except Exception as e:
            fail_count += 1
            print(f"[错误] 执行命令失败: {e}")
    
    print(f"\n{'='*60}")
    print(f"[完成] 成功: {success_count}, 失败: {fail_count}")
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