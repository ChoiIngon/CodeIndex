"""
CodeIndex 상태 확인 기능
"""

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from code_index import constants
from code_index.config import load_config, get_all_source_paths


def status(cfg) -> None:
    """인덱싱 상태와 시스템 정보를 출력한다."""
    
    from code_index.store.metadata_store import MetadataStore as _MS

    _vs_cfg   = cfg["vector_store"]
    _data_dir = _vs_cfg.get("data_path", "./data/qdrant")
    _meta_path  = os.path.join(os.path.dirname(_data_dir), "metadata.db")
    _cache_path = os.path.join(os.path.dirname(_data_dir), "embed_cache.db")
    
    _source_paths = get_all_source_paths(cfg)

    _meta = _MS(_meta_path)
    _total = _meta.stats()
    _proj  = _meta.project_stats(_source_paths)
    _meta.close()

    # Qdrant 서버 상태 확인 및 임시 실행
    _qdrant_mode = _vs_cfg.get("mode", "server")
    _started_qdrant = False
    _qdrant_process = None
    
    if _qdrant_mode == "server":
        # 기존 Qdrant 서버 실행 여부 확인
        _q_host = _vs_cfg.get("host", "localhost")
        _q_port = _vs_cfg.get("port", constants.DEFAULT_PORTS["qdrant"])
        
        def _is_qdrant_running():
            try:
                with socket.create_connection((_q_host, _q_port), timeout=1):
                    return True
            except:
                return False
        
        _was_running = _is_qdrant_running()
        
        if not _was_running:
            # Qdrant 서버가 실행되지 않은 경우 임시 실행
            try:
                from code_index.store.qdrant_server import ensure_qdrant_server
                _qdrant_cache_root = Path(__file__).parent.parent.parent / constants.DEFAULT_PATHS["cache_dir"]
                _qdrant_process = ensure_qdrant_server(_vs_cfg, _qdrant_cache_root)
                _started_qdrant = True
            except Exception as e:
                print(f"[Status] Qdrant 서버 시작 실패: {e}", file=sys.stderr)

    # 벡터 스토어 통계 (선택적)
    _vector_count = 0
    _vector_status = "연결 실패"
    try:
        from code_index.store.vector_store import VectorStore as _VS
        _vs = _VS(_vs_cfg, cfg["embedding"]["vector_size"])
        _vector_count = _vs.count()
        _vector_status = "정상"
        _vs.close()
    except Exception as e:
        _vector_status = f"연결실패"

    # 임베딩 캐시 통계 (선택적)
    _cache_stats = {"cached_embeddings": 0, "cache_size_mb": 0.0}
    try:
        from code_index.store.cache import EmbedCache
        _cache = EmbedCache(_cache_path)
        _cache_stats = _cache.get_stats()
        _cache.close()
    except Exception:
        pass

    def _check_qdrant_size_mismatch(vector_count: int, data_dir: str) -> None:
        """Qdrant 디스크 사용량과 벡터 개수의 불일치를 감지하고 안내한다."""
        try:
            qdrant_path = Path(data_dir)
            if not qdrant_path.exists():
                return
                
            # Qdrant 디렉토리 크기 계산 (WAL 포함)
            total_size_mb = 0
            wal_size_mb = 0
            
            for file_path in qdrant_path.rglob("*"):
                if file_path.is_file():
                    file_size_mb = file_path.stat().st_size / (1024 * 1024)
                    total_size_mb += file_size_mb
                    
                    # WAL 파일 크기 별도 계산
                    if "/wal/" in str(file_path) and not file_path.name.startswith('.'):
                        wal_size_mb += file_size_mb
            
            # 벡터 수 대비 과도한 용량 사용 감지
            if vector_count < constants.PERFORMANCE_THRESHOLDS["max_vector_count_for_size_check"] and total_size_mb > constants.PERFORMANCE_THRESHOLDS["max_disk_usage_mb"]:
                print(f"  ⚠️  Qdrant 용량 불일치 감지:", file=sys.stderr)
                print(f"      벡터 {vector_count:,}개에 {total_size_mb:.1f}MB 사용 중", file=sys.stderr)
                if wal_size_mb > constants.PERFORMANCE_THRESHOLDS["max_wal_size_mb"]:
                    print(f"      WAL 파일: {wal_size_mb:.1f}MB (정리 필요)", file=sys.stderr)
                print(f"      해결 방법:", file=sys.stderr)
                print(f"        1) MCP 서버 재시작: python -m code_index", file=sys.stderr)
                print(f"        2) 완전 재생성: python -m code_index --remove", file=sys.stderr)
                print()
            
        except Exception:
            pass  # 크기 확인 실패는 무시

    def _fmt_dt(iso: str) -> str:
        if not iso:
            return "(없음)"
        try:
            dt = datetime.fromisoformat(iso).astimezone()
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return iso

    print("=" * 60)
    print("  CodeIndex  인덱싱 상태")
    print("=" * 60)
    print(f"  전체 파일 : {_total['total_files']:,}개")
    print(f"  전체 청크 : {_total['total_chunks']:,}개")
    print(f"  벡터 개수 : {_vector_count:,}개  ({_vector_status})")
    print(f"  캐시 개수 : {_cache_stats['cached_embeddings']:,}개  ({_cache_stats['cache_size_mb']} MB)")
    print()
    print(f"  메타 DB   : {_meta_path}")
    print(f"  임베딩 캐시: {_cache_path}")
    
    # Qdrant 용량 불일치 감지 및 안내
    _check_qdrant_size_mismatch(_vector_count, _data_dir)
    _qdrant_mode = _vs_cfg.get("mode", "server")
    if _qdrant_mode == "server":
        _q_host = _vs_cfg.get("host", "localhost")
        _q_port = _vs_cfg.get("port", constants.DEFAULT_PORTS["qdrant"])
        _q_cache = Path(__file__).parent.parent.parent / constants.DEFAULT_PATHS["cache_dir"]
        _q_exe_name = "qdrant.exe" if sys.platform == "win32" else "qdrant"
        _q_exe = _q_cache / "qdrant" / _q_exe_name
        _q_ready = "준비됨" if _q_exe.exists() else "미설치 (최초 실행 시 자동 다운로드)"
        print(f"  벡터 DB   : server mode  ({_q_host}:{_q_port})")
        print(f"  Qdrant exe: {_q_exe}  [{_q_ready}]")
    else:
        print(f"  벡터 DB   : embedded mode  ({_data_dir})")
    _debug    = cfg.get("debug", False)
    _log_path = str(Path(constants.DEFAULT_PATHS["log_file"]).resolve())
    _model_cache_dir = cfg.get("models", {}).get("cache_dir", "").strip()
    if not _model_cache_dir:
        _model_cache_dir = str((Path(__file__).parent.parent.parent / constants.DEFAULT_PATHS["cache_dir"]).resolve())
    print(f"  모델 캐시 : {_model_cache_dir}")
    print(f"  MCP 전송  : stdio (SSE 사용 시 --http-port PORT 로 실행)")
    print(f"  로그 파일 : {_log_path}  ({'debug=true' if _debug else 'debug=false, 비활성'})")
    print()
    if not _source_paths:
        print("  등록된 source_paths 없음 (config/settings.json 확인)")
    else:
        print(f"  {'프로젝트 경로':<45} {'파일':>6} {'청크':>7}  최종 인덱싱")
        print("  " + "-" * 78)
        for p in _proj:
            sp   = p["source_path"]
            disp = (sp[:42] + "...") if len(sp) > 45 else sp
            print(f"  {disp:<45} {p['files']:>6,} {p['chunks']:>7,}  {_fmt_dt(p['last_indexed'])}")
    print("=" * 60)
    
    # 임시로 실행한 Qdrant 서버 정리
    if _started_qdrant and _qdrant_mode == "server":
        try:
            # Windows에서 qdrant.exe 프로세스 종료
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/f", "/im", "qdrant.exe"], 
                             capture_output=True, check=False)
            else:
                # Linux/Mac에서는 포트로 프로세스 찾아서 종료
                subprocess.run(["pkill", "-f", f"qdrant.*{_q_port}"], 
                             capture_output=True, check=False)
            time.sleep(0.5)  # 종료 대기
        except Exception as e:
            print(f"[Status] Qdrant 서버 종료 중 오류: {e}", file=sys.stderr)
    
    sys.exit(0)