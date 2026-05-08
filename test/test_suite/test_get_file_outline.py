from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess


def test_get_file_outline() -> bool:
    """파일 아웃라인 조회 테스트"""
    log_info("파일 아웃라인 조회 테스트를 시작합니다...")

    # 파일별 기대 심볼 목록 (namespace 정합성 포함 검증)
    # get_file_outline의 name 필드는 fully qualified(예: GameServer::CalculateDamage)로 반환됨
    test_cases = [
        {
            "file_path": "combat.cpp",
            "expected_symbols": [
                {"name": "GameServer::CalculateDamage", "namespace": "GameServer"},
                {"name": "GameServer::ApplyDamage", "namespace": "GameServer"},
                {"name": "GameServer::CalculateSkillDamage", "namespace": "GameServer"},
                {"name": "GameServer::CalculateHealAmount", "namespace": "GameServer"},
            ],
            "description": "combat.cpp 아웃라인 (namespace: GameServer)",
        },
        {
            "file_path": "player.h",
            "expected_symbols": [
                {"name": "GameServer::PlayerPosition", "namespace": "GameServer"},
                {"name": "GameServer::PlayerManager", "namespace": "GameServer"},
                {"name": "GameServer::PlayerManager::MovePlayer", "namespace": "GameServer"},
            ],
            "description": "player.h 아웃라인 (namespace: GameServer)",
        },
        {
            "file_path": "player.cpp",
            "expected_symbols": [
                {"name": "GameServer::PlayerManager::PlayerManager", "namespace": "GameServer"},
                {"name": "GameServer::PlayerManager::MovePlayer", "namespace": "GameServer"},
                {"name": "GameServer::PlayerManager::AttackPlayer", "namespace": "GameServer"},
                {"name": "GameServer::PlayerManager::GetPosition", "namespace": "GameServer"},
            ],
            "description": "player.cpp 아웃라인 (namespace: GameServer)",
        },
        {
            "file_path": "monster.h",
            "expected_symbols": [
                {"name": "GameServer::Monster::MonsterInstance", "namespace": "GameServer::Monster"},
                {"name": "GameServer::Monster::MonsterSpawnData", "namespace": "GameServer::Monster"},
            ],
            "description": "monster.h 아웃라인 (namespace: GameServer::Monster - C++17 nested)",
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
                    f" ns={sym.get('namespace', '')} L{sym.get('line', '')}"
                )

            # 모든 기대 심볼 검증 (fully-qualified name과 namespace 정합성 포함)
            for exp in expected:
                exp_name = exp["name"]
                exp_ns   = exp["namespace"]
                
                matched = any(
                    sym.get("name") == exp_name and sym.get("namespace") == exp_ns
                    for sym in symbols
                )
                
                if matched:
                    log_verbose(f"  ✅ '{exp_name}' (ns: {exp_ns}) 확인")
                else:
                    log_error(f"[{desc}] 기대 심볼을 찾을 수 없음: {exp_name} (ns: {exp_ns})")
                    log_verbose(f"    파싱된 심볼: {[(s.get('name'), s.get('namespace')) for s in symbols]}")
                    all_passed = False

        if all_passed:
            log_info("파일 아웃라인 조회 테스트가 성공적으로 완료되었습니다")
        return all_passed

    except Exception as e:
        log_error(f"파일 아웃라인 조회 테스트 중 예외 발생: {e}")
        return False
    finally:
        child.kill()