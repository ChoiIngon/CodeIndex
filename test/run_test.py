"""
CodeIndex 정확도 테스트

사용법:
    cd C:\CodeIndex
    python test/run_test.py

동작:
    1. config/settings.json 의 source_paths 에 test/data 가 없으면 추가
    2. python code_index --index-only 실행 (의존성 설치, 모델 다운, 인덱싱)
    3. python code_index --query-batch 로 10개 쿼리 일괄 실행
    4. 예상 심볼이 top-K 결과 안에 있는지 판정 후 리포트 출력
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── 경로 ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent.resolve()   # C:\CodeIndex
TEST_DATA  = (ROOT / "test" / "data").as_posix()
SETTINGS   = ROOT / "config" / "settings.json"

# ── 테스트 케이스 ─────────────────────────────────────────────────────────────
# (query, expected_symbol, top_k, description)
TEST_CASES = [
    ("플레이어 이동 처리 함수",        "MovePlayer",              5, "player.h"),
    ("데미지 계산 로직",               "CalculateDamage",         5, "combat.cpp"),
    ("인벤토리에서 아이템 검색",        "FindItem",                5, "Inventory.cs"),
    ("몬스터 스폰 생성",               "SpawnMonster",            5, "monster.cpp"),
    ("서버 연결 실패 처리",             "HandleConnectionFailure", 5, "network.h"),
    ("아이템 드롭 확률 계산",           "CalculateDropRate",       5, "ItemDrop.cs"),
    ("오브젝트 풀 재사용",             "ObjectPool",              5, "object_pool.h"),
    ("레벨업 이벤트 발생 및 보상 지급",   "OnLevelUp",               5, "LevelSystem.cs"),
    ("로그 출력 인터페이스",            "ILogger",                 5, "Logger.cs"),
    ("캐릭터 스탯 구조체 정의",         "CharacterStats",          5, "character_stats.h"),
    # 청크 분할 테스트: 80라인 초과 심볼이 여러 청크로 분할되어도 검색 가능한지 확인
    ("스킬 체인 처리 및 콤보 배율 계산", "ProcessSkillChain",        5, "skill_processor.cpp"),
]


# ── 1. settings.json 에 test/data 추가 ────────────────────────────────────────

def ensure_test_data_in_settings() -> None:
    with open(SETTINGS, encoding="utf-8-sig") as f:
        settings = json.load(f)

    paths = settings.setdefault("indexer", {}).setdefault("source_paths", [])
    normalized = [Path(p).as_posix() for p in paths]

    if TEST_DATA not in normalized:
        paths.append(TEST_DATA)
        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        print(f"[설정] test/data 경로 추가: {TEST_DATA}")
    else:
        print(f"[설정] test/data 이미 포함됨")


# ── 2. 인덱싱 실행 ────────────────────────────────────────────────────────────

def run_indexing() -> bool:
    print("\n[인덱싱] python code_index --index-only 실행 중...\n")
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "code_index", "--index-only"],
        cwd=str(ROOT),
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        print(f"\n[오류] 인덱싱 실패 (exit={proc.returncode})")
        return False
    print(f"\n[인덱싱] 완료 ({elapsed:.1f}s)")
    return True


# ── 3. 쿼리 배치 실행 ─────────────────────────────────────────────────────────

def run_queries(top_k: int = 20) -> list[dict] | None:
    queries_input = json.dumps([
        {"query": q, "top_k": top_k}
        for q, _, _, _ in TEST_CASES
    ], ensure_ascii=False)

    print("\n[검색] 쿼리 배치 실행 중...")
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "code_index", "--query-batch", "--top-k", str(top_k)],
        cwd=str(ROOT),
        input=queries_input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - t0

    if proc.returncode != 0:
        print(f"[오류] 쿼리 실행 실패 (exit={proc.returncode})")
        err = (proc.stderr[-2000:] if proc.stderr else "").replace('\ufffd', '?')
        print(err)
        return None

    print(f"[검색] 완료 ({elapsed:.1f}s)\n")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"[오류] 결과 파싱 실패: {e}")
        print("stdout:", proc.stdout[:500])
        return None


# ── 4. 결과 판정 및 리포트 ────────────────────────────────────────────────────

def _hit(results: list[dict], expected: str, top_k: int) -> bool:
    for r in results[:top_k]:
        if expected.lower() in r.get("symbol_name", "").lower():
            return True
        if expected.lower() in r.get("content", "").lower():
            return True
    return False


def report(query_results: list[dict]) -> tuple[int, int]:
    passed = failed = 0
    fail_details = []

    print("=" * 72)
    print(f"{'#':<3} {'결과':<6} {'예상 심볼':<28} {'쿼리'}")
    print("=" * 72)

    for i, ((query, expected, top_k, src), item) in enumerate(
        zip(TEST_CASES, query_results), 1
    ):
        results = item.get("results", [])
        ok = _hit(results, expected, top_k)

        mark  = "PASS" if ok else "FAIL"
        icon  = "O" if ok else "X"
        print(f"{i:<3} {icon} {mark:<4}  {expected:<28} {query}  [{src}]")

        if ok:
            passed += 1
        else:
            failed += 1
            top3 = [r.get("symbol_name") or "(no symbol)" for r in results[:3]]
            fail_details.append((i, query, expected, src, top3))

    print("=" * 72)
    pct = passed * 100 // len(TEST_CASES)
    print(f"\n결과: {passed}/{len(TEST_CASES)} 통과  ({pct}%)\n")

    if fail_details:
        print("── 실패 상세 ──────────────────────────────")
        for no, q, exp, src, top3 in fail_details:
            print(f"  [{no}] {src}")
            print(f"       쿼리  : {q}")
            print(f"       예상  : {exp}")
            print(f"       top-3 : {top3}")
        print()

    return passed, len(TEST_CASES)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ensure_test_data_in_settings()

    if not run_indexing():
        sys.exit(1)

    results = run_queries(top_k=20)
    if results is None:
        sys.exit(1)

    passed, total = report(results)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
