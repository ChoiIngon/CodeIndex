"""
CodeIndex 제거 기능
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from code_index import constants


def remove() -> None:
    """설치된 패키지, 모델 캐시, 인덱스 데이터를 삭제한다."""
    print("[Remove] 다음 항목을 삭제합니다:", file=sys.stderr)
    print("  - pip 패키지 (torch, sentence-transformers, qdrant-client, tree-sitter 등)", file=sys.stderr)
    print("  - .cache/ (모델 캐시 + Qdrant 실행 파일)", file=sys.stderr)
    print("  - 인덱스 데이터 (벡터 DB, 메타데이터 DB, 임베딩 캐시)", file=sys.stderr)
    answer = input("  계속하시겠습니까? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        print("[Remove] 취소했습니다.", file=sys.stderr)
        sys.exit(0)

    # settings.json 에서 경로 직접 로드 (패키지 의존 없이)
    _settings_path = Path(__file__).parent.parent.parent / constants.DEFAULT_PATHS["settings"]
    try:
        with open(_settings_path, encoding="utf-8") as _f:
            _settings = json.load(_f)
    except Exception:
        _settings = {}

    _vs_cfg    = _settings.get("vector_store", {})
    _model_cfg = _settings.get("models", {})

    # ── 인덱스 데이터 경로 계산 ──────────────────────────────────────────────
    _data_dir = Path(_vs_cfg.get("data_path", constants.DEFAULT_PATHS["data_dir"]))
    if not _data_dir.is_absolute():
        _data_dir = (Path(__file__).parent.parent.parent / _data_dir).resolve()
    _data_parent = _data_dir.parent

    _index_paths = [
        _data_dir,
        _data_parent / "metadata.db",
        _data_parent / "embed_cache.db",
    ]

    print("[Remove] 인덱스 데이터 삭제 중...", file=sys.stderr)
    for _p in _index_paths:
        if _p.exists():
            if _p.is_dir():
                shutil.rmtree(_p)
            else:
                _p.unlink()
            print(f"  삭제: {_p}", file=sys.stderr)
        else:
            print(f"  건너뜸 (없음): {_p}", file=sys.stderr)

    # ── 모델 캐시 삭제 ────────────────────────────────────────────────────────
    _cache_dir = _model_cfg.get("cache_dir", "").strip()

    # cache_dir 미설정 시 프로젝트 루트 .cache 가 기본값
    _default_cache = Path(__file__).parent.parent.parent / constants.DEFAULT_PATHS["cache_dir"]
    _resolved_cache = Path(_cache_dir) if _cache_dir else _default_cache

    print("[Remove] 모델 캐시 삭제 중...", file=sys.stderr)
    if _resolved_cache.exists():
        shutil.rmtree(_resolved_cache)
        print(f"  삭제: {_resolved_cache}", file=sys.stderr)
    else:
        print(f"  건너뜸 (없음): {_resolved_cache}", file=sys.stderr)

    # ── pip 패키지 언인스톨 ───────────────────────────────────────────────────
    print("[Remove] pip 패키지 언인스톨 중...", file=sys.stderr)
    _uninstall_pkgs = list(constants.TORCH_PACKAGES) + [constants.PACKAGE_INSTALL_NAMES.get(p, p) for p in constants.REQUIRED_PACKAGES]
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "uninstall", "-y"] + _uninstall_pkgs,
        )
        print("[Remove] 패키지 언인스톨 완료.", file=sys.stderr)
    except subprocess.CalledProcessError as _e:
        print(f"[Remove] 패키지 언인스톨 중 오류 발생: {_e}", file=sys.stderr)

    print("", file=sys.stderr)
    print("[Remove] 완료. 재설치하려면 'python -m code_index' 를 다시 실행하세요.", file=sys.stderr)
    sys.exit(0)