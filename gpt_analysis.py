# gpt_analysis.py

import openai
import config
from file_utils import extract_text_from_pdfs, truncate_to_token_limit
import os
import json
import time
import pandas as pd
import json
import requests

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


def generate_chart_insight(chart_data: pd.DataFrame, chart_type: str, company_details: dict) -> str:
    """
    Generate a strategic insight paragraph for a company based on chart data.
    """
    try:
        csv_sample = chart_data.head(20).to_csv(index=False)

        prompt = f"""
        You are a federal contract strategist analyzing historical award data to generate insights for a company.

        Company Information:
        {json.dumps(company_details, indent=2)}

        Chart Type:
        {chart_type}

        Chart Data (CSV Format):
        {csv_sample}

        Based on this information, provide a strategic 2–4 sentence insight for the company.
        Focus on competitive positioning, opportunities, or warnings based on the data.
        """

        response = openai.ChatCompletion.create(
            model=config.GPT_MODEL_CHAT,
            messages=[
                {"role": "system", "content": "You are a strategic analyst for government contracts."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=300
        )
        return response["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"[Insight generation failed: {e}]"



def fetch_perplexity_summary(company_name: str, perplexity_key: str) -> str:
    """
    Query the Perplexity API to get a company overview with government contracting focus.
    """
    headers = {
        "Authorization": f"Bearer {perplexity_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "sonar-pro",
        "messages": [
            {
                "role": "user",
                "content": f"Summarize what the company {company_name} does, especially in the context of U.S. federal contracts. Highlight strengths, focus areas, and past performance."
            }
        ]
    }

    try:
        response = requests.post("https://api.perplexity.ai/chat/completions", headers=headers, json=data)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Error fetching summary for {company_name}: {e}]"


def generate_competitor_positioning_insight(top_df: pd.DataFrame,
                                            client_info: dict,
                                            perplexity_key: str) -> str:
    """
    Generate a strategic insight on how the client can position themselves
    against the top federal awardees based on live Perplexity web results.
    """
    import openai

    # Pull top 10 company names
    top_companies = top_df["recipient_name"].head(10).tolist()
    company_profiles = {}

    for name in top_companies:
        summary = fetch_perplexity_summary(name, perplexity_key)
        company_profiles[name] = summary

    # Construct prompt
    prompt = f"""
You are a senior strategic advisor for a government contractor.

Your client is:
{json.dumps(client_info, indent=2)}

The following companies are the top 10 recipients of federal awards in this NAICS code:
{top_companies}

Below are Perplexity-based summaries of these companies and their competitive positioning:

{json.dumps(company_profiles, indent=2)}

Based on this information:
- Recommend whether the client should target or avoid competing with any of these companies.
- Explain which competitors represent threats vs. opportunities.
- Suggest a clear positioning strategy for the client that exploits unique advantages or avoids vulnerable areas.

Be candid, strategic, and insightful. Avoid generic statements. Focus on specifics where possible.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a strategic advisor for government contractors."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=700
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[GPT Insight Generation Error: {e}]"
