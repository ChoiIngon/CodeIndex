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
from test_suite.test_search_code import test_search_code
from test_suite.test_exec_options import test_exec_options
from test_suite.test_source_path_removal import test_source_path_removal
from test_suite.test_get_chunk import test_get_chunk
from test_suite.test_get_file_outline import test_get_file_outline
from test_suite.test_project_deletion import test_project_deletion
from test_suite.test_data_cleanup import test_data_cleanup
from test_suite.test_incremental_update import test_incremental_update
from test_suite.test_exclude_patterns import test_exclude_patterns

# ── 경로 ─────────────────────────────────────────────────────────────────────
ROOT           = Path(__file__).parent.parent.resolve()   # C:\GitRoot\CodeIndex

SETTINGS       = ROOT / "config" / "settings.json"
SETTINGS_TEMPLATE = ROOT / "config" / "settings.json.template"
SETTINGS_TMP   = ROOT / "config" / "settings.json.tmp"
DATA_DIR       = ROOT / "data"
DATA_BACKUP    = ROOT / "data.tmp"

# ── CLI 테스트 모드 ──────────────────────────────────────────────────────────────
_VERBOSE           = "--verbose" in sys.argv

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """메인 함수: 전체 테스트 수트를 순차적으로 실행합니다."""
    backup_needed = setup_test_settings()
    if not backup_needed:
        log_error("설정 준비 실패")
        sys.exit(1)
    data_backup_needed = backup_data_directory()

    test_cases = [
        #("실행 옵션 테스트",           test_exec_options),
        #("코드 검색 정확도 테스트",     test_search_code),
        #("파일 아웃라인 조회 테스트",   test_get_file_outline),
        #("청크 조회 테스트",            test_get_chunk),
        #("증분 업데이트 테스트",        test_incremental_update),
        #("데이터 정리 테스트",          test_data_cleanup),
        #("소스 경로 제거 테스트",       test_source_path_removal),
        #("프로젝트 삭제 테스트",        test_project_deletion),
        ("제외 패턴 테스트",            test_exclude_patterns),
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


if __name__ == "__main__":
    main()