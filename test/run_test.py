"""
CodeIndex 통합 테스트 수트

사용법:
    python test/run_test.py [--verbose]

모드:
    (기본값): 전체 테스트 수트 순차 실행
        1. 실행 옵션 테스트 (CLI 옵션들 정상 동작 확인)
        2. 코드 검색 정확도 테스트 (다양한 필터 조합 포함)
        3. 증분 업데이트 테스트 (파일 수정 반영 확인)
        4. 데이터 정리 테스트 (파일 삭제 반영 확인)
        5. 소스 경로 제거 테스트 (프로젝트 내 일부 디렉토리 제거 확인)
        6. 프로젝트 삭제 테스트 (설정 없는 프로젝트 제거 확인)
        
    --verbose: 상세한 로그 출력 및 성능 측정
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from code_index import CodeIndexProcess
# ── 경로 ─────────────────────────────────────────────────────────────────────
ROOT           = Path(__file__).parent.parent.resolve()   # C:\GitRoot\CodeIndex

SETTINGS       = ROOT / "config" / "settings.json"
SETTINGS_TEMPLATE = ROOT / "config" / "settings.json.template"
SETTINGS_TMP   = ROOT / "config" / "settings.json.tmp"
DATA_DIR       = ROOT / "data"
DATA_BACKUP    = ROOT / "data.tmp"

# ── CLI 테스트 모드 ──────────────────────────────────────────────────────────────
_VERBOSE           = "--verbose" in sys.argv

# ── 로깅 유틸리티 ───────────────────────────────────────────────────────────────
def log_info(msg: str, prefix: str = "정보") -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{prefix}] {msg}")

def log_error(msg: str, prefix: str = "오류") -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{prefix}] {msg}", file=sys.stderr)

def log_verbose(msg: str, prefix: str = "상세") -> None:
    if _VERBOSE:
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] [{prefix}] {msg}")

# ── 성능 측정 유틸리티 ──────────────────────────────────────────────────────────
class Timer:
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        log_verbose(f"{self.name} 시작...")
        return self
    
    def __exit__(self, *args):
        if self.start_time:
            elapsed = time.time() - self.start_time
            log_info(f"{self.name} 완료 ({elapsed:.2f}s)")

# ── 1. settings.json 테스트용 설정 및 복원 관리 ─────────────────────────────────

def setup_test_settings() -> bool:
    """
    테스트용 settings.json을 준비합니다.
    
    Returns:
        bool: 기존 settings.json이 존재했는지 여부 (복원 필요 여부)
    """
    try:
        backup_needed = False
        
        if not SETTINGS_TEMPLATE.exists():
            log_error(f"템플릿 파일이 없습니다: {SETTINGS_TEMPLATE}")
            return False
        
        # 기존 settings.json이 있으면 백업
        if SETTINGS.exists():
            log_info(f"기존 settings.json을 백업합니다")
            log_verbose(f"백업 경로: {SETTINGS_TMP}")
            # 기존 백업 파일이 있으면 삭제 후 백업
            if SETTINGS_TMP.exists():
                SETTINGS_TMP.unlink()
            SETTINGS.rename(SETTINGS_TMP)
            backup_needed = True
        
        # 템플릿을 복사하여 settings.json 생성
        log_info("템플릿에서 설정 파일을 복사합니다")
        with open(SETTINGS_TEMPLATE, encoding="utf-8-sig") as f:
            settings = json.load(f)
        
        # indexer에서 다른 프로젝트들 제거하고 테스트 프로젝트들만 남기기
        indexer_config = settings.get("indexer", {})
        
        # chunk 관련 설정 보존
        chunk_settings = {}
        for key in ["chunk_min_lines", "chunk_max_lines", "chunk_overlap_lines", "chunk_workers"]:
            if key in indexer_config:
                chunk_settings[key] = indexer_config[key]
                log_verbose(f"chunk 설정 보존: {key}={indexer_config[key]}")
        
        # 테스트 프로젝트 설정
        test_projects = {
            "project1": {
                "source_paths": [(ROOT / "test" / "project1").as_posix()],
                "extensions": [".h", ".c", ".cpp", ".cs"],
                "exclude_patterns": []
            },
            "project2": {
                "source_paths": [(ROOT / "test" / "project2_1").as_posix(), (ROOT / "test" / "project2_2").as_posix()],
                "extensions": [".cpp", ".h", ".cs"],
                "exclude_patterns": []
            }
        }
        
        # indexer를 새로 구성
        settings["indexer"] = {**chunk_settings, **test_projects}
        
        # 수정된 설정을 저장
        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        
        return backup_needed
    
    except Exception as e:
        log_error(f"테스트 설정 준비 중 오류 발생: {e}")
        return False


def restore_settings(backup_existed: bool) -> None:
    """
    테스트 후 원래 settings.json을 복원합니다.
    
    Args:
        backup_existed: 백업 파일이 존재하는지 여부
    """
    try:
        if backup_existed and SETTINGS_TMP.exists():
            log_info("백업된 settings.json을 복원합니다")
            if SETTINGS.exists():
                SETTINGS.unlink()  # 현재 파일 삭제
            SETTINGS_TMP.rename(SETTINGS)  # 백업 파일을 원래 이름으로 변경
        else:
            # 백업이 없었으면 테스트용 파일 삭제
            if SETTINGS.exists():
                log_info("테스트용 settings.json을 삭제합니다")
                SETTINGS.unlink()
    
    except Exception as e:
        log_error(f"설정 파일 복원 중 오류 발생: {e}")


# ── data 디렉토리 백업 및 복원 관리 ────────────────────────────────────────────

def backup_data_directory() -> bool:
    """
    기존 data 디렉토리를 data.tmp로 백업합니다.
    
    Returns:
        bool: 기존 data 디렉토리가 존재했는지 여부 (복원 필요 여부)
    """
    try:
        backup_needed = False
        
        # 기존 백업 파일이 있으면 삭제
        if DATA_BACKUP.exists():
            log_info("기존 백업 디렉토리를 삭제합니다")
            log_verbose(f"삭제 경로: {DATA_BACKUP}")
            shutil.rmtree(DATA_BACKUP)
        
        # 기존 data 디렉토리가 있으면 백업
        if DATA_DIR.exists():
            log_info("기존 data 디렉토리를 백업합니다")
            log_verbose(f"백업 경로: {DATA_DIR} → {DATA_BACKUP}")
            shutil.move(str(DATA_DIR), str(DATA_BACKUP))
            backup_needed = True
        else:
            log_info("기존 data 디렉토리가 없습니다")
        
        return backup_needed
    
    except Exception as e:
        log_error(f"데이터 디렉토리 백업 중 오류 발생: {e}")
        return False


def restore_data_directory(backup_existed: bool) -> None:
    """
    테스트 후 data 디렉토리를 복원합니다.
    
    Args:
        backup_existed: 백업 디렉토리가 존재하는지 여부
    """
    try:
        # 테스트로 생성된 data 디렉토리 삭제
        if DATA_DIR.exists():
            log_info("테스트로 생성된 data 디렉토리를 삭제합니다")
            shutil.rmtree(DATA_DIR)
        
        # 백업이 있었으면 복원
        if backup_existed and DATA_BACKUP.exists():
            log_info("백업된 data 디렉토리를 복원합니다")
            log_verbose(f"복원 경로: {DATA_BACKUP} → {DATA_DIR}")
            shutil.move(str(DATA_BACKUP), str(DATA_DIR))
        else:
            log_info("복원할 백업이 없습니다")
        
        # 백업 파일이 남아있으면 삭제 (정리)
        if DATA_BACKUP.exists():
            log_verbose("잔여 백업 파일을 삭제합니다")
            shutil.rmtree(DATA_BACKUP)
    
    except Exception as e:
        log_error(f"데이터 디렉토리 복원 중 오류 발생: {e}")

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

                results.append({"results": result})

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

def test_exec_options() -> bool:
    test_file_path = (ROOT / "test" / "project1" / "character_stats.h").as_posix()
    options = [
        ("--help 옵션",             ["--help"]),
        ("--index-only 옵션",        ["--index-only"]),
        ("--status 옵션",            ["--status"]),
        ("--search-code 옵션",       ["--search-code", "test"]),
        ("--get-file-outline 옵션",  ["--get-file-outline", test_file_path]),
        ("--get-chunk 옵션",         ["--get-chunk", "dummy-chunk-id"]),
    ]
    
    with Timer("실행 옵션 테스트"):
        results = []
        for name, option in options:
            try:
                log_info(f"{name} 테스트 시작...")
                child = CodeIndexProcess()
                returncode = child.run(option, wait=True)

                if returncode is None:
                    success = False
                    msg = "프로세스 시작 실패"
                elif returncode == 0:
                    success = True
                    msg = f"성공 (returncode={returncode})"
                else:
                    success = False
                    # stderr 마지막 줄에서 원인 추출
                    stderr_tail = child.last_stderr.strip().splitlines()
                    cause = next((l.strip() for l in reversed(stderr_tail) if l.strip()), "")
                    msg = f"실패 (returncode={returncode}): {cause[:80]}" if cause else f"실패 (returncode={returncode})"

                results.append((name, success, msg))
                log_info(f"{name} 테스트 {'성공' if success else '실패'}: {msg}")
            except subprocess.TimeoutExpired:
                results.append((name, False, "시간 초과 (300초)"))
                log_info(f"{name} 테스트 시간 초과")
            except Exception as e:
                results.append((name, False, f"예외 발생: {e}"))
                log_info(f"{name} 테스트 예외: {e}")
    
    # 결과 정렬 (원래 순서로)
    test_order = {name: i for i, (name, _) in enumerate(options)}
    results.sort(key=lambda x: test_order.get(x[0], 999))
    
    # 결과 출력
    passed = 0
    total = len(results)
    
    print("\n" + "=" * 72)
    print(f"{'#':<3} {'결과':<6} {'테스트':<25} {'설명'}")
    print("=" * 72)
    
    for i, (name, success, msg) in enumerate(results, 1):
        status = "PASS" if success else "FAIL"
        icon = "✓" if success else "✗"
        print(f"{i:<3} {icon} {status:<4}  {name:<25} {msg}")
        if success:
            passed += 1
    
    print("=" * 72)
    pct = passed * 100 // total if total > 0 else 0
    log_info(f"실행 옵션 테스트 결과: {passed}/{total} 통과 ({pct}%)")
    
    if passed != total:
        log_error(f"실행 옵션 테스트 실패: {passed}/{total} 통과")
        return False
    log_info("✅ 실행 옵션 테스트 통과!")
    return True

def _hit(results: List[Dict[str, Any]], expected: str, top_k: int) -> Tuple[bool, int]:
    """결과에서 예상 심볼이 발견되는지 확인합니다."""
    for i, r in enumerate(results[:top_k]):
        symbol_name = r.get("symbol_name", "").lower()
        content = r.get("content", "").lower()
        expected_lower = expected.lower()
        
        if expected_lower in symbol_name or expected_lower in content:
            return True, i + 1  # 발견된 순위 반환
    
    return False, -1

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
        ok, rank = _hit(results, expected, top_k)

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
    if _VERBOSE and success_details:
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

def test_source_path_removal() -> bool:
    """소스 경로 제거 테스트 (프로젝트 내 일부 디렉토리 삭제)"""
    log_info("소스 경로 제거 테스트를 시작합니다...")

    child = None
    settings_backup = None
    try:
        # 1단계: 초기 상태에서 project2_2 내용 검색 확인
        log_verbose("1단계: project2_2 내용 검색 확인")

        project2_2_keywords = ["Server", "Frontend", "NetworkManager"]
        found_before = []

        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("초기 MCP 서버 시작 실패")
            return False

        for keyword in project2_2_keywords:
            result = child.search_code(keyword, top_k=5, project="project2")
            if result is None:
                log_error(f"키워드 '{keyword}' 검색 중 오류 발생")
                return False
            found, _ = _hit(result, keyword, len(result))
            if found:
                found_before.append(keyword)
                log_verbose(f"project2_2 키워드 '{keyword}' 검색 확인")

        child.kill()
        child = None

        if not found_before:
            log_error("project2_2 관련 데이터를 찾을 수 없어 테스트를 중단합니다")
            return False

        # 2단계: settings.json에서 project2_2 경로 제거
        log_verbose("2단계: settings.json에서 project2_2 경로 제거")

        with open(SETTINGS, "r", encoding="utf-8-sig") as f:
            settings_backup = json.load(f)

        settings = json.loads(json.dumps(settings_backup))  # 깊은 복사
        if "project2" in settings.get("indexer", {}):
            project2_config = settings["indexer"]["project2"]
            original_paths = project2_config.get("source_paths", [])
            project2_2_path = (ROOT / "test" / "project2_2").as_posix()
            filtered_paths = [p for p in original_paths if project2_2_path not in p]

            if len(filtered_paths) < len(original_paths):
                project2_config["source_paths"] = filtered_paths
                log_verbose(f"project2 source_paths: {original_paths} → {filtered_paths}")
            else:
                log_error("project2_2 경로를 찾을 수 없습니다")
                return False

        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        # 3단계: 증분 업데이트 + 검색 확인 (run()은 변경분 재인덱싱 후 MCP 서버 시작)
        log_verbose("3단계: 증분 업데이트 (source_paths 변경 반영) 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("증분 업데이트/MCP 서버 시작 실패")
            return False

        # 4단계: project2_2 키워드가 제거되었는지 확인
        log_verbose("4단계: project2_2 내용 검색 불가 확인")
        removed_count = 0
        for keyword in found_before:
            result = child.search_code(keyword, top_k=5, project="project2")
            if result is None:
                log_error(f"키워드 '{keyword}' 검색 중 오류 발생")
                return False
            found, _ = _hit(result, keyword, len(result))
            if found:
                log_error(f"제거된 경로의 키워드 '{keyword}'이 여전히 검색됨")
            else:
                removed_count += 1
                log_verbose(f"project2_2 키워드 '{keyword}' 정상적으로 제거됨")

        # 5단계: project2_1 내용은 여전히 검색되는지 확인
        log_verbose("5단계: project2_1 내용 정상 작동 확인")
        project2_1_keywords = ["DataAnalyzer", "DataPipeline"]
        for keyword in project2_1_keywords:
            result = child.search_code(keyword, top_k=5, project="project2")
            if result is None:
                log_error(f"project2_1 키워드 '{keyword}' 검색 중 오류 발생")
                return False
            found, _ = _hit(result, keyword, len(result))
            if not found:
                log_error(f"project2_1 키워드 '{keyword}' 검색 실패 - project2_1 데이터가 손상되었을 가능성")
                return False

        child.kill()
        child = None

        # 6단계: settings.json 복원
        log_verbose("6단계: settings.json 복원")
        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings_backup, f, indent=2, ensure_ascii=False)
        settings_backup = None

        # 결과 판정: 대부분의 project2_2 키워드가 제거되었으면 성공
        success_rate = removed_count / len(found_before) if found_before else 0
        if success_rate >= 0.8:
            log_info(f"소스 경로 제거 테스트가 성공적으로 완료되었습니다 ({removed_count}/{len(found_before)} 제거)")
            return True
        else:
            log_error(f"소스 경로 제거 테스트 실패: {removed_count}/{len(found_before)} 제거 (80% 미만)")
            return False

    except Exception as e:
        log_error(f"소스 경로 제거 테스트 중 예외 발생: {e}")
        return False
    finally:
        if child is not None:
            child.kill()
        if settings_backup is not None:
            try:
                with open(SETTINGS, "w", encoding="utf-8-sig") as f:
                    json.dump(settings_backup, f, indent=2, ensure_ascii=False)
            except Exception as restore_error:
                log_error(f"settings.json 복원 실패: {restore_error}")

def test_incremental_update() -> bool:
    """증분 업데이트 테스트"""
    log_info("증분 업데이트 테스트를 시작합니다...")
    
    child = None
    try:
        # 테스트 파일 경로
        test_file = ROOT / "test" / "project1" / "test_update.cpp"
        
        # 1단계: 새 파일 생성
        log_verbose("1단계: 새 파일 생성")
        test_content_v1 = '''// 테스트용 업데이트 파일 - C++
#include <string>
#include <iostream>

class TestClass {
public:
    std::string testFunction() {
        return "version 1";
    }
    
    int getValue() {
        return value;
    }
    
private:
    int value = 1;
};'''
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content_v1)
        
        # 2단계: 초기 인덱싱 + 검색 확인 (run()은 인덱싱 후 MCP 서버 시작)
        log_verbose("2단계: 초기 인덱싱 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("초기 인덱싱/MCP 서버 시작 실패")
            return False
        
        result = child.search_code("version 1", top_k=5)
        child.kill()
        child = None
        
        hit, rank = _hit(result, "version 1", len(result))
        if not hit:
            log_error("초기 내용 검색 실패")
            return False
        
        # 3단계: 파일 수정
        log_verbose("3단계: 파일 수정")
        test_content_v2 = '''// 테스트용 업데이트 파일 - C++ (수정됨)
#include <string>
#include <iostream>

class TestClass {
public:
    std::string testFunction() {
        return "version 2 updated";
    }
    
    bool newFunction() {
        return true;
    }
    
    int getValue() {
        return value;
    }
    
    std::string getNewField() {
        return newField;
    }
    
private:
    int value = 2;
    std::string newField = "added";
};

struct NewInterface {
    std::string id;
    std::string name;
};'''
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content_v2)
        
        # 4단계: 증분 업데이트 + 검색 확인 (run()은 변경분 재인덱싱 후 MCP 서버 시작)
        log_verbose("4단계: 증분 업데이트 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("증분 업데이트/MCP 서버 시작 실패")
            return False
        
        # 새로운 내용 검색
        result_v2 = child.search_code("version 2 updated", top_k=5)
        if not result_v2:
            log_error("새로운 내용 검색 실패")
            return False
        
        # 이전 내용이 검색되지 않는지 확인
        result_v1 = child.search_code("version 1", top_k=5)
        child.kill()
        child = None
        
        if result_v1 and any(
            "version 1" in r.get("content", "") and "version 2" not in r.get("content", "")
            for r in result_v1
        ):
            log_error("이전 내용이 여전히 검색됨 - 증분 업데이트 실패")
            return False
        
        # 5단계: 정리
        test_file.unlink(missing_ok=True)
        
        log_info("증분 업데이트 테스트가 성공적으로 완료되었습니다")
        return True

    except Exception as e:
        log_error(f"증분 업데이트 테스트 중 예외 발생: {e}")
        if 'test_file' in locals():
            Path(test_file).unlink(missing_ok=True)
        return False
    finally:
        if child is not None:
            child.kill()


def test_data_cleanup() -> bool:
    """데이터 정리 테스트 (파일 삭제 시)"""
    log_info("데이터 정리 테스트를 시작합니다...")

    child = None
    try:
        # 테스트 파일 경로
        test_file = ROOT / "test" / "project2_1" / "test_cleanup.cpp"
        
        # 1단계: 테스트 파일 생성
        log_verbose("1단계: 테스트 파일 생성")
        test_content = '''// 테스트용 정리 파일 - C++
#include <string>
#include <iostream>

namespace TestCleanup {
    
    std::string cleanup_test_function() {
        // 이 함수는 삭제 테스트용입니다
        return "cleanup_test_marker_unique_string";
    }
    
    class CleanupTestClass {
    public:
        CleanupTestClass() {
            marker = "cleanup_test_class_marker";
        }
        
        std::string get_marker() const {
            return marker;
        }
        
    private:
        std::string marker;
    };
    
    // 고유 식별자
    const std::string CLEANUP_MARKER = "very_unique_cleanup_marker_12345";
    
    void initialize_cleanup_test() {
        CleanupTestClass testObj;
        std::cout << "Cleanup test initialized: " << testObj.get_marker() << std::endl;
    }
    
} // namespace TestCleanup'''
        
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)
        
        # 2단계: 인덱싱 + 검색 확인 (run()은 인덱싱 후 MCP 서버 시작)
        log_verbose("2단계: 파일 포함하여 인덱싱 및 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("인덱싱/MCP 서버 시작 실패")
            return False

        result = child.search_code("cleanup_test_marker_unique_string", top_k=5)
        child.kill()
        child = None

        # result가 None이면 오류, 빈 리스트이면 검색 결과 없음, 키워드가 실제로 포함된 결과가 있어야 성공
        if result is None:
            log_error("초기 내용 검색 중 오류 발생 (타임아웃 또는 프로세스 종료)")
            return False
        found, _ = _hit(result, "cleanup_test_marker_unique_string", len(result))
        if not found:
            log_error("초기 내용 검색 실패 - 키워드가 검색 결과에 없음")
            return False
        
        # 3단계: 파일 삭제
        log_verbose("3단계: 테스트 파일 삭제")
        test_file.unlink()
        
        # 4단계: 증분 업데이트 + 삭제 반영 확인 (run()은 변경분 재인덱싱 후 MCP 서버 시작)
        log_verbose("4단계: 증분 업데이트 (삭제 반영) 및 검색 불가 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("증분 업데이트/MCP 서버 시작 실패")
            return False

        result_after = child.search_code("cleanup_test_marker_unique_string", top_k=5)
        if result_after is None:
            log_error("삭제 후 검색 중 오류 발생 (타임아웃 또는 프로세스 종료)")
            return False
        found_after, _ = _hit(result_after, "cleanup_test_marker_unique_string", len(result_after))
        if found_after:
            log_error("삭제된 파일의 내용이 여전히 검색됨 - 데이터 정리 실패")
            return False

        # 다른 고유 마커들도 확인
        markers = ["cleanup_test_class_marker", "very_unique_cleanup_marker_12345"]
        for marker in markers:
            result_marker = child.search_code(marker, top_k=5)
            if result_marker is None:
                log_error(f"마커 '{marker}' 검색 중 오류 발생")
                return False
            found_marker, _ = _hit(result_marker, marker, len(result_marker))
            if found_marker:
                log_error(f"삭제된 파일의 마커 '{marker}'가 여전히 검색됨")
                return False

        child.kill()
        child = None

        log_info("데이터 정리 테스트가 성공적으로 완료되었습니다")
        return True
        
    except Exception as e:
        log_error(f"데이터 정리 테스트 중 예외 발생: {e}")
        if 'test_file' in locals():
            Path(test_file).unlink(missing_ok=True)
        return False
    finally:
        if child is not None:
            child.kill()


def test_project_deletion() -> bool:
    """프로젝트 삭제 테스트"""
    log_info("프로젝트 삭제 테스트를 시작합니다...")

    child = None
    settings_backup = None
    try:
        # 1단계: 초기 상태에서 project2 내용 검색 확인
        log_verbose("1단계: project2 내용 검색 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("초기 MCP 서버 시작 실패")
            return False

        result = child.search_code("DataAnalyzer", top_k=5, project="project2")
        if result is None:
            log_error("project2 내용 초기 검색 중 오류 발생")
            return False
        found, _ = _hit(result, "DataAnalyzer", len(result))
        if not found:
            log_error("project2 내용 초기 검색 실패 - DataAnalyzer가 검색 결과에 없음")
            return False
        log_verbose("project2 키워드 'DataAnalyzer' 검색 확인")

        child.kill()
        child = None

        # 2단계: settings.json에서 project2 제거
        log_verbose("2단계: settings.json에서 project2 제거")
        with open(SETTINGS, "r", encoding="utf-8-sig") as f:
            settings_backup = json.load(f)

        settings = json.loads(json.dumps(settings_backup))  # 깊은 복사
        if "project2" in settings.get("indexer", {}):
            del settings["indexer"]["project2"]
        else:
            log_error("settings.json에 project2가 없습니다")
            return False

        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        # 3단계: 증분 업데이트 + MCP 서버 시작
        log_verbose("3단계: 증분 업데이트 (프로젝트 삭제 반영) 및 MCP 서버 시작")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("증분 업데이트/MCP 서버 시작 실패")
            return False

        # 4단계: project2 필터 검색 시 결과 없음 확인
        log_verbose("4단계: project2 필터 검색 불가 확인")
        result_proj = child.search_code("DataAnalyzer", top_k=5, project="project2")
        if result_proj is None:
            log_error("project2 필터 검색 중 오류 발생")
            return False
        found_proj, _ = _hit(result_proj, "DataAnalyzer", len(result_proj))
        if found_proj:
            log_error("삭제된 프로젝트의 내용이 project2 필터 검색에서 여전히 나타남")
            return False
        log_verbose("project2 필터 검색 결과 없음 확인")

        # 5단계: 일반 검색에서도 project2 특정 심볼이 나타나지 않는지 확인
        log_verbose("5단계: 일반 검색에서 project2 심볼 제거 확인")
        project2_keywords = ["DataAnalyzer", "DataPipeline", "DataUtils"]
        for keyword in project2_keywords:
            result_kw = child.search_code(keyword, top_k=5)
            if result_kw is None:
                log_error(f"키워드 '{keyword}' 검색 중 오류 발생")
                return False
            found_kw, _ = _hit(result_kw, keyword, len(result_kw))
            if found_kw:
                log_error(f"삭제된 프로젝트의 키워드 '{keyword}'이 일반 검색에서 여전히 나타남")
                return False
            log_verbose(f"키워드 '{keyword}' 제거 확인")

        # 6단계: 다른 프로젝트(project1)는 여전히 검색되는지 확인
        log_verbose("6단계: project1 정상 작동 확인")
        result_p1 = child.search_code("MovePlayer", top_k=5, project="project1")
        if result_p1 is None:
            log_error("project1 검색 중 오류 발생")
            return False
        found_p1, _ = _hit(result_p1, "MovePlayer", len(result_p1))
        if not found_p1:
            log_error("project1의 내용이 검색되지 않음 - project1 데이터가 손상되었을 가능성")
            return False
        log_verbose("project1 키워드 'MovePlayer' 검색 확인")

        child.kill()
        child = None

        # 7단계: settings.json 복원
        log_verbose("7단계: settings.json 복원")
        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings_backup, f, indent=2, ensure_ascii=False)
        settings_backup = None

        log_info("프로젝트 삭제 테스트가 성공적으로 완료되었습니다")
        return True

    except Exception as e:
        log_error(f"프로젝트 삭제 테스트 중 예외 발생: {e}")
        return False
    finally:
        if child is not None:
            child.kill()
        if settings_backup is not None:
            try:
                with open(SETTINGS, "w", encoding="utf-8-sig") as f:
                    json.dump(settings_backup, f, indent=2, ensure_ascii=False)
            except Exception as restore_error:
                log_error(f"settings.json 복원 실패: {restore_error}")


def test_get_chunk() -> bool:
    """get_chunk 조회 테스트 (search_code 결과의 chunk_id로 청크 조회)"""
    log_info("get_chunk 조회 테스트를 시작합니다...")

    child = CodeIndexProcess()
    pid = child.run(None, wait=False)
    if pid is None:
        log_error("MCP 서버 시작 실패")
        return False

    try:
        # 1단계: search_code 로 chunk_id 수집
        log_verbose("1단계: search_code 로 chunk_id 수집")
        results = child.search_code("데미지 계산", top_k=5)
        if not results:
            log_error("search_code 결과 없음 - chunk_id 를 얻을 수 없습니다")
            return False

        chunk_ids = [r.get("chunk_id") for r in results if r.get("chunk_id")]
        if not chunk_ids:
            log_error("결과에 chunk_id 필드가 없습니다")
            return False
        log_verbose(f"수집된 chunk_id {len(chunk_ids)}건")

        # 2단계: 각 chunk_id 로 get_chunk 호출 및 검증
        log_verbose("2단계: chunk_id 로 get_chunk 호출 및 검증")
        all_passed = True
        for i, chunk_id in enumerate(chunk_ids, 1):
            chunk = child.get_chunk(chunk_id)
            if chunk is None:
                log_error(f"[{i}] chunk_id='{chunk_id}' 조회 실패")
                all_passed = False
                continue

            returned_id = chunk.get("chunk_id", "")
            if returned_id != chunk_id:
                log_error(f"[{i}] chunk_id 불일치: 요청={chunk_id}, 응답={returned_id}")
                all_passed = False
                continue

            required_fields = ["file_path", "language", "start_line", "end_line", "content"]
            missing = [f for f in required_fields if not chunk.get(f)]
            if missing:
                log_error(f"[{i}] 필수 필드 누락: {missing}")
                all_passed = False
                continue

            log_verbose(
                f"  [{i}] {chunk.get('symbol_name', '')} ({chunk.get('symbol_type', '')})"
                f" | {chunk.get('file_path', '')} L{chunk.get('start_line', '')}-{chunk.get('end_line', '')}"
            )

        # 3단계: 존재하지 않는 chunk_id 로 조회 시 None 반환 확인
        log_verbose("3단계: 잘못된 chunk_id 로 조회 시 None 반환 확인")
        invalid_chunk = child.get_chunk("00000000-0000-0000-0000-000000000000")
        if invalid_chunk is not None:
            log_error("잘못된 chunk_id 에 대해 None 이 아닌 값 반환")
            all_passed = False
        else:
            log_verbose("잘못된 chunk_id → None 정상 확인")

        if all_passed:
            log_info("get_chunk 조회 테스트가 성공적으로 완료되었습니다")
        return all_passed

    except Exception as e:
        log_error(f"get_chunk 조회 테스트 중 예외 발생: {e}")
        return False
    finally:
        child.kill()


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


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """메인 함수: 전체 테스트 수트를 순차적으로 실행합니다."""
    backup_needed = setup_test_settings()
    if not backup_needed:
        log_error("설정 준비 실패")
        sys.exit(1)
    data_backup_needed = backup_data_directory()

    test_cases = [
        ("실행 옵션 테스트",           test_exec_options),
        ("코드 검색 정확도 테스트",     test_search_code),
        ("파일 아웃라인 조회 테스트",   test_get_file_outline),
        ("청크 조회 테스트",            test_get_chunk),
        ("증분 업데이트 테스트",        test_incremental_update),
        ("데이터 정리 테스트",          test_data_cleanup),
        ("소스 경로 제거 테스트",       test_source_path_removal),
        ("프로젝트 삭제 테스트",        test_project_deletion),
    ]
    try:
        test_results = []
        for name, func in test_cases:
            print("\n" + "=" * 72)
            print(name)
            print("=" * 72)
            success = func()
            test_results.append((name, success))
            if success:
                log_info(f"✅ {name} 통과!")
            else:
                log_error(f"❌ {name} 실패")

        # 전체 결과 요약
        print("\n" + "=" * 72)
        print("전체 테스트 결과 요약")
        print("=" * 72)
        passed_count = sum(1 for _, s in test_results if s)
        total_count = len(test_results)
        for test_name, success in test_results:
            icon = "✅" if success else "❌"
            status = "PASS" if success else "FAIL"
            print(f"{icon} {status:<4} {test_name}")
        print("=" * 72)
        if passed_count == total_count:
            log_info(f"🎉 모든 테스트 통과! ({passed_count}/{total_count})")
        else:
            log_error(f"일부 테스트 실패: {passed_count}/{total_count} 통과")
        sys.exit(0 if passed_count == total_count else 1)
    except KeyboardInterrupt:
        log_error("사용자에 의해 테스트가 중단되었습니다")
        sys.exit(130)
    except Exception as e:
        log_error(f"예상치 못한 오류 발생: {e}")
        if _VERBOSE:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        # 항상 환경 복원
        restore_data_directory(data_backup_needed)
        restore_settings(backup_needed)

if __name__ == "__main__":
    main()