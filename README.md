# CodeIndex

게임 서버 소스코드(.cs / .h / .cpp)를 인덱싱하고, 자연어 질의에 관련 코드 청크를 반환하는 **로컬 MCP 서버**입니다.  
VS Code, Visual Studio 2022, Claude Desktop 등 MCP를 지원하는 AI 클라이언트와 연동됩니다.

## 특징

- 외부 API 키 불필요 — 임베딩 모델을 최초 실행 시 HuggingFace에서 자동 다운로드
- Dense(HNSW) + BM25 하이브리드 검색 + RRF 점수 결합
- SHA-256 기반 증분 인덱싱 — 변경된 파일만 재처리
- GPU 자동 감지 및 CUDA wheel 자동 설치
- MCP stdio / HTTP(streamable-http) 두 가지 전송 방식 지원

---

## 요구 사항

- Python 3.11+
- NVIDIA GPU 권장 (CPU 동작 가능, 속도 저하)
- CUDA 11.8 이상 (GPU 사용 시)

---

## Quick Start

1. **클론**
   ```powershell
   git clone https://github.com/ChoiIngon/CodeIndex.git
   cd CodeIndex
   ```

2. **경로 설정** — `config/settings.json`의 `indexer.source_paths`에 인덱싱할 경로 추가 (자세한 내용은 [설정](#설정) 참고)
   ```json
   { "indexer": { "source_paths": ["C:/MyProject/src"] } }
   ```

3. **서버 실행** (자세한 내용은 [실행](#실행) 참고)
   ```powershell
   python -m code_index          # stdio 모드
   python -m code_index --http-port 6380  # HTTP 모드
   ```

4. **에디터 연동** 후 재시작 (자세한 내용은 [MCP 에디터 연동](#mcp-에디터-연동) 참고)
   ```json
   {
     "servers": {
       "CodeIndex": { "type": "stdio", "command": "python", "args": ["-m", "code_index"], "cwd": "E:/work/CodeIndex" }
     }
   }
   ```
---

## 설치

```powershell
git clone https://github.com/ChoiIngon/CodeIndex.git
cd CodeIndex
```

의존성은 첫 실행 시 자동 설치됩니다. 수동 설치가 필요하면:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install qdrant-client tree-sitter tree-sitter-cpp tree-sitter-c-sharp mcp sentencepiece einops
```

---

## 설정

`config/settings.json` 파일에서 인덱싱 대상 경로와 옵션을 설정합니다.

```json
{
  "indexer": {
    "source_paths": ["C:/MyProject/src", "./test/data"],
    "extensions": [".cpp", ".h", ".c", ".cs"],
    "exclude_patterns": ["*/build/*", "*/.git/*", "*/generated/*"],
    "chunk_min_lines": 5,
    "chunk_max_lines": 80,
    "chunk_overlap_lines": 10,
    "chunk_workers": 0
  },
  "models": {
    "cache_dir": "",
    "embed": "BAAI/bge-m3",
    "rerank": "cross-encoder/ms-marco-MiniLM-L-12-v2"
  },
  "embedding": {
    "vector_size": 1024,
    "batch_size": 64,
    "n_gpu_layers": -1
  },
  "vector_store": {
    "mode": "server",
    "host": "localhost",
    "port": 6333,
    "data_path": "./data/qdrant",
    "collection": "code_index_chunks"
  },
  "search": {
    "top_k": 20,
    "rerank_top_k": 8,
    "min_score": 0.0,
    "alpha": 0.5,
    "use_reranker": false
  },
  "debug": false
}
```

### indexer

| 항목 | 설명 | 기본값 |
|---|---|---|
| `source_paths` | 인덱싱할 소스 경로 목록. 절대 경로 또는 프로젝트 루트 기준 상대 경로 | `[]` |
| `extensions` | 인덱싱 대상 확장자 목록 | `[".cpp", ".h", ".c", ".cs"]` |
| `exclude_patterns` | 제외할 경로 패턴 (glob). `*/build/*` 등 빌드 산출물 제외에 사용 | `["*/build/*", "*/.git/*", "*/generated/*"]` |
| `chunk_min_lines` | 이 값 미만의 라인 수를 가진 심볼은 청크에서 제외 | `5` |
| `chunk_max_lines` | 청크 최대 라인 수. 초과 시 overlap을 유지하며 분할 | `80` |
| `chunk_overlap_lines` | 분할된 청크 간 중복 라인 수. 컨텍스트 연속성 유지 | `10` |
| `chunk_workers` | 청킹 병렬 프로세스 수. `0` = CPU 코어 수의 절반 자동 사용 | `0` |

### models

| 항목 | 설명 | 기본값 |
|---|---|---|
| `cache_dir` | 모델 다운로드 캐시 경로. 비워두면 프로젝트 루트의 `.cache/` 사용 | `""` |
| `embed` | 임베딩 모델 HuggingFace ID. 변경 시 `vector_size`도 함께 변경하고 재인덱싱 필요 | `"BAAI/bge-m3"` |
| `rerank` | 재랭커 모델 HuggingFace ID. `search.use_reranker: true` 일 때만 로드됨 | `"cross-encoder/ms-marco-MiniLM-L-12-v2"` |

### embedding

| 항목 | 설명 | 기본값 |
|---|---|---|
| `vector_size` | 임베딩 벡터 차원. 사용하는 `models.embed` 모델의 출력 차원과 일치해야 함 | `1024` |
| `batch_size` | 임베딩 배치 크기. GPU VRAM에 따라 조정 (RTX 3060: 64, RTX 4090: 128+) | `64` |
| `n_gpu_layers` | (예약) GPU 레이어 수. 현재 미사용 | `-1` |

### vector_store

| 항목 | 설명 | 기본값 |
|---|---|---|
| `mode` | `"server"`: 별도 Qdrant 프로세스 사용 (권장), `"embedded"`: Python 프로세스 내 내장 모드 | `"server"` |
| `host` | Qdrant 서버 호스트. `mode: "server"` 일 때 사용 | `"localhost"` |
| `port` | Qdrant HTTP 포트. gRPC는 `port + 1` 자동 사용 | `6333` |
| `data_path` | Qdrant 데이터 저장 경로. `mode: "server"` 시 서버 시작 인자로 전달됨 | `"./data/qdrant"` |
| `collection` | Qdrant 컬렉션 이름. 변경 시 기존 데이터와 호환되지 않으므로 재인덱싱 필요 | `"code_index_chunks"` |

> **server mode**: 최초 실행 시 `.cache/qdrant/qdrant.exe`를 GitHub Releases에서 자동 다운로드하고 백그라운드 프로세스로 기동합니다. code_index 종료 시 함께 종료됩니다.

### search

| 항목 | 설명 | 기본값 |
|---|---|---|
| `top_k` | 검색 결과 반환 수. 리랭커 사용 시 이 수만큼 후보를 뽑아 `rerank_top_k`로 압축 | `20` |
| `rerank_top_k` | 리랭커 최종 반환 수. `use_reranker: true` 일 때만 적용 | `8` |
| `min_score` | 최소 점수 필터. 이 값 미만 결과는 제외 (`0.0` = 필터 없음) | `0.0` |
| `alpha` | Dense/BM25 가중치. `1.0` = Dense 전용, `0.0` = BM25 전용, `0.5` = 균등 혼합 | `0.5` |
| `use_reranker` | `true` 시 `models.rerank` 모델로 결과를 재정렬해 정확도 향상. 속도 소폭 저하 | `false` |

### 디버깅

| 항목 | 설명 | 기본값 |
|---|---|---|
| `debug` | `true` 시 MCP 요청/응답을 `log.txt`에 기록 | `false` |

---

## 실행

### 인덱싱만 수행

```powershell
python -m code_index --index-only
```

### stdio 모드로 MCP 서버 실행 (단일 에디터)

```powershell
python -m code_index
```

### HTTP 모드로 MCP 서버 실행 (여러 에디터 동시 사용)

```powershell
python -m code_index --http-port 6380
```

### 인덱싱 상태 확인

```powershell
python -m code_index --status
```

### CLI 검색 (MCP 없이 직접 질의)

```powershell
# 자연어 검색
python -m code_index --search-code "데미지 계산 로직"

# 필터 옵션
python -m code_index --search-code "CalculateDamage" --top-k 10 --language cpp --symbol-type function

# 파일 심볼 목록
python -m code_index --get-file-outline "combat.cpp"

# 청크 ID로 코드 조회
python -m code_index --get-chunk "fc617902-35bc-5155-b9d1-b94837fd181d"
```

---

## MCP 에디터 연동

### stdio 모드 (기본 — 에디터 1개)

에디터가 code_index를 자식 프로세스로 직접 실행합니다. 
mcp 서버를 사용하는 에디터가 1개일 때 사용. 여러개 동시 사용시 뒤에 사용하는 mcp는 공유 파일 접근 불가 이슈로 자식 프로세스 생성 실패합니다.
여러 에디터에서 동시에 mcp 서버에 접근하려면 HTTP 모드를 사용하십시오.

**Claude Desktop** 
- 프로젝트 스코프(Local - 최우선 순위): 현재 작업 중인 워크스페이스의 루트 폴더 내 `.vscode/mcp.json`
- 유저 스코프(Global - 낮은 순위): `%APPDATA%\Claude\claude_desktop_config.json`(`C:\Users\<사용자명>\AppData\Roaming\Claude\claude_desktop_config.json`) 
```json
{
  "mcpServers": {
    "CodeIndex": {
      "command": "python",
      "args": ["-m", "code_index"],
      "cwd": "E:/work/CodeIndex"
    }
  }
}
```

**VS Code**
- 프로젝트 스코프(Local - 최우선 순위): 현재 작업 중인 워크스페이스의 루트 폴더 내 `.vscode/mcp.json`
- 유저 스코프(Global - 낮은 순위): `%APPDATA%\Code\User\mcp.json`(`C:\Users\<사용자명>\AppData\Roaming\Code\User\mcp.json`)
```json
{
  "servers": {
    "CodeIndex": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "code_index"],
      "cwd": "E:/work/CodeIndex"
    }
  }
}
```

**Visual Studio 2022**
- 프로젝트 스코프(Local - 최우선 순위): `<솔루션폴더>\.mcp.json`
- 유저 스코프(Global - 낮은 순위): `%USERPROFILE%\.mcp.json`(`C:\Users\<사용자명>\.mcp.json`)
```json
{
  "servers": {
    "CodeIndex": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "code_index"],
      "cwd": "E:/work/CodeIndex"
    }
  }
}
```

### HTTP 모드 (에디터 여러 개 동시 사용)

먼저 서버를 실행합니다:
```powershell
python -m code_index --http-port 6380
```

각 에디터 MCP 설정에 URL을 등록합니다:

**Claude Desktop**
```json
{
  "mcpServers": {
    "CodeIndex": {
      "url": "http://127.0.0.1:6380/mcp"
    }
  }
}
```

**VS Code / Visual Studio 2022**
```json
{
  "servers": {
    "CodeIndex": {
      "type": "http",
      "url": "http://127.0.0.1:6380/mcp"
    }
  }
}
```

---

## MCP 도구 목록

AI 클라이언트가 호출할 수 있는 도구입니다.

| 도구 | 설명 | 주요 파라미터 |
|---|---|---|
| `search_code` | 자연어/심볼명으로 코드 청크 검색 | `query`, `top_k`, `language`, `symbol_type` |
| `get_file_outline` | 파일의 심볼 목록(클래스/함수/메서드) 반환 | `file_path` |
| `get_chunk` | 청크 ID로 코드 전문 조회 | `chunk_id` |

---

## 데이터 저장 위치

| 파일/디렉터리 | 내용 |
|---|---|
| `./data/metadata.db` | 파일/청크 메타데이터 + FTS5 BM25 인덱스 (SQLite) |
| `./data/embed_cache.db` | content_hash → 임베딩 벡터 캐시 (SQLite) |
| `./data/qdrant/` | HNSW 벡터 인덱스 (Qdrant 데이터) |
| `./.cache/qdrant/qdrant.exe` | 자동 다운로드된 Qdrant 실행 파일 |
| `./.cache/` | HuggingFace 모델 캐시 (`models.cache_dir` 미설정 시) |
| `./log.txt` | MCP 요청/응답 로그 (`debug: true` 시) |

인덱스를 완전히 초기화하려면:
```powershell
python -m code_index --remove
python -m code_index --index-only
```

---

## 아키텍처

```
인덱싱 파이프라인
  소스코드 → 파일 스캐너(변경 감지) → Tree-sitter 파싱
          → 청킹 → 임베딩(GPU) → Qdrant + SQLite FTS5

검색 파이프라인
  질의 → 쿼리 임베딩
       ├─ Dense 검색 (HNSW)
       └─ BM25 검색 (FTS5)
            └─ RRF 점수 결합 → [재랭킹(선택)] → 결과 반환
```

## 프로젝트 구조

```
CodeIndex/
├── code_index/
│   ├── __main__.py        # 진입점, CLI 옵션 처리
│   ├── config.py          # 설정 로드 및 기본값
│   ├── indexer/
│   │   ├── scanner.py     # 파일 스캔 및 변경 감지
│   │   ├── parser.py      # Tree-sitter AST 파싱
│   │   ├── chunker.py     # 심볼 단위 청킹
│   │   ├── embedder.py    # 임베딩 생성
│   │   └── pipeline.py    # 인덱싱 파이프라인 오케스트레이션
│   ├── store/
│   │   ├── vector_store.py    # Qdrant HNSW 벡터 저장소
│   │   ├── metadata_store.py  # SQLite 메타데이터 + FTS5
│   │   └── cache.py           # 임베딩 캐시
│   ├── retriever/
│   │   ├── hybrid_search.py   # Dense + BM25 + RRF
│   │   └── reranker.py        # 재랭킹 (선택)
│   ├── mcp/
│   │   ├── server.py          # FastMCP 서버 (도구 정의)
│   │   └── debug_logger.py    # 요청/응답 로거
│   └── models/
│       └── model_manager.py   # HuggingFace 모델 경로 관리
├── config/
│   └── settings.json      # 사용자 설정
├── test/
│   ├── run_test.py         # 정확도 테스트
│   └── data/               # 테스트용 샘플 소스코드
└── data/                   # 인덱스 데이터 (gitignore)
```
