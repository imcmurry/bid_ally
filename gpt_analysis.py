# gpt_analysis.py

import openai
import config
from file_utils import extract_text_from_pdfs, truncate_to_token_limit
import os
import json
import time

# Set the OpenAI API key from config
openai.api_key = config.OPENAI_API_KEY

# ---------- 1.  INSIGHTS -------------------------------------------------
def generate_insights(content: str,
                      description: str,
                      description_byte: str,
                      pdf_files: list[str]) -> str:
    """
    GPT insights with hard cap on internal retries to prevent infinite loop.
    """
    import time, os, json, tiktoken
    from openai.error import InvalidRequestError, RateLimitError

    MAX_INTERNAL_RETRIES = 3
    reduction_pct = 1.0
    step = 0
    enc = tiktoken.get_encoding("cl100k_base")

    base_info = f"{description}\n{content}\n{description_byte}"
    extracted_text = extract_text_from_pdfs(pdf_files)

    while reduction_pct > 0.05 and step < MAX_INTERNAL_RETRIES:
        step += 1
        bi_trim = base_info[: int(len(base_info) * reduction_pct)]
        et_trim = extracted_text[: int(len(extracted_text) * reduction_pct)]

        prompt = f"""
        Given the following bid information extracted from government procurement documents, provide:
        1. A concise top level summary of the bid.
        2. A timeline to accomplish the requirements.
        3. An estimated valuation of the contract.
        4. An action plan with estimated man‑hours.

        ---
        Contextual Information:
        {bi_trim}

        Attachments Extracted Text:
        {et_trim}
        """

        try:
            response = openai.ChatCompletion.create(
                model=config.GPT_MODEL_CHAT,
                messages=[
                    {"role": "system",
                     "content": "You are a contract analyst providing structured procurement insights."},
                    {"role": "user", "content": prompt}
                ],
                temperature=config.GPT_TEMPERATURE,
                max_tokens=config.GPT_MAX_TOKENS
            )
            return response["choices"][0]["message"]["content"].strip()

        except (InvalidRequestError, RateLimitError) as e:
            err = str(e).lower()
            if ("maximum context length" in err or "request too large" in err):
                reduction_pct *= 0.8
                _log_trunc("insights", step, reduction_pct, bi_trim, et_trim, err)
                continue
            raise  # unrelated error → bubble up

        except Exception:
            raise  # bubble up any other error

    raise InvalidRequestError("too_many_retries in generate_insights")


# ---------- 2.  SWOT -----------------------------------------------------
def generate_swot_analysis(content: str,
                           description: str,
                           description_byte: str,
                           insights: str,
                           company_details: dict) -> str:
    """
    GPT SWOT with capped internal retries.
    """
    import time, os, json, tiktoken
    from openai.error import InvalidRequestError, RateLimitError

    MAX_INTERNAL_RETRIES = 3
    reduction_pct = 1.0
    step = 0
    enc = tiktoken.get_encoding("cl100k_base")
    base_info = f"{description}\n{insights}\n{description_byte}\n{content}"

    while reduction_pct > 0.05 and step < MAX_INTERNAL_RETRIES:
        step += 1
        bi_trim = base_info[: int(len(base_info) * reduction_pct)]

        prompt = f"""
        You are a strategic consultant. The following data includes:
        - Company Info: {company_details}
        - Solicitation/Bid Details + Preliminary Insights:
          {bi_trim}

        Provide a concise but thorough SWOT analysis.
        """

        try:
            response = openai.ChatCompletion.create(
                model=config.GPT_MODEL_CHAT,
                messages=[
                    {"role": "system",
                     "content": "You are a strategic advisor focusing on SWOT analyses for bid opportunities."},
                    {"role": "user", "content": prompt}
                ],
                temperature=config.GPT_TEMPERATURE,
                max_tokens=config.GPT_MAX_TOKENS
            )
            return response["choices"][0]["message"]["content"].strip()

        except (InvalidRequestError, RateLimitError) as e:
            err = str(e).lower()
            if ("maximum context length" in err or "request too large" in err):
                reduction_pct *= 0.8
                _log_trunc("swot", step, reduction_pct, bi_trim, "", err)
                continue
            raise
    raise InvalidRequestError("too_many_retries in generate_swot_analysis")


# ---------- 3.  TAGS -----------------------------------------------------
def generate_solicitation_tags(content: str,
                               description: str,
                               insights: str) -> list[str]:
    """
    GPT tag generation with retry cap.
    """
    import time, os, json, tiktoken
    from openai.error import InvalidRequestError, RateLimitError

    MAX_INTERNAL_RETRIES = 3
    reduction_pct = 1.0
    step = 0
    enc = tiktoken.get_encoding("cl100k_base")
    base_info = f"{description}\n{insights}\n{content}"

    while reduction_pct > 0.05 and step < MAX_INTERNAL_RETRIES:
        step += 1
        bi_trim = base_info[: int(len(base_info) * reduction_pct)]

        prompt = f"""
        Generate 3‑5 short, specific keyword tags (comma‑separated) for this solicitation:
        ---
        {bi_trim}
        """

        try:
            response = openai.ChatCompletion.create(
                model=config.GPT_MODEL_CHAT,
                messages=[
                    {"role": "system",
                     "content": "You specialize in extracting relevant topic tags from text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=256
            )
            return [t.strip() for t in response["choices"][0]["message"]["content"].split(",") if t.strip()]

        except (InvalidRequestError, RateLimitError) as e:
            err = str(e).lower()
            if ("maximum context length" in err or "request too large" in err):
                reduction_pct *= 0.8
                _log_trunc("tags", step, reduction_pct, bi_trim, "", err)
                continue
            raise
    raise InvalidRequestError("too_many_retries in generate_solicitation_tags")


# ---------- helper to log truncation attempts ---------------------------
def _log_trunc(label: str, step: int, pct: float, base_sample: str, txt_sample: str, err: str):
    os.makedirs("truncated_logs", exist_ok=True)
    path = f"truncated_logs/{label}_{int(time.time())}_{step}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "step": step,
            "reduction_pct": pct,
            "base_sample": base_sample[:1000],
            "text_sample": txt_sample[:1000],
            "error": err
        }, f, indent=2, ensure_ascii=False)



def generate_news_impact_paragraph(insights: str,
                                   article: dict,
                                   company_details: dict) -> str:
    """
    If an article is relevant, call GPT for a short paragraph explaining
    how this news might impact the company's performance if they secure the bid.
    
    :param insights: The previously generated insights about the solicitation.
    :param article: A dict with 'title', 'description', 'content' for the news story.
    :param company_details: A dict describing the company's name, strengths, past performance, etc.
    :return: A short GPT-generated paragraph discussing potential positive/negative impacts.
    """
    prompt = f"""
    You are an analyst assessing how a recent news article might impact the performance or outcome
    of a government contract. Here is the data:

    Company Info: {company_details}

    Solicitation Insights:
    {insights}

    News Article:
    Title: {article.get('title', '')}
    Description: {article.get('description', '')}
    Content: {article.get('content', '')}

    Please provide a 3-4 brief and concise bullet points on how the event/news in this article could positively or negatively
    affect the company's performance if they secure this bid.
    """

    response = openai.ChatCompletion.create(
        model=config.GPT_MODEL_CHAT,
        messages=[
            {"role": "system", "content": "You are an expert in analyzing the impact of current events on bids."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,         # Slightly lower temp for more concise paragraphs
        max_tokens=256
    )
    return response["choices"][0]["message"]["content"].strip()
