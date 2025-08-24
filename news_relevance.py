# news_relevance.py

import math
import config

# 1) scikit-learn for TF-IDF local pre-filter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- OpenAI SDK compatibility (v0.x vs v1.x) -------------------------------
try:
    # New SDK (v1.x)
    from openai import OpenAI, BadRequestError, RateLimitError
    client = OpenAI(api_key=getattr(config, "OPENAI_API_KEY", None))
    _OPENAI_V1 = True
except Exception:
    # Legacy SDK (v0.x)
    import openai
    from openai import InvalidRequestError as BadRequestError, RateLimitError
    openai.api_key = getattr(config, "OPENAI_API_KEY", None)
    client = None
    _OPENAI_V1 = False


def _embed(text: str, model: str | None = None) -> list[float]:
    """
    Return a single embedding vector for the given text, across SDK versions.
    """
    model = (
        model
        or getattr(config, "GPT_MODEL_EMBEDDING", None)
        or getattr(config, "GPT_EMBED_MODEL", "text-embedding-3-small")
    )
    if _OPENAI_V1:
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding
    else:
        resp = openai.Embedding.create(model=model, input=text)
        return resp["data"][0]["embedding"]


def _chat_complete(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    """
    Uniform chat completion wrapper for both SDKs.
    """
    if _OPENAI_V1:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    else:
        resp = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp["choices"][0]["message"]["content"]


def compute_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute the cosine similarity between two vectors.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must be the same dimension.")
    dot_product = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot_product += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))


def passes_local_pre_filter(article_text: str,
                            solicitation_text: str,
                            local_threshold: float = 0.05,
                            debug: bool = False) -> bool:
    """
    Fast TF‑IDF similarity pre‑filter (no GPT).
    """
    docs = [solicitation_text, article_text]
    vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
    tfidf_matrix = vectorizer.fit_transform(docs)
    sim = cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0, 0]
    if debug:
        print(f"[DEBUG - local_pre_filter] TF-IDF Cosine Similarity: {sim:.4f}, Threshold={local_threshold}")
    return sim >= local_threshold


def generate_tags_multi_step(article_text: str, debug: bool = False) -> list[str]:
    """
    MULTI‑STEP TAG GENERATION via chat API (v1/v0 compatible).
    """
    step1_prompt = f"""
You are a domain expert. Examine the following text and identify the *main domain(s) or sector(s)* it pertains to.
Return one to three short labels, comma-separated.

Text:
---
{article_text}
---
"""
    if debug:
        print("[DEBUG] Step 1 Prompt (Identify Domain):")
        print(step1_prompt)
        print()

    domain_line = _chat_complete(
        model=getattr(config, "GPT_MODEL_CHAT", "gpt-4o"),
        messages=[
            {"role": "system", "content": "You are an expert in identifying the domain or sector of a text."},
            {"role": "user", "content": step1_prompt},
        ],
        temperature=0.3,
        max_tokens=200
    ).strip()

    if debug:
        print("[DEBUG] Step 1 GPT Response (Identified Domain(s)):")
        print(domain_line)
        print()

    step2_prompt = f"""
We identified these domain(s)/sector(s): {domain_line}

Now generate 3-5 short keyword tags that best capture specific topics in the text.
Return them comma-separated.

Text:
---
{article_text}
---
"""
    if debug:
        print("[DEBUG] Step 2 Prompt (Generate Final Tags):")
        print(step2_prompt)
        print()

    tags_text = _chat_complete(
        model=getattr(config, "GPT_MODEL_CHAT", "gpt-4o"),
        messages=[
            {"role": "system", "content": "You are an expert in generating short keyword tags for a given domain."},
            {"role": "user", "content": step2_prompt},
        ],
        temperature=0.5,
        max_tokens=200
    ).strip()

    if debug:
        print("[DEBUG] Step 2 GPT Response (Raw Tags):")
        print(tags_text)
        print()

    final_tags = [t.strip() for t in tags_text.split(",") if t.strip()]

    if debug:
        print("[DEBUG] Final Multi-Step Tags:")
        print(final_tags)
        print()

    return final_tags


def article_is_relevant(article_title: str,
                        article_text: str,
                        solicitation_tags: list[str],
                        solicitation_text: str,
                        threshold: float = None,
                        local_threshold: float = 0.05,
                        debug: bool = True) -> bool:
    """
    1) TF‑IDF local pre‑filter (cheap).
    2) If it passes, compute weighted average cosine similarity between
       the article embedding and each tag embedding.
    """
    if threshold is None:
        threshold = getattr(config, "RELEVANCE_THRESHOLD", 0.75)  # default if not set

    # --- Step 1: local pre‑filter
    if not passes_local_pre_filter(article_text, solicitation_text, local_threshold=local_threshold, debug=debug):
        if debug:
            print(f"[DEBUG] Article: {article_title}")
            print(f"[DEBUG] Article  FAILED local pre-filter (threshold={local_threshold}); skipping GPT.\n")
        return False
    else:
        if debug:
            print(f"[DEBUG] Article: {article_title}")
            print(f"[DEBUG] Article ({article_title}) PASSED local pre-filter (threshold={local_threshold}), continuing to GPT embedding.\n")

    # --- Step 2: weighted average similarity with embeddings
    N = len(solicitation_tags or [])
    if N == 0:
        if debug:
            print("[DEBUG] No tags were provided, returning False by default.")
        return False

    weights = [N - i for i in range(N)]  # e.g., N=3 -> [3,2,1]
    if debug:
        print(f"[DEBUG] Weighted-Average Similarity Approach, Found {N} tag(s). Weights: {weights}")
        print(f"[DEBUG] GPT Threshold set to {threshold}. Embedding article text (length={len(article_text)}).")

    # Embed article
    try:
        article_embedding = _embed(article_text)
    except Exception as e:
        if debug:
            print(f"[DEBUG] Failed to embed article: {e}")
        return False

    # Weighted similarities
    sum_weighted_sims = 0.0
    total_weight = 0.0

    for weight, tag in zip(weights, solicitation_tags):
        try:
            tag_embedding = _embed(tag)
        except Exception as e:
            if debug:
                print(f"[DEBUG] Failed to embed tag '{tag}': {e}")
            continue

        similarity = compute_cosine_similarity(article_embedding, tag_embedding)
        sum_weighted_sims += similarity * weight
        total_weight += weight

        if debug:
            print(f"[DEBUG] Tag='{tag}', Weight={weight}, Similarity={similarity:.4f}, "
                  f"Weighted Contribution={(similarity * weight):.4f}")

    if total_weight == 0.0:
        if debug:
            print("[DEBUG] No tag embeddings were computed; returning False.")
        return False

    weighted_avg = sum_weighted_sims / total_weight

    if debug:
        print(f"[DEBUG] Weighted Avg GPT Similarity: {weighted_avg:.4f} (Threshold: {threshold})\n")

    return weighted_avg >= threshold


# ----------------------------------------------------------------
# Test harness (optional)
# ----------------------------------------------------------------
if __name__ == "__main__":
    test_article_text = (
        "Naval Group charges rival ThyssenKrupp with selling out submarine tech. "
        "The legal battle could escalate, impacting future submarine manufacturing "
        "contracts and allied cooperation across Europe. Meanwhile, defense industry "
        "analysts question the strategic ramifications of sharing sensitive technology."
    )
    test_solicitation_text = (
        "This solicitation is for the design and construction of advanced submarine vessels, "
        "focusing on stealth technology, defense systems, and hull manufacturing. "
        "Vendors must demonstrate proven expertise in naval engineering."
    )

    print("=== Testing local TF-IDF pre-filter ===")
    print(passes_local_pre_filter(test_article_text, test_solicitation_text, local_threshold=0.1, debug=True))
    print()

    print("=== Testing Multi-Step Tag Generation ===")
    print(generate_tags_multi_step(test_article_text, debug=True))
    print()

    print("=== Testing Weighted-Average Relevance Check with Pre-Filter ===")
    solicitation_tags = ["naval engineering", "submarine manufacturing", "stealth technology"]
    print(article_is_relevant(
        article_title="Dummy",
        article_text=test_article_text,
        solicitation_tags=solicitation_tags,
        solicitation_text=test_solicitation_text,
        threshold=0.75,
        local_threshold=0.1,
        debug=True
    ))
