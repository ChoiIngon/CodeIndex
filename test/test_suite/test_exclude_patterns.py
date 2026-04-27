from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess

ROOT     = Path(__file__).parent.parent.parent.resolve()
SETTINGS = ROOT / "config" / "settings.json"


def test_exclude_patterns() -> bool:
    """exclude_patterns 테스트 (설정 추가/삭제에 따른 인덱싱 반영 확인)"""
    log_info("exclude_patterns 테스트를 시작합니다...")

    # 테스트에 사용할 패턴 및 검색 키워드
    # Logger.cs (project1)를 제외 패턴으로 지정 → ConsoleLogger / FileLogger 심볼이 사라져야 함
    EXCLUDE_PATTERN = "*/Logger.cs"
    SEARCH_KEYWORD  = "ConsoleLogger"
    TARGET_PROJECT  = "project1"

    child = None
    settings_backup = None
    try:
        # ── 1단계: 초기 인덱싱 ──────────────────────────────────────────────
        log_verbose("1단계: --index-only 로 초기 인덱싱")
        rc, _ = CodeIndexProcess().run("--index-only", wait=True)
        if rc != 0:
            log_error(f"초기 인덱싱 실패 (returncode={rc})")
            return False

        # ── 2단계: 인덱싱 상태 확인 (기준선) ────────────────────────────────
        log_verbose("2단계: --status 로 기준선 확인")
        status_before = _get_status_output()
        if status_before is None:
            log_error("기준선 status 획득 실패")
            return False
        files_before, chunks_before = _parse_status_counts(status_before)
        log_info(f"기준선: 파일={files_before}개, 청크={chunks_before}개")
        if files_before < 0 or chunks_before < 0:
            log_error("status 출력 파싱 실패")
            return False

        # ── 3단계: exclude_patterns 추가 ────────────────────────────────────
        log_verbose(f"3단계: {TARGET_PROJECT}에 exclude_pattern '{EXCLUDE_PATTERN}' 추가")
        with open(SETTINGS, "r", encoding="utf-8-sig") as f:
            settings_backup = json.load(f)

        settings = json.loads(json.dumps(settings_backup))
        proj_cfg = settings.get("indexer", {}).get(TARGET_PROJECT)
        if proj_cfg is None:
            log_error(f"settings.json에 '{TARGET_PROJECT}' 프로젝트가 없습니다")
            return False
        if EXCLUDE_PATTERN not in proj_cfg.setdefault("exclude_patterns", []):
            proj_cfg["exclude_patterns"].append(EXCLUDE_PATTERN)
        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        # ── 4단계: 증분 업데이트 + MCP 서버 시작 ──────────────────────────────
        log_verbose("4단계: --index-only 로 변경 사항 반영 (exclude_patterns 적용)")
        rc, _ = CodeIndexProcess().run("--index-only", wait=True)
        if rc != 0:
            log_error(f"재인덱싱 실패 (returncode={rc})")
            return False

        # ── 5단계: 인덱싱 상태 재확인 및 비교 ────────────────────────────────
        log_verbose("5단계: --status 로 변경 후 상태 확인 및 비교")
        status_after = _get_status_output()
        if status_after is None:
            log_error("변경 후 status 획득 실패")
            return False
        files_after, chunks_after = _parse_status_counts(status_after)
        log_info(f"변경 후: 파일={files_after}개, 청크={chunks_after}개")

        log_info(f"파일 변화: {files_before}개 → {files_after}개 (Δ{files_after - files_before:+d})")
        log_info(f"청크 변화: {chunks_before}개 → {chunks_after}개 (Δ{chunks_after - chunks_before:+d})")

        if files_after >= files_before:
            log_error(f"exclude_patterns 적용 후 파일 수가 줄지 않음 ({files_before} → {files_after})")
            return False
        if chunks_after >= chunks_before:
            log_error(f"exclude_patterns 적용 후 청크 수가 줄지 않음 ({chunks_before} → {chunks_after})")
            return False

        # ── 6단계: 제외된 파일 내용이 검색되지 않는지 확인 ───────────────────
        log_verbose(f"6단계: '{SEARCH_KEYWORD}' 검색 → 제외 후 결과 없음 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("MCP 서버 시작 실패")
            return False

        result_excluded = child.search_code(SEARCH_KEYWORD, top_k=5, project=TARGET_PROJECT)
        child.kill()
        child = None

        if result_excluded is None:
            log_error(f"'{SEARCH_KEYWORD}' 검색 중 오류 발생")
            return False
        found_excluded, rank_excluded = result_excluded.hit(SEARCH_KEYWORD)
        if found_excluded:
            log_error(f"exclude_patterns 적용 후에도 '{SEARCH_KEYWORD}'이 검색됨 (순위 #{rank_excluded})")
            return False
        log_info(f"'{SEARCH_KEYWORD}' 검색 결과 없음 확인 (exclude_patterns 정상 동작)")

        # ── 7단계: exclude_patterns 제거 ────────────────────────────────────
        log_verbose(f"7단계: {TARGET_PROJECT}에서 exclude_pattern '{EXCLUDE_PATTERN}' 제거")
        settings_restored = json.loads(json.dumps(settings_backup))
        with open(SETTINGS, "w", encoding="utf-8-sig") as f:
            json.dump(settings_restored, f, indent=2, ensure_ascii=False)
        settings_backup = None  # 복원 완료 — finally 블록에서 재복원 방지

        # ── 8단계: 재인덱싱 없이 status만 확인 (인덱스 미변경 확인) ────────────
        log_verbose("8단계: --status 로 상태 확인 (재인덱싱 없음 — 인덱스는 아직 변경 전)")
        status_restored_noindex = _get_status_output()
        if status_restored_noindex is None:
            log_error("8단계 status 획득 실패")
            return False
        files_noindex, chunks_noindex = _parse_status_counts(status_restored_noindex)
        log_info(f"설정 복원 후(재인덱싱 전): 파일={files_noindex}개, 청크={chunks_noindex}개")

        # ── 9단계: 재인덱싱 후 — 제외된 내용이 검색되는지 확인 ────────────────
        log_verbose(f"9단계: '{SEARCH_KEYWORD}' 검색 → 재인덱싱 후 결과 다시 확인")
        child = CodeIndexProcess()
        if child.run(None, wait=False) is None:
            log_error("MCP 서버 시작 실패")
            return False

        result_included = child.search_code(SEARCH_KEYWORD, top_k=5, project=TARGET_PROJECT)
        child.kill()
        child = None

        if result_included is None:
            log_error(f"'{SEARCH_KEYWORD}' 재검색 중 오류 발생")
            return False
        found_included, rank_included = result_included.hit(SEARCH_KEYWORD)
        if False == found_included:
            log_error(f"재인덱싱 되었음에도 '{SEARCH_KEYWORD}'이 검색되지 않음")
            return False
        log_info(f"재인덱싱 후 '{SEARCH_KEYWORD}' 검색됨 (순위 #{rank_included})")

        # ── 10단계: 복원 후 파일/청크 수가 기준선과 일치하는지 확인 ──────────────
        log_verbose("10단계: --status 로 복원 후 파일·청크 수 기준선 비교")
        status_final = _get_status_output()
        if status_final is None:
            log_error("복원 후 status 획득 실패")
            return False
        files_final, chunks_final = _parse_status_counts(status_final)
        log_info(f"복원 후: 파일={files_final}개, 청크={chunks_final}개")
        log_info(f"파일 변화: {files_after}개 → {files_final}개 (Δ{files_final - files_after:+d})")
        log_info(f"청크 변화: {chunks_after}개 → {chunks_final}개 (Δ{chunks_final - chunks_after:+d})")

        if files_final != files_before:
            log_error(f"복원 후 파일 수가 기준선({files_before})과 다름: {files_final}")
            return False
        if chunks_final != chunks_before:
            log_error(f"복원 후 청크 수가 기준선({chunks_before})과 다름: {chunks_final}")
            return False

        log_info("exclude_patterns 테스트가 성공적으로 완료되었습니다")
        return True

    except Exception as e:
        log_error(f"exclude_patterns 테스트 중 예외 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if child is not None:
            child.kill()
        # settings.json 복원 (오류 발생 시 백업이 남아 있을 경우)
        if settings_backup is not None:
            try:
                with open(SETTINGS, "w", encoding="utf-8-sig") as f:
                    json.dump(settings_backup, f, indent=2, ensure_ascii=False)
            except Exception as restore_error:
                log_error(f"settings.json 복원 실패: {restore_error}")

def _get_status_output() -> Optional[str]:
    """--status 명령 출력을 캡처하여 반환합니다."""
    child = CodeIndexProcess()
    rc, stdout = child.run("--status", wait=True)
    if rc is None:
        log_error("--status 프로세스 시작 실패")
        return None
    if rc != 0:
        log_error(f"--status 실행 실패 (returncode={rc})")
        return None
    return stdout


def _parse_status_counts(status_output: str) -> Tuple[int, int]:
    """status 출력에서 전체 파일 수와 청크 수를 파싱합니다.

    Returns:
        (files, chunks) 튜플. 파싱 실패 시 (-1, -1).
    """
    files = chunks = -1
    for line in status_output.splitlines():
        if "전체 파일" in line:
            try:
                files = int(line.split(":")[1].strip().replace(",", "").replace("개", "").strip())
            except (IndexError, ValueError):
                pass
        elif "전체 청크" in line:
            try:
                chunks = int(line.split(":")[1].strip().replace(",", "").replace("개", "").strip())
            except (IndexError, ValueError):
                pass
    return files, chunks
