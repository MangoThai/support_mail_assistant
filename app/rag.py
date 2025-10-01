from __future__ import annotations

import shutil
import unicodedata
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import FastEmbedEmbeddings


@dataclass(frozen=True)
class Snippet:
    content: str
    source: str
    score: float  # plus petit = meilleur


def _chunk_markdown(text: str, max_len: int = 600) -> List[str]:
    chunks: List[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > max_len:
            chunks.append(para[:max_len].strip())
            para = para[max_len:]
        if para:
            chunks.append(para)
    return chunks


def _read_kb_docs(kb_dir: Path) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    for p in sorted(kb_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        for chunk in _chunk_markdown(text):
            if chunk.strip():
                items.append((str(p), chunk.strip()))
    return items


# ---------- Normalisation lexicale FR ----------

_FR_SUFFIXES = (
    "ations", "ation",
    "tions", "tion",
    "ements", "ement",
    "ments", "ment",
    "ées", "és", "ees", "es",
    "ée", "é", "ee", "e",
    "er", "re", "s"
)

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9]+", text.lower())

def _stem_fr(tok: str) -> str:
    t = _strip_accents(tok)
    for suf in _FR_SUFFIXES:
        if t.endswith(suf) and len(t) > len(suf) + 2:
            return t[: -len(suf)]
    return t

def _lexical_score(query: str, text: str) -> int:
    """Score = |tiges(query) ∩ tiges(texte)| (accents/suffixes FR gérés)."""
    q_stems = {_stem_fr(t) for t in _tokenize(query) if len(t) >= 3}
    if not q_stems:
        return 0
    t_stems = {_stem_fr(t) for t in _tokenize(text) if len(t) >= 3}
    return len(q_stems & t_stems)


# ---------------------- Construction de l'index ----------------------

def build_index(kb_dir: str = "data/kb", persist_dir: str = "data/chroma") -> Chroma:
    """(Re)construit un index Chroma persistant à partir des .md (déterministe)."""
    kb = Path(kb_dir)
    persist = Path(persist_dir)
    if persist.exists():
        shutil.rmtree(persist)
    persist.mkdir(parents=True, exist_ok=True)

    embeddings = FastEmbedEmbeddings()  # télécharge un petit modèle au premier run
    vs = Chroma(
        collection_name="kb_index",
        embedding_function=embeddings,
        persist_directory=str(persist),
    )

    docs = _read_kb_docs(kb)
    if not docs:
        return vs

    metadatas = [{"source": src} for (src, _chunk) in docs]
    texts = [chunk for (_src, chunk) in docs]
    vs.add_texts(texts=texts, metadatas=metadatas)
    try:
        vs.persist()  # no-op sur versions récentes, toléré
    except Exception:
        pass
    return vs


# ------------------------- Recherche (snippets) -------------------------

_NUM_LINE_RE = re.compile(r"^\s*\d+\.\s", flags=re.MULTILINE)

def _is_numbered_steps(text: str) -> bool:
    return bool(_NUM_LINE_RE.search(text))

def _norm(s: str) -> str:
    return _strip_accents(s.lower())

def retrieve_snippets(query: str, k: int = 3, kb_dir: str = "data/kb", persist_dir: str = "data/chroma") -> List[Dict[str, str]]:
    """
    Renvoie [{"content": ..., "source": ..., "score": "..."}].
    Tri principal: score lexical décroissant, puis score vectoriel croissant.
    Post-traitements:
      - bonus doux pour les paragraphes d'étapes,
      - garantir au moins un paragraphe d'étapes pertinent,
      - si la phrase "lien de réinitialisation" existe quelque part, garantir sa présence dans le top-k.
    """
    persist = Path(persist_dir)
    embeddings = FastEmbedEmbeddings()
    vs = Chroma(
        collection_name="kb_index",
        embedding_function=embeddings,
        persist_directory=str(persist),
    )

    vector_candidates: List[Tuple[str, float, Dict]] = []
    try:
        hits = vs.similarity_search_with_score(query, k=max(k, 5))
        for doc, score in hits:
            vector_candidates.append((doc.page_content, float(score or 0.0), doc.metadata or {}))
    except Exception:
        pass

    from collections import defaultdict
    lex_candidates: List[Tuple[str, int, Dict]] = []
    for src, chunk in _read_kb_docs(Path(kb_dir)):
        lex = _lexical_score(query, chunk)
        if lex > 0:
            if _is_numbered_steps(chunk):
                lex += 1  # petit bonus pour les "procédures"
            lex_candidates.append((chunk, lex, {"source": src}))

    combined: Dict[Tuple[str, str], Tuple[int, float]] = defaultdict(lambda: (0, 1e9))
    for chunk, vscore, meta in vector_candidates:
        key = (chunk, meta.get("source", ""))
        lex, _ = combined[key]
        combined[key] = (lex, min(vscore, combined[key][1]))
    for chunk, lex, meta in lex_candidates:
        key = (chunk, meta.get("source", ""))
        _, vscore = combined[key]
        combined[key] = (max(lex, combined[key][0]), vscore)

    if not combined:
        for src, chunk in _read_kb_docs(Path(kb_dir)):
            combined[(chunk, src)] = (0, 1e9)

    # Classement
    items: List[Snippet] = sorted(
        [Snippet(content=c, source=s, score=(1 - _lexical_score(query, c)) + v) for (c, s), (l, v) in combined.items()],
        key=lambda sn: (-_lexical_score(query, sn.content), sn.score, sn.source, sn.content),
    )

    # Top-k initial
    top = items[:k]

    # (1) Garantir au moins un paragraphe d'étapes pertinent
    if not any(_is_numbered_steps(sn.content) for sn in top):
        cand = None
        for sn in items:
            if _is_numbered_steps(sn.content) and _lexical_score(query, sn.content) > 0:
                cand = sn
                break
        if cand:
            if all(not (cand.content == s.content and cand.source == s.source) for s in top):
                if len(top) == k:
                    top[-1] = cand
                else:
                    top.append(cand)

    # (2) Si une occurrence de "lien de réinitialisation" existe dans la collection,
    #     garantir sa présence dans le top-k (comparaison insensible aux accents/casse).
    phrase = _norm("lien de réinitialisation")
    if not any(phrase in _norm(sn.content) for sn in top):
        target = next((sn for sn in items if phrase in _norm(sn.content)), None)
        if target:
            if all(not (target.content == s.content and target.source == s.source) for s in top):
                if len(top) == k:
                    top[-1] = target
                else:
                    top.append(target)

    out: List[Dict[str, str]] = []
    for sn in top[:k]:
        out.append({"content": sn.content, "source": sn.source, "score": f"{sn.score:.6f}"})
    return out
