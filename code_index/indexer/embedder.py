from __future__ import annotations

import sys
from typing import Optional

from ..store.cache import EmbedCache


def _pick_device(torch) -> str:
    if not torch.cuda.is_available():
        return "cpu"
    try:
        torch.tensor([1.0]).cuda() + torch.tensor([1.0]).cuda()
        return "cuda"
    except RuntimeError as e:
        print(f"[Embedder] CUDA 커널 실패: {e}\n  → CPU 모드로 동작합니다.", file=sys.stderr)
        return "cpu"


class Embedder:
    """transformers AutoModel 기반 로컬 임베딩 생성기."""

    def __init__(self, model_name: str, cfg: dict, cache: Optional[EmbedCache] = None):
        self._cache = cache
        self._batch_size = cfg.get("batch_size", 32)

        print(f"[Embedder] 모델 로드 중: {model_name}", file=sys.stderr)
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._device = _pick_device(torch)
        print(f"[Embedder] 디바이스: {self._device}", file=sys.stderr)

        self._torch = torch
        # use_fast=False: Rust fast tokenizer PyO3 바인딩 버그 우회 (sentencepiece 필요)
        self._tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
        print(f"[Embedder] 토크나이저: {type(self._tokenizer).__name__}", file=sys.stderr)

        # FP16: CUDA 환경에서 메모리 절반, 속도 1.5~2배 (RTX 3060 이상 Tensor Core 활용)
        dtype = torch.float16 if self._device == "cuda" else torch.float32
        self._model = AutoModel.from_pretrained(model_name, dtype=dtype).to(self._device)
        self._model.eval()

        self._dtype = dtype
        print(f"[Embedder] 모델 로드 완료 (dtype={dtype}).", file=sys.stderr)

    # ── 공개 API ────────────────────────────────────────────────────────────

    def embed_batch(self, texts: list[str], content_hashes: list[str]) -> list[list[float]]:
        results: list[Optional[list[float]]] = [None] * len(texts)
        uncached_idx: list[int] = []

        if self._cache:
            for i, (_, ch) in enumerate(zip(texts, content_hashes)):
                vec = self._cache.get(ch)
                if vec is not None:
                    results[i] = vec
                else:
                    uncached_idx.append(i)
        else:
            uncached_idx = list(range(len(texts)))

        if uncached_idx:
            raw = self._embed_texts([texts[i] for i in uncached_idx])
            for idx, vec in zip(uncached_idx, raw):
                results[idx] = vec
                if self._cache:
                    self._cache.set(content_hashes[idx], vec)

        return [r for r in results if r is not None]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_texts([str(text)])[0]

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        import torch.nn.functional as F

        all_vecs: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = [str(t) for t in texts[i: i + self._batch_size]]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {k: v.to(self._device) for k, v in encoded.items()}
            with self._torch.no_grad():
                # autocast: FP16 모델에서 mixed precision 연산 보장
                with self._torch.autocast(device_type=self._device, dtype=self._dtype, enabled=(self._device == "cuda")):
                    out = self._model(**encoded)
            # CLS 토큰 (인덱스 0) 사용 — bge 계열 표준
            vecs = out.last_hidden_state[:, 0]
            vecs = F.normalize(vecs, p=2, dim=1)
            all_vecs.extend(vecs.cpu().float().numpy().tolist())
        return all_vecs
