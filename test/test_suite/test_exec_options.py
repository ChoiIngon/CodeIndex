from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import Timer, log_error, log_info
from code_index import CodeIndexProcess

ROOT = Path(__file__).parent.parent.parent.resolve()


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
                returncode, _ = child.run(option, wait=True)

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