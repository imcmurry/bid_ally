# news_relevance.py

import math
import openai
import config

# 1) We import scikit-learn for TF-IDF local pre-filter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Set OpenAI key here (you can also do this just once in your main script)
openai.api_key = config.OPENAI_API_KEY

def compute_cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute the cosine similarity between two vectors.
    Both vectors must have the same dimension.
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

    # Avoid division by zero
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))


def passes_local_pre_filter(article_text: str,
                            solicitation_text: str,
                            local_threshold: float = 0.05,
                            debug: bool = False) -> bool:
    """
    Quickly check relevance via a local TF-IDF approach (no GPT).
    We compare just these two documents (article vs. entire solicitation text)
    and compute a simple cosine similarity on their TF-IDF vectors.

    :param article_text: Full text of the news article.
    :param solicitation_text: Full text of the solicitation or a summary of it.
    :param local_threshold: If the TF-IDF similarity is below this, we skip the GPT check.
    :param debug: If True, prints out debug info (similarity score, threshold).
    :return: True if local similarity >= local_threshold, else False.
    """
    # Combine them into a 2-document list
    docs = [solicitation_text, article_text]

    # Build TF-IDF for these 2 docs
    vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
    tfidf_matrix = vectorizer.fit_transform(docs)
    # tfidf_matrix will be shape (2, vocab_size)

    # Compute cosine similarity between doc0 (solicitation) and doc1 (article)
    sim = cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0, 0]

    if debug:
        print(f"[DEBUG - local_pre_filter] TF-IDF Cosine Similarity: {sim:.4f}, Threshold={local_threshold}")

    return sim >= local_threshold


def generate_tags_multi_step(article_text: str, debug: bool = False) -> list[str]:
    """
    MULTI-STEP TAG GENERATION:
      1) Identify the domain or sector from the article text in a first GPT call.
      2) Generate short keyword tags focusing on that domain, in a second GPT call.

    Example use case:
      tags = generate_tags_multi_step(article_text, debug=True)
    """
    # STEP 1) Identify Domain or Sector
    step1_prompt = f"""
    You are a domain expert. Examine the following text and identify the *main domain(s) or sector(s)* it pertains to.
    For example, "naval technology," "military aerospace," "health and pharmaceuticals," "renewable energy," etc.

    The text is:
    ---
    {article_text}
    ---

    Please return one to three short domain/sector labels in a single line, comma-separated, e.g.:
    "naval technology, submarine manufacturing" or "pharmaceutical research".
    If the text is unclear, do your best guess.
    """

    if debug:
        print("[DEBUG] Step 1 Prompt (Identify Domain):")
        print(step1_prompt)
        print()

    response_step1 = openai.ChatCompletion.create(
        model=config.GPT_MODEL_CHAT,  # e.g., "gpt-3.5-turbo" or "gpt-4o"
        messages=[
            {"role": "system", "content": "You are an expert in identifying the domain or sector of a text."},
            {"role": "user", "content": step1_prompt}
        ],
        temperature=0.3,
        max_tokens=200
    )
    domain_line = response_step1["choices"][0]["message"]["content"].strip()

    if debug:
        print("[DEBUG] Step 1 GPT Response (Identified Domain(s)):")
        print(domain_line)
        print()

    # STEP 2) Generate Final Tags
    step2_prompt = f"""
    We have identified the following domain(s) or sector(s): {domain_line}

    Now, given the text and these domain labels, please generate 3-5 short keyword tags
    that best capture the text's specific topics. Avoid overly generic words or unrelated domains.
    Provide them in a comma-separated format. For example: "naval engineering, submarine stealth, industrial espionage"

    The text again is:
    ---
    {article_text}
    ---
    """

    if debug:
        print("[DEBUG] Step 2 Prompt (Generate Final Tags):")
        print(step2_prompt)
        print()

    response_step2 = openai.ChatCompletion.create(
        model=config.GPT_MODEL_CHAT,
        messages=[
            {"role": "system", "content": "You are an expert in generating short keyword tags for a given domain."},
            {"role": "user", "content": step2_prompt}
        ],
        temperature=0.5,
        max_tokens=200
    )
    tags_text = response_step2["choices"][0]["message"]["content"].strip()

    if debug:
        print("[DEBUG] Step 2 GPT Response (Raw Tags):")
        print(tags_text)
        print()

    final_tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]

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
    1) First, a local TF-IDF pre-filter checks if the article is obviously irrelevant.
       If it fails, we skip GPT calls and return False.

    2) If it passes local_pre_filter, we do the existing "weighted-average similarity"
       approach with GPT embeddings, giving the first tag the highest weight, etc.

    :param article_text: Full text of the news article (title + description + content).
    :param solicitation_tags: List of tags describing the solicitation. The first is most important.
    :param solicitation_text: The entire text (or summary) of the solicitation for local TF-IDF filtering.
    :param threshold: Cosine similarity threshold for GPT-based weighted-average result.
                     Defaults to config.RELEVANCE_THRESHOLD if None.
    :param local_threshold: TF-IDF similarity threshold for the local pre-filter. Default=0.1
    :param debug: If True, print debug logs.
    """
    from news_relevance import compute_cosine_similarity

    if threshold is None:
        threshold = config.RELEVANCE_THRESHOLD  # e.g. 0.85 in config

    # --------------------
    # Step 1: Local Pre-Filter
    # --------------------
    if not passes_local_pre_filter(article_text, solicitation_text, local_threshold=local_threshold, debug=debug):
        if debug:
            print(f"[DEBUG] Article: {article_title}")
            print(f"[DEBUG] Article  FAILED local pre-filter (threshold={local_threshold}); skipping GPT.\n")
        return False
    else:
        if debug:
            print(f"[DEBUG] Article: {article_title}")
            print(f"[DEBUG] Article ({article_title}) PASSED local pre-filter (threshold={local_threshold}), continuing to GPT embedding.\n")

    # --------------------
    # Step 2: Weighted-Average GPT Similarity
    # --------------------
    N = len(solicitation_tags)
    if N == 0:
        if debug:
            print("[DEBUG] No tags were provided, returning False by default.")
        return False

    # Descending weights, e.g. if N=3 => [3, 2, 1]
    weights = [N - i for i in range(N)]

    if debug:
        print(f"[DEBUG] Weighted-Average Similarity Approach, Found {N} tag(s). Weights: {weights}")
        print(f"[DEBUG] GPT Threshold set to {threshold}. Embedding article text (length={len(article_text)}).")

    # (A) Embed the entire article text
    article_response = openai.Embedding.create(
        input=article_text,
        model=config.GPT_MODEL_EMBEDDING
    )
    article_embedding = article_response["data"][0]["embedding"]

    # (B) Compute weighted similarities
    sum_weighted_sims = 0.0
    total_weight = 0.0

    for weight, tag in zip(weights, solicitation_tags):
        tag_response = openai.Embedding.create(
            input=tag,
            model=config.GPT_MODEL_EMBEDDING
        )
        tag_embedding = tag_response["data"][0]["embedding"]

        similarity = compute_cosine_similarity(article_embedding, tag_embedding)
        sum_weighted_sims += similarity * weight
        total_weight += weight

        if debug:
            print(f"[DEBUG] Tag='{tag}', Weight={weight}, Similarity={similarity:.4f}, "
                  f"Weighted Contribution={(similarity * weight):.4f}")

    weighted_avg = sum_weighted_sims / total_weight

    if debug:
        print(f"[DEBUG] Weighted Avg GPT Similarity: {weighted_avg:.4f} (Threshold: {threshold})\n")

    return weighted_avg >= threshold


# ----------------------------------------------------------------
# Test Harness
# ----------------------------------------------------------------
if __name__ == "__main__":
    """
    Run 'python news_relevance.py' to:
      - test the local TF-IDF pre-filter
      - test the multi-step tag generation
      - test the final GPT-based relevance
    """

    test_article_text = (
        "Naval Group charges rival ThyssenKrupp with selling out submarine tech. "
        "The legal battle could escalate, impacting future submarine manufacturing "
        "contracts and allied cooperation across Europe. Meanwhile, defense industry "
        "analysts question the strategic ramifications of sharing sensitive technology."
    )

    # Suppose our solicitation is also about submarine manufacturing, stored in a string:
    test_solicitation_text = (
        "This solicitation is for the design and construction of advanced submarine vessels, "
        "focusing on stealth technology, defense systems, and hull manufacturing. "
        "Vendors must demonstrate proven expertise in naval engineering."
    )

    print("=== Testing local TF-IDF pre-filter ===")
    passes_filter = passes_local_pre_filter(test_article_text, test_solicitation_text, local_threshold=0.1, debug=True)
    print(f"Local filter pass? {passes_filter}")
    print("")

    print("=== Testing Multi-Step Tag Generation ===")
    tags = generate_tags_multi_step(test_article_text, debug=True)
    print(f"Final Tags from Multi-Step Approach: {tags}\n")

    print("=== Testing Weighted-Average Relevance Check with Pre-Filter ===")
    # Suppose we have some solicitation tags (just an example):
    solicitation_tags = ["naval engineering", "submarine manufacturing", "stealth technology"]

    relevant = article_is_relevant(
        article_text=test_article_text,
        solicitation_tags=solicitation_tags,
        solicitation_text=test_solicitation_text,
        threshold=0.75,
        local_threshold=0.1,
        debug=True
    )
    print(f"Final result: Is the article relevant? {relevant}")
