# MapleCodeIndex 개발 지침

## 1. 프로젝트 개요

* MapleCodeIndex는 대량의 게임 서버 소스코드를 인덱싱
* MCP를 통해 AI 클라이언트(Copilot, Claude 등)의 질의에 관련 코드 청크를 반환하는 코드 검색 MCP 서버다.

### 목표
- 대상 프로젝트: .cs/.h/.cpp 포함 약 6만 개 파일
- 자연어 질의에 대해 관련성 높은 코드 청크를 랭킹 순으로 반환
- 질의 응답 시간 1초 이내
- 증분 업데이트(incremental indexing)로 변경분만 재인덱싱
- MCP 서버로 제공 (대상: VS Code, VS 2022, Claude)
- 외부 API 키 불필요 — 임베딩 모델은 최초 실행 시 HuggingFace에서 자동 다운로드

### 사용 흐름
```
코드 에디터나 ai 앱에서 사용자 질문
    │
    ▼
AI 클라이언트 (Copilot / Claude)
    │  코드 검색 필요 판단
    ▼
MapleCodeIndex MCP 서버
    │  관련 코드 청크 반환 (랭킹 포함)
    ▼
AI 클라이언트가 청크 기반으로 코드 이해·분석·답변 생성
```
---

## 2. 시스템 아키텍처

#### 인덱싱 파이프라인 (오프라인)
```
[소스코드 저장소]
       │
       ▼
[파일 스캐너 & 변경 감지]
       │
       ▼
[코드 파서 & 청킹(Chunking)]  ← ProcessPoolExecutor 병렬 처리
       │
       ▼
[임베딩 생성기 (로컬 GGUF)]  ← EmbedCache로 content_hash 캐싱
       │
       ▼
[벡터 DB (Qdrant) + SQLite FTS5]
```

#### 검색 파이프라인 (온라인, MCP 요청 처리)
```
[MCP 질의]
       │
       ▼
[쿼리 임베딩 (로컬 GGUF)]
       │
       ├─────────────────┐
       ▼                 ▼
[Vector 검색 (HNSW)]  [BM25 검색 (FTS5)]   ← 병렬
       │                 │
       └────────┬────────┘
                ▼
       [RRF 점수 결합]
                │
                ▼
       [재랭킹 (선택, use_reranker: false)]
                │
                ▼
  [랭킹된 코드 청크 반환 → AI 클라이언트]
```

### 주요 컴포넌트
| 컴포넌트 | 역할 | 모듈 |
|---|---|---|
| File Scanner | 코드 파일 탐색, 변경 감지, SHA256 해시 | `indexer/scanner.py` |
| Code Parser | Tree-sitter AST 파싱, 심볼 추출 | `indexer/parser.py` |
| Chunker | 심볼 단위 청킹 + 슬라이딩 윈도우 폴백 | `indexer/chunker.py` |
| Embedder | llama-cpp-python GGUF 임베딩 (인덱싱 + 쿼리) | `indexer/embedder.py` |
| Pipeline | 파일 스캔 → 청킹 → 임베딩 → 저장 오케스트레이션 | `indexer/pipeline.py` |
| Vector Store | Qdrant embedded HNSW 벡터 검색 | `store/vector_store.py` |
| Metadata Store | SQLite 파일·청크 메타데이터 + FTS5 BM25 | `store/metadata_store.py` |
| Embed Cache | content_hash 기반 임베딩 벡터 SQLite 캐시 | `store/cache.py` |
| Model Manager | HuggingFace GGUF 자동 다운로드 (urllib) | `models/model_manager.py` |
| Hybrid Search | Dense HNSW + BM25 FTS5, RRF 퓨전 | `retriever/hybrid_search.py` |
| Reranker | Qwen3-Reranker GGUF 재순위화 (기본 비활성) | `retriever/reranker.py` |
| Config | settings.json 로드 + 기본값 deep merge | `config.py` |
| MCP Server | FastMCP 기반 AI 클라이언트 연동 | `mcp/server.py` |

---

## 3. 파일 스캐너 & 변경 감지

### 3.1 대상 파일 필터링
```
포함: .cpp, .h, .c, .cs
제외: build/, .git/, generated/, __pycache__/
```

### 3.2 변경 감지 전략
- **초기 인덱싱**: 전체 파일 해시(SHA-256) 계산 후 DB 저장
- **증분 인덱싱**: 파일 수정시각(mtime) 선행 체크 (오차 0.01초) → 변경 시 해시 재계산
- mtime 변경이 없으면 SHA256을 계산하지 않아 I/O 최소화

### 3.3 인덱싱 상태 저장 (SQLite `files` 테이블)
```sql
files (file_path TEXT PRIMARY KEY, sha256 TEXT, mtime REAL, indexed_at TEXT)
```

### 3.4 주요 함수
```python
scan_files(source_paths, extensions, exclude_patterns) -> Generator[str]
detect_changes(current_files, metadata_store) -> (new, modified, deleted)
file_sha256(path) -> str
```

---

## 4. 코드 파싱 & 청킹

### 4.1 파싱 전략
- **AST 기반 파싱** (우선): Tree-sitter (`tree-sitter>=0.22`) 사용
  - C/C++: `tree_sitter_cpp`, C#: `tree_sitter_c_sharp`
  - 함수/메서드/클래스/구조체/인터페이스/네임스페이스 추출
- **슬라이딩 윈도우** (폴백): AST 실패 시 `max_lines` 단위로 분할

### 4.2 파싱 결과 (`ParsedSymbol`)
```python
@dataclass
class ParsedSymbol:
    symbol_type: str   # "function" | "class" | "struct" | "namespace" | "method" | "interface"
    symbol_name: str   # 네임스페이스::클래스::메서드 형식으로 완전 경로
    parent_class: str
    namespace: str
    start_line: int    # 1-based
    end_line: int
    content: str
```

### 4.3 청킹 규칙

#### 심볼 단위 청킹 (최우선)
```
- 단일 심볼이 max_lines 이하 → 1청크 (메타데이터 프리픽스 포함)
- 단일 심볼이 max_lines 초과 → (max_lines - overlap) 단위로 분할
- 메타데이터 프리픽스: "// File: path | symbol_type: symbol_name"
```

#### 청크 크기 기준
| 항목 | 값 (config 기본값) |
|---|---|
| 최소 청크 크기 | 5 라인 (`chunk_min_lines`) |
| 최대 청크 크기 | 150 라인 (`chunk_max_lines`) |
| 오버랩 크기 | 10 라인 (`chunk_overlap_lines`) |

#### 청크 ID 생성
```python
chunk_id = uuid.uuid5(NAMESPACE, f"{file_path}:{start_line}:{end_line}")
content_hash = sha256(content)[:16]  # 캐시 키용
```

#### Chunk 데이터클래스
```python
@dataclass
class Chunk:
    chunk_id: str        # UUID v5
    file_path: str
    language: str        # "cpp" | "h" | "c" | "cs"
    start_line: int
    end_line: int
    symbol_type: str
    symbol_name: str
    parent_class: str
    namespace: str
    content: str         # 메타 프리픽스 + 코드
    content_hash: str    # SHA256 앞 16자 (임베딩 캐시 키)
```

---

## 5. 임베딩

> **원칙**: 외부 API 없이 로컬 모델로 임베딩. 인터넷 연결은 최초 모델 다운로드 시에만 필요.

### 5.1 임베딩 라이브러리

`sentence-transformers` + `torch` 사용. PyTorch CUDA wheel로 GPU 자동 지원 — 소스 컴파일 불필요.

| 모델 | 차원수 | 크기 | 특징 |
|---|---|---|---|
| **nomic-ai/nomic-embed-text-v1.5** (기본) | 768 | ~540MB | 코드+텍스트 균형, 한국어 지원, prompt_name 지원 |
| BAAI/bge-m3 | 1024 | ~1.2GB | 다국어, 정확도 높음 |
| intfloat/multilingual-e5-large | 1024 | ~1.1GB | 다국어 강점 |

```python
class Embedder:
    def __init__(self, model_name: str, cfg: dict, cache: EmbedCache = None)
    def embed_batch(self, texts: list[str], content_hashes: list[str]) -> list[list[float]]
    def embed_query(self, text: str) -> list[float]
```

- GPU: `torch.cuda.is_available()` 로 자동 감지
- `nomic-embed-text` 등 prompt_name 지원 모델은 인덱싱 시 `"search_document"`, 쿼리 시 `"search_query"` 자동 적용
- `embed_batch`: `content_hash` 기준 캐시 히트 시 기존 벡터 재사용, 미스 분만 모델 호출

### 5.2 배치 임베딩 처리
- 배치 크기: `embedding.batch_size` (기본 64, GPU에서 128~256 까지 증가 가능)
- 파이프라인에서 청킹 결과를 버퍼에 누적하다가 `batch_size` 초과 시 플러시

### 5.3 임베딩 캐시 (`EmbedCache`)
- SQLite `embeddings` 테이블, `content_hash TEXT PRIMARY KEY, vector BLOB`
- 벡터를 `struct.pack("Nf")` 바이너리로 저장/복원
- WAL 저널 모드로 동시 읽기 성능 향상

---

## 6. 벡터 저장소 (`VectorStore`)

### 6.1 ANN 검색 (핵심 주의사항)
반드시 **HNSW** 인덱스가 활성화된 설정을 사용해야 한다.

| 검색 방식 | 60만 청크 예상 속도 | 비고 |
|---|---|---|
| Flat (선형) | 수 분~수십 분 | **절대 사용 금지** |
| **HNSW** | **1~10ms** | Qdrant 기본, `full_scan_threshold: 0` 필수 |

### 6.2 Qdrant embedded 모드
```python
QdrantClient(path="./data/qdrant")  # Docker/서버 불필요
```

### 6.3 컬렉션 설정 (코드 기반)
```python
VectorParams(size=768, distance=Distance.COSINE, on_disk=True)
HnswConfigDiff(m=16, ef_construct=200, full_scan_threshold=0)
```
- `full_scan_threshold=0`: 소규모에서 Flat 폴백 방지
- `on_disk=True`: 벡터 데이터 디스크 저장, RAM 절약

### 6.4 페이로드 인덱스 (필터링 성능)
컬렉션 생성 시 자동 생성:
- `file_path` (KEYWORD)
- `language` (KEYWORD)
- `symbol_type` (KEYWORD)
- `parent_class` (KEYWORD)

### 6.5 주요 메서드
```python
VectorStore(cfg: dict)  # cfg = 전체 설정 딕셔너리 (cfg["vector_store"], cfg["embedding"] 접근)
upsert_batch(items: list[(chunk_id, vector, payload)])
delete(chunk_ids: list[str])
search(query_vector, top_k, filters) -> list[SearchResult]
count() -> int
```
> chunk_id(UUID)는 `md5(chunk_id)[:8]` → uint64 변환 후 Qdrant point ID로 사용

---

## 7. 메타데이터 저장소 (`MetadataStore`)

SQLite 단일 파일(`data/metadata.db`)에 파일 상태, 청크 메타, FTS5 BM25 인덱스를 모두 저장한다.

### 7.1 스키마
```sql
-- 파일 상태
files (file_path TEXT PK, sha256 TEXT, mtime REAL, indexed_at TEXT)

-- 청크 메타데이터
chunks (chunk_id TEXT PK, file_path TEXT, language TEXT, start_line INT,
        end_line INT, symbol_type TEXT, symbol_name TEXT,
        parent_class TEXT, namespace TEXT, content TEXT, content_hash TEXT)

-- BM25 전문 검색 (FTS5)
chunks_fts USING fts5(chunk_id UNINDEXED, content, symbol_name, file_path UNINDEXED)
```

### 7.2 BM25 검색
```python
def bm25_search(self, query: str, top_k: int = 20) -> list[(chunk_id, score)]
```
- SQLite FTS5 `MATCH` 쿼리 사용
- `bm25()` 반환값은 음수이므로 부호 반전하여 반환

### 7.3 주요 메서드
```python
upsert_file(file_path, sha256, mtime)
upsert_chunks(chunks: list[Chunk])
delete_file(file_path)           # files + chunks + chunks_fts 동시 삭제
get_file_symbols(file_path) -> list[dict]
get_chunk(chunk_id) -> ChunkMeta
get_chunks_by_ids(chunk_ids) -> list[ChunkMeta]
stats() -> {"total_files": int, "total_chunks": int}
```

---

## 8. 검색 엔진 (Hybrid Search)

### 8.1 하이브리드 검색 전략
```python
def hybrid_search(
    query_vec, query_text, metadata, vector_store,
    top_k=20, alpha=0.7, filters=None
) -> list[SearchResult]
```

1. Dense: `vector_store.search(query_vec, top_k=top_k*2, filters=filters)`
2. Sparse: `metadata.bm25_search(query_text, top_k=top_k*2)`
3. RRF 퓨전: `score[id] += alpha/(k+rank+1)` (dense) + `(1-alpha)/(k+rank+1)` (sparse), k=60

### 8.2 RRF 파라미터
```python
alpha = 0.7     # Dense 가중치 (코드 검색 기준)
k = 60          # RRF 상수 (순위 영향 완화)
```

### 8.3 재랭킹 (선택)
- `search.use_reranker: true` 시 활성화 (기본값 `false`)
- `Reranker(model_name, cfg).rerank(query, results, top_k=8)`
- 모델: `cross-encoder/ms-marco-MiniLM-L-12-v2` (sentence-transformers CrossEncoder)
- 한국어 강화 필요 시 `BAAI/bge-reranker-v2-m3` 로 교체 가능
- `CrossEncoder.predict(pairs)` 로 (query, content) 쌍 일괄 스코어링

### 8.4 SearchResult
```python
@dataclass
class SearchResult:
    chunk_id, score, file_path, language
    start_line, end_line, symbol_type, symbol_name
    parent_class, namespace, content
```

---

## 9. MCP 서버

`FastMCP` (`mcp.server.fastmcp.FastMCP`) 기반으로 구현. stdio transport 사용.

### 9.1 노출 도구 (MCP Tools)

#### `search_code`
```python
def search_code(
    query: str,
    top_k: int = 20,
    language: str = "",      # "cpp" | "cs" | "" (전체)
    symbol_type: str = "",   # "function" | "class" | "method" | ""
) -> list[dict]
```
- Dense + BM25 하이브리드 검색 후 RRF 결합
- `use_reranker: true` 시 재랭킹 적용
- 반환 필드: `chunk_id, score, file_path, language, start_line, end_line, symbol_type, symbol_name, parent_class, namespace, content`

#### `get_file_outline`
```python
def get_file_outline(file_path: str) -> list[dict]
```
- 파일 경로 일부 매칭 지원 (파일명만 입력해도 동작)
- 반환: `[{"type": str, "name": str, "line": int}, ...]`

#### `get_chunk`
```python
def get_chunk(chunk_id: str) -> dict | None
```
- chunk_id(UUID)로 특정 청크 전체 내용 조회

### 9.2 서버 시작
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("MapleCodeIndex")
mcp.run(transport="stdio")
```

### 9.3 클라이언트별 MCP 설정

#### VS Code (`.vscode/mcp.json`)
```json
{
  "servers": {
    "maple-code-index": {
      "type": "stdio",
      "command": "python",
      "args": ["C:\\MapleCodeIndex\\maple_code_index"]
    }
  }
}
```

#### Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "maple-code-index": {
      "command": "python",
      "args": ["C:\\MapleCodeIndex\\maple_code_index"]
    }
  }
}
```

#### VS 2022
GitHub Copilot Extension → MCP 설정에서 동일 stdio 방식 적용.

---

## 10. 인덱싱 파이프라인 (`pipeline.py`)

### 10.1 전체 흐름
```
1. 파일 스캔 → (new, modified, deleted) 분류
2. deleted: vector_store + metadata 동시 삭제
3. modified: 기존 인덱스 삭제 후 신규와 동일 처리
4. new + modified: ProcessPoolExecutor 병렬 청킹
5. 청크 buffer → batch_size 초과 시 임베딩 + upsert 플러시
6. 파일 메타 일괄 업데이트
```

### 10.2 병렬 청킹
```python
# chunk_workers = 0: CPU 코어 수 절반 자동 사용
cfg_workers = idx_cfg.get("chunk_workers", 0)
workers = cfg_workers if cfg_workers > 0 else max(1, cpu_count // 2)

with ProcessPoolExecutor(max_workers=workers) as pool:
    futures = {pool.submit(_chunk_worker, (fpath, chunk_cfg)): fpath ...}
```
- `_chunk_worker`는 모듈 최상위 함수 (Windows `spawn` 방식에서 pickle 가능)

### 10.3 스트리밍 임베딩
청킹 결과를 `embed_buffer`에 누적하다가 `batch_size` 초과 시 플러시:
```
청킹(병렬) → embed_buffer → [batch_size 초과] → embedder.embed_batch → vector_store.upsert_batch
```

### 10.4 진행 상황 출력
```
[Pipeline] 청킹 500/3000  (12s, 40파일/s)
[Pipeline] 완료. 3000개 파일 / 24500개 청크 (245.3s)
```

---

## 11. 모델 관리 (`model_manager.py`)

### 11.1 모델 식별자 형식
```
HuggingFace 모델 ID
예: nomic-ai/nomic-embed-text-v1.5
    cross-encoder/ms-marco-MiniLM-L-12-v2
```

### 11.2 `resolve_model(model_ref, cache_dir) -> str`
- `cache_dir` 지정 시 `SENTENCE_TRANSFORMERS_HOME`, `HF_HOME` 환경 변수 설정
- 모델 ID를 그대로 반환 — 실제 다운로드는 `SentenceTransformer(model_name)` 호출 시 자동 처리
- 캐시는 `~/.cache/huggingface/hub/` (기본) 또는 `cache_dir` 에 저장

---

## 12. 디렉토리 구조

```
MapleCodeIndex/
├── maple_code_index/           ← 실행 패키지 (python maple_code_index)
│   ├── __init__.py
│   ├── __main__.py             # 진입점: 의존성→모델→인덱싱→MCP 서버
│   ├── config.py               # load_config(), 기본값 deep merge
│   ├── indexer/
│   │   ├── scanner.py          # 파일 스캔, 변경 감지, SHA256
│   │   ├── parser.py           # Tree-sitter AST 파싱 (C/C++, C#)
│   │   ├── chunker.py          # 심볼 단위 청킹 + 슬라이딩 윈도우
│   │   ├── embedder.py         # llama-cpp-python 임베딩
│   │   └── pipeline.py         # 인덱싱 오케스트레이션
│   ├── store/
│   │   ├── vector_store.py     # Qdrant embedded HNSW
│   │   ├── metadata_store.py   # SQLite (파일 상태 + 청크 + FTS5 BM25)
│   │   └── cache.py            # SQLite 임베딩 벡터 캐시
│   ├── retriever/
│   │   ├── hybrid_search.py    # Dense + BM25 + RRF
│   │   └── reranker.py         # Qwen3-Reranker GGUF (선택)
│   ├── models/
│   │   └── model_manager.py    # HuggingFace GGUF 자동 다운로드
│   └── mcp/
│       └── server.py           # FastMCP 서버 (search_code, get_file_outline, get_chunk)
├── config/
│   └── settings.json           # 사용자 설정 (source_paths 등)
├── data/                       # 인덱스 데이터 (자동 생성)
│   ├── qdrant/                 # Qdrant embedded 저장소
│   ├── metadata.db             # SQLite (파일·청크·FTS5)
│   └── embed_cache.db          # SQLite 임베딩 캐시
├── test/
│   ├── data/                   # 테스트용 샘플 소스 (C++, C#, .h 10개)
│   └── run_test.py             # 정확도 테스트 스크립트
└── requirements.txt
```

---

## 13. 실행 방식

### 13.1 기본 실행 (MCP 서버 포함)

```cmd
cd C:\MapleCodeIndex
python maple_code_index
```

`__main__.py`가 아래 순서를 자동으로 처리:

```
① 의존성 확인 & 자동 설치
   - CUDA 감지(nvcc.exe 실제 존재 확인) 시 CUDA 빌드, 없으면 CPU 빌드
   - 실패 시 CPU 빌드로 자동 폴백

② config/settings.json 로드 (없으면 기본값 사용)
   - source_paths 가 비어 있으면 오류 출력 후 종료

③ 임베딩 모델 확인 (없으면 HuggingFace 자동 다운로드)
   - use_reranker: true 시 리랭커 모델도 확인

④ 인덱싱
   - metadata.db total_files == 0: 전체 인덱싱
   - total_files > 0: 증분 인덱싱 (변경 파일만)

⑤ MCP 서버 시작 (stdio)
```

### 13.2 CLI 플래그

```cmd
rem 인덱싱만 실행하고 MCP 서버를 시작하지 않음
python maple_code_index --index-only

rem stdin에서 JSON 쿼리 배열을 받아 검색 결과를 stdout으로 출력
python maple_code_index --query-batch

rem --query-batch 에서 반환할 결과 수 지정 (기본 20)
python maple_code_index --query-batch --top-k 10
```

#### `--query-batch` 입출력 형식
```json
// stdin (JSON 배열)
[{"query": "필드 로딩 로직", "top_k": 5}, ...]

// stdout (JSON 배열)
[{"query": "...", "results": [{"chunk_id": "...", "score": 0.92, "file_path": "...", "symbol_name": "...", "content": "..."}, ...]}, ...]
```

---

## 14. 설정 파일 구조 (`config/settings.json`)

```json
{
  "indexer": {
    "source_paths": ["D:\\MapleServer\\src"],
    "extensions": [".cpp", ".h", ".c", ".cs"],
    "exclude_patterns": ["*/build/*", "*/.git/*", "*/generated/*", "*/__pycache__/*"],
    "chunk_min_lines": 5,
    "chunk_max_lines": 150,
    "chunk_overlap_lines": 10,
    "chunk_workers": 0
  },
  "models": {
    "cache_dir": "",
    "embed": "hf:ggml-org/nomic-embed-text-v1.5-GGUF/nomic-embed-text-v1.5.Q8_0.gguf",
    "rerank": "hf:ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/qwen3-reranker-0.6b-q8_0.gguf"
  },
  "embedding": {
    "vector_size": 768,
    "batch_size": 32,
    "n_gpu_layers": -1
  },
  "vector_store": {
    "mode": "embedded",
    "data_path": "./data/qdrant",
    "collection": "maple_code_chunks"
  },
  "search": {
    "top_k": 20,
    "rerank_top_k": 8,
    "min_score": 0.0,
    "alpha": 0.7,
    "use_reranker": false
  }
}
```

| 설정 키 | 설명 |
|---|---|
| `chunk_workers` | 청킹 병렬 워커 수. 0이면 CPU 코어 수 절반 자동 사용 |
| `n_gpu_layers` | -1이면 모든 레이어 GPU 오프로드 |
| `use_reranker` | true 시 Qwen3-Reranker 모델 로드 및 재랭킹 적용 |
| `alpha` | RRF Dense 가중치 (0~1, 높을수록 의미 검색 비중 증가) |
| `models.cache_dir` | 비어 있으면 실행 디렉토리 기준 `.cache/models/` 사용 |

---

## 15. 최초 설치 및 실행

### 15.1 사전 요구사항

```
Windows 10/11 (x64)
Python 3.11+         https://www.python.org/downloads/
  └─ 설치 시 "Add Python to PATH" 체크 필수
GPU 드라이버 (NVIDIA CUDA 12+)  —  선택사항, 없으면 CPU로 동작
```

### 15.2 설치 순서

#### Step 1. 소스 다운로드
```cmd
git clone https://github.com/nexon/MapleCodeIndex.git
cd MapleCodeIndex
```

#### Step 2. settings.json 에 소스코드 경로 지정
`config\settings.json` 열어 `source_paths` 수정:
```json
"source_paths": ["D:\\MapleServer\\src"]
```

#### Step 3. 실행
```cmd
python maple_code_index
```

이후 모든 것이 자동으로 진행된다:
```
[Setup] 누락된 패키지 설치 중: llama-cpp-python, ...
[Setup] CUDA 감지됨: C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8
[Setup] llama-cpp-python CUDA 빌드 컴파일 중...
[Setup] 패키지 설치 완료.

[Setup] 임베딩 모델 확인 중...
[모델] nomic-embed-text-v1.5.Q8_0.gguf 다운로드 중... (270MB)

[Index] 전체 인덱싱 시작...
[Pipeline] 파일 61,203개 발견 (2.1s)
[Pipeline] 신규=61203, 수정=0, 삭제=0
[Pipeline] 청킹 시작 (병렬 워커=8, 파일=61203개)...
[Pipeline] 청킹 500/61203  (12s, 40파일/s)
...
[Pipeline] 완료. 61203개 파일 / 487320개 청크 (1114.3s)

[MCP] MapleCodeIndex MCP 서버 시작 (stdio)...
```

**두 번째 실행부터:**
```
[Index] 증분 인덱싱 시작...
[Pipeline] 파일 61215개 발견 (2.1s)
[Pipeline] 신규=12, 수정=11, 삭제=3
[Pipeline] 완료. 23개 파일 / 187개 청크 (4.2s)
[MCP] MapleCodeIndex MCP 서버 시작 (stdio)...
```

### 15.3 초기 인덱싱 소요 시간 예측 (6만 파일 기준)

| 환경 | 임베딩 속도 | 예상 소요시간 |
|---|---|---|
| GPU (RTX 3080+) | ~500 청크/초 | **15~20분** |
| GPU (RTX 3060) | ~300 청크/초 | **25~35분** |
| CPU only | ~50 청크/초 | **2~3시간** |

> 초기 인덱싱은 1회성. 이후 증분 인덱싱은 수 초~수 분 이내.

---

## 16. 정확도 테스트

### 16.1 테스트 스크립트
```cmd
cd C:\MapleCodeIndex
python test/run_test.py
```

### 16.2 동작 순서
1. `config/settings.json` 의 `source_paths` 에 `test/data` 경로 자동 추가
2. `python maple_code_index --index-only` 실행 (의존성·모델·인덱싱)
3. `python maple_code_index --query-batch` 로 10개 쿼리 일괄 실행
4. 예상 심볼이 top-5 결과 안에 있는지 판정 후 리포트 출력

### 16.3 테스트 케이스 (10개)
| 쿼리 | 예상 심볼 | 소스 파일 |
|---|---|---|
| 플레이어 이동 처리 함수 | MovePlayer | player.h |
| 데미지 계산 로직 | CalculateDamage | combat.cpp |
| 인벤토리에서 아이템 검색 | FindItem | Inventory.cs |
| 몬스터 스폰 생성 | SpawnMonster | monster.cpp |
| 서버 연결 실패 처리 | HandleConnectionFailure | network.h |
| 아이템 드롭 확률 계산 | CalculateDropRate | ItemDrop.cs |
| 오브젝트 풀 재사용 | ObjectPool | object_pool.h |
| 레벨업 이벤트 처리 보상 | OnLevelUp | LevelSystem.cs |
| 로그 출력 인터페이스 | ILogger | Logger.cs |
| 캐릭터 스탯 구조체 정의 | CharacterStats | character_stats.h |

### 16.4 리포트 형식
```
========================================================================
#   결과   예상 심볼                    쿼리
========================================================================
1   ✓ PASS  MovePlayer                   플레이어 이동 처리 함수  [player.h]
2   ✓ PASS  CalculateDamage              데미지 계산 로직  [combat.cpp]
...
========================================================================
결과: 9/10 통과  (90%)
```

---

## 17. 성능 최적화

### 17.1 인덱싱 성능
| 최적화 항목 | 적용 방법 |
|---|---|
| 청킹 병목 | `ProcessPoolExecutor` 멀티프로세싱 (`chunk_workers`) |
| 임베딩 병목 | 배치 크기 최대화 (`embedding.batch_size`) |
| 중복 임베딩 | `EmbedCache`: `content_hash` 기반 캐싱 |
| 벡터 업서트 | `upsert_batch` (단건 금지) |
| mtime 선행 체크 | SHA256 계산 최소화 |

### 17.2 검색 성능
| 최적화 항목 | 적용 방법 |
|---|---|
| HNSW 파라미터 | `full_scan_threshold=0` — 항상 HNSW 사용 |
| 필터 인덱스 | `file_path, language, symbol_type, parent_class` payload index |
| 결과 캐싱 | 동일 쿼리 벡터 캐싱 (TTL 5분, 추후 구현) |

### 17.3 메모리 관리
- Qdrant `on_disk=True` — 벡터 데이터 디스크 저장, RAM 절약
- SQLite WAL 모드 — 동시 읽기/쓰기 성능
- 임베딩 모델 단일 프로세스 내 재사용

---

## 18. requirements.txt

```
torch
sentence-transformers
qdrant-client
tree-sitter>=0.22
tree-sitter-c
tree-sitter-cpp
tree-sitter-c-sharp
mcp
```

> `torch` 는 `pip install torch` 로 CPU 빌드가 설치됨. GPU 사용 시 `__main__.py` 가 자동으로 CUDA wheel 로 설치 (`--index-url https://download.pytorch.org/whl/cu124`).

---

## 19. 개발 현황 (Phase별)

```
Phase 1 — 인덱싱 기반         ✅ 완료
  ① 파일 스캐너 + MetadataStore (SQLite)
  ② Tree-sitter 파서 (C/C++, C#) + Chunker
  ③ ModelManager (HuggingFace GGUF 자동 다운로드)
  ④ Embedder (llama-cpp-python) + EmbedCache + VectorStore (Qdrant)
  ⑤ Pipeline (ProcessPoolExecutor 병렬 청킹, 스트리밍 임베딩)

Phase 2 — 검색 구현           ✅ 완료
  ⑥ Dense Vector 검색 (HNSW)
  ⑦ BM25 검색 (SQLite FTS5 — MetadataStore 내장)
  ⑧ RRF 퓨전 + Reranker (구현 완료, 기본값 비활성)
  ⑨ --query-batch CLI로 검색 품질 검증 가능

Phase 3 — MCP 서버            ✅ 완료
  ⑩ FastMCP 서버 (search_code, get_file_outline, get_chunk)
  ⑪ VS Code / Claude Desktop 연동 설정

Phase 4 — 운영 안정화         ✅ 완료 (기반) / 🔲 일부 미완
  ⑫ 증분 인덱싱 (변경 감지) ✅
  ⑬ CUDA 자동 감지 및 CPU 폴백 ✅
  ⑭ 정확도 테스트 스위트 (test/run_test.py) ✅
  ⑮ 검색 결과 캐싱 (TTL) 🔲
  ⑯ VS 2022 연동 테스트 🔲
  ⑰ 모니터링 (인덱싱 상태 대시보드) 🔲
```
