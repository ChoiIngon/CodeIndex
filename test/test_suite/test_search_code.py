from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import Timer, log_error, log_info, log_verbose
from code_index import CodeIndexProcess, SearchResult

def test_search_code() -> Optional[List[Dict[str, Any]]]:
    queries = [
        # === 기본 검색 테스트 (필터 없음) ===
        {
            "query": "플레이어 이동 처리 함수",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": None,
            "expected_symbol": "MovePlayer",
            "description": "player.h - 기본 검색"
        },
        {
            "query": "데미지 계산 로직",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": None,
            "expected_symbol": "CalculateDamage",
            "description": "combat.cpp - 기본 검색"
        },
        {
            "query": "인벤토리에서 아이템 추가",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": None,
            "expected_symbol": "AddItem",
            "description": "Inventory.cs - 기본 검색"
        },
        {
            "query": "레벨업 이벤트 발생",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": None,
            "expected_symbol": "OnLevelUp",
            "description": "LevelSystem.cs - 기본 검색"
        },
        # === 언어 필터 적용 테스트 ===
        {
            "query": "플레이어 이동 함수",
            "top_k": 5,
            "language": "cpp",
            "symbol_type": None,
            "project": None,
            "expected_symbol": "MovePlayer",
            "description": "C++ 언어 필터 - 함수 검색"
        },
        {
            "query": "인벤토리 클래스 정의",
            "top_k": 5,
            "language": "cs",
            "symbol_type": None,
            "project": None,
            "expected_symbol": "Inventory",
            "description": "C# 언어 필터 - 클래스 검색"
        },
        {
            "query": "캐릭터 스탯 구조체 정의",
            "top_k": 5,
            "language": "cpp",
            "symbol_type": None,
            "project": None,
            "expected_symbol": "CharacterStats",
            "description": "C++ 언어 필터 - 구조체 검색"
        },
        # === 심볼 타입 필터 적용 테스트 ===
        {
            "query": "데미지 계산 함수",
            "top_k": 5,
            "language": None,
            "symbol_type": "function",
            "project": None,
            "expected_symbol": "CalculateDamage",
            "description": "함수 타입 필터 - 데이터 처리"
        },
        {
            "query": "아이템 관리 클래스",
            "top_k": 5,
            "language": None,
            "symbol_type": "class",
            "project": None,
            "expected_symbol": "Inventory",
            "description": "클래스 타입 필터 - 관리 시스템"
        },
        {
            "query": "캐릭터 스탯 데이터 구조",
            "top_k": 5,
            "language": None,
            "symbol_type": "struct",
            "project": None,
            "expected_symbol": "CharacterStats",
            "description": "구조체 타입 필터 - 데이터 구조"
        },
        # === 프로젝트 필터 적용 테스트 ===
        {
            "query": "애플리케이션 클래스",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": "project2",
            "expected_symbol": "App",
            "description": "project2 필터 - 앱 클래스"
        },
        {
            "query": "사용자 정보",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": "project2",
            "expected_symbol": "UserInfo",
            "description": "project2 필터 - 사용자 정보"
        },
        {
            "query": "데이터 분석기",
            "top_k": 5,
            "language": None,
            "symbol_type": None,
            "project": "project2",
            "expected_symbol": "DataAnalyzer",
            "description": "project2 필터 - 데이터 분석기"
        },
        # === 복합 필터 조합 테스트 ===
        {
            "query": "앱 구조",
            "top_k": 3,
            "language": "cpp",
            "symbol_type": "class",
            "project": "project2",
            "expected_symbol": "App",
            "description": "복합 필터 - C++ + class + project2"
        },
        {
            "query": "데이터 분석 함수",
            "top_k": 3,
            "language": "cpp",
            "symbol_type": "method",
            "project": "project2",
            "expected_symbol": "calculateStatistics",
            "description": "복합 필터 - C++ + method + project2"
        },
        {
            "query": "캐릭터 스탯 게임 데이터",
            "top_k": 10,
            "language": None,
            "symbol_type": None,
            "project": "project1",
            "expected_symbol": "CharacterStats",
            "description": "project1 프로젝트 - 게임 데이터 검색"
        },
        # === 언어별 심볼 타입 조합 테스트 ===
        {
            "query": "레벨 관리 시스템",
            "top_k": 5,
            "language": "cs",
            "symbol_type": "class",
            "project": None,
            "expected_symbol": "LevelSystem",
            "description": "C# 클래스 필터 조합"
        },
        {
            "query": "네트워크 접속 실패 처리 함수",
            "top_k": 5,
            "language": "cpp",
            "symbol_type": "method",
            "project": None,
            "expected_symbol": "HandleConnectionFailure",
            "description": "C++ 메서드 필터 조합"
        },
    ]

    child = CodeIndexProcess()
    pid = child.run(None, wait=False)
    if pid is None:
        log_error("MCP 서버 시작 실패")
        return False

    try:
        with Timer("쿼리 배치 실행"):
            results: List[Dict[str, Any]] = []
            for i, test_case in enumerate(queries, 1):
                query    = test_case["query"]
                tc_top_k = test_case.get("top_k", 5)
                lang     = test_case.get("language") or ""
                sym_type = test_case.get("symbol_type") or ""
                project  = test_case.get("project") or ""

                result = child.search_code(query, top_k=tc_top_k, language=lang, symbol_type=sym_type, project=project)
                if result is None:
                    log_error(f"쿼리 [{i}] 응답 없음 (타임아웃 또는 프로세스 종료)")
                    results.append({"results": []})
                    continue

                # search_code()는 이미 파싱된 List[Dict]를 반환
                log_info(f"쿼리 [{i}] 검색 결과: {len(result)}건")
                for j, item in enumerate(result, 1):
                    log_info(
                        f"  [{j}] {item.get('symbol_name', '')} ({item.get('symbol_type', '')})"
                        f" | {item.get('file_path', '')} L{item.get('start_line', '')}-{item.get('end_line', '')}"
                        f" | {item.get('language', '')} | {item.get('project_name', '')} | score={item.get('score', '')}"
                    )

                results.append({"results": result.results})

            log_info(f"쿼리 배치 완료: {len(results)}개 처리")

        passed, total = report(queries, results)
        accuracy_success = passed >= int(total * 0.8)  # 80% 이상 통과면 성공

        return accuracy_success
    except Exception as e:
        log_error(f"MCP 쿼리 실행 중 예외: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        child.kill()
        
def report(queries: List[Dict[str, Any]], query_results: List[Dict[str, Any]]) -> Tuple[int, int]:
    """테스트 결과를 분석하고 리포트를 출력합니다."""
    passed = failed = 0
    fail_details = []
    success_details = []

    print("\n" + "=" * 72)
    print(f"{'#':<3} {'결과':<6} {'순위':<4} {'예상 심볼':<28} {'쿼리'} [필터]")
    print("=" * 72)

    for i, (test_case, item) in enumerate(
        zip(queries, query_results), 1
    ):
        query = test_case["query"]
        expected = test_case["expected_symbol"]
        top_k = test_case["top_k"]
        description = test_case["description"]
        
        # 필터 정보 추출
        filters = []
        if test_case.get("language"):
            filters.append(f"lang:{test_case['language']}")
        if test_case.get("symbol_type"):
            filters.append(f"type:{test_case['symbol_type']}")
        if test_case.get("project"):
            filters.append(f"proj:{test_case['project']}")
        filter_str = ",".join(filters) if filters else "없음"
        
        results = item.get("results", [])
        ok, rank = SearchResult(results).hit(expected)

        mark = "PASS" if ok else "FAIL"
        icon = "✓" if ok else "✗"
        rank_str = f"#{rank}" if ok else "N/A"
        
        query_short = query[:25] + "..." if len(query) > 25 else query
        print(f"{i:<3} {icon} {mark:<4}  {rank_str:<4} {expected:<28} {query_short:<29} [{filter_str}]")

        if ok:
            passed += 1
            success_details.append((i, query, expected, description, rank, filter_str))
        else:
            failed += 1
            top3 = []
            for r in results[:3]:
                symbol = r.get("symbol_name", "")
                if not symbol:
                    # 심볼명이 없는 경우 content에서 첫 번째 라인 추출
                    content_lines = r.get("content", "").strip().split('\n')
                    symbol = content_lines[0][:30] + ("..." if len(content_lines[0]) > 30 else "") if content_lines else "(no content)"
                top3.append(symbol)
            fail_details.append((i, query, expected, description, top3, filter_str))

    print("=" * 72)
    total = len(queries)
    pct = passed * 100 // total if total else 0

    if passed == total:
        log_info(f"🎉 모든 테스트 통과! {passed}/{total} 성공 (100%)")
    else:
        log_info(f"결과: {passed}/{total} 통과 ({pct}%)")
    
    # 성공한 케이스 상세 정보 (verbose 모드에서만)
    if success_details:
        print("\n── 성공 상세 ──────────────────────────────")
        for no, q, exp, desc, rank, filter_info in success_details[:5]:  # 상위 5개만 표시
            print(f"  [✓ {no}] {desc} (순위 #{rank})")
            print(f"       쿼리: {q}")
            print(f"       발견: {exp}")
            print(f"       필터: {filter_info}")
        if len(success_details) > 5:
            print(f"  ... 및 {len(success_details) - 5}개 추가 성공")

    # 실패한 케이스 상세 정보
    if fail_details:
        print("\n── 실패 상세 ──────────────────────────────")
        for no, q, exp, desc, top3, filter_info in fail_details:
            print(f"  [✗ {no}] {desc}")
            print(f"       쿼리: {q}")
            print(f"       예상: {exp}")
            print(f"       실제: {', '.join(top3) if top3 else '(결과 없음)'}")
            print(f"       필터: {filter_info}")
        
        print(f"\n💡 개선 제안:")
        print("  - 예상 심볼명이 정확한지 확인")
        print("  - 테스트 데이터에 해당 심볼이 실제 존재하는지 확인")
        print("  - 필터 조합이 올바른지 확인")
        print("  - top_k 값을 늘려서 재시도")

    return passed, total