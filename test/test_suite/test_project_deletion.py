from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from utility import log_error, log_info, log_verbose
from code_index import CodeIndexProcess

ROOT     = Path(__file__).parent.parent.parent.resolve()
SETTINGS = ROOT / "config" / "settings.json"


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
        found, _ = result.hit("DataAnalyzer")
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
        found_proj, _ = result_proj.hit("DataAnalyzer")
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
            found_kw, _ = result_kw.hit(keyword)
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
        found_p1, _ = result_p1.hit("MovePlayer")
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