from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess


def test_get_file_outline() -> bool:
    """파일 아웃라인 조회 테스트"""
    log_info("파일 아웃라인 조회 테스트를 시작합니다...")

    # 파일별 기대 심볼 목록
    test_cases = [
        {
            "file_path": "combat.cpp",
            "expected_symbols": ["CalculateDamage", "ApplyDamage", "CalculateSkillDamage", "CalculateHealAmount"],
            "description": "combat.cpp 아웃라인",
        },
        {
            "file_path": "player.h",
            "expected_symbols": ["PlayerManager", "MovePlayer"],
            "description": "player.h 아웃라인",
        },
        {
            "file_path": "player.cpp",
            "expected_symbols": ["PlayerManager", "MovePlayer"],
            "description": "player.cpp 아웃라인",
        },
    ]

    child = CodeIndexProcess()
    pid = child.run(None, wait=False)
    if pid is None:
        log_error("MCP 서버 시작 실패")
        return False

    try:
        all_passed = True
        for tc in test_cases:
            file_path = tc["file_path"]
            expected  = tc["expected_symbols"]
            desc      = tc["description"]

            symbols = child.get_file_outline(file_path)
            if symbols is None:
                log_error(f"[{desc}] get_file_outline 호출 실패")
                all_passed = False
                continue

            log_info(f"[{desc}] 심볼 {len(symbols)}건 반환")
            for sym in symbols:
                log_verbose(
                    f"  {sym.get('name', '')} ({sym.get('type', '')})"
                    f" L{sym.get('line', '')}"
                )

            symbol_names = [sym.get("name", "") for sym in symbols]
            for exp in expected:
                # qualified name(예: "NS::Func") 또는 단순 이름 모두 허용
                matched = any(
                    exp == name or name.endswith(f"::{exp}")
                    for name in symbol_names
                )
                if matched:
                    log_verbose(f"  ✅ '{exp}' 확인")
                else:
                    log_error(f"[{desc}] 기대 심볼 '{exp}'이 결과에 없음 (반환: {symbol_names})")
                    all_passed = False

        if all_passed:
            log_info("파일 아웃라인 조회 테스트가 성공적으로 완료되었습니다")
        return all_passed

    except Exception as e:
        log_error(f"파일 아웃라인 조회 테스트 중 예외 발생: {e}")
        return False
    finally:
        child.kill()