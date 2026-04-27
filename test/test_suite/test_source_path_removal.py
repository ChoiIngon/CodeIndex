from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess

ROOT     = Path(__file__).parent.parent.parent.resolve()
SETTINGS = ROOT / "config" / "settings.json"


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
            found, _ = result.hit(keyword)
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
            found, _ = result.hit(keyword)
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
            found, _ = result.hit(keyword)
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