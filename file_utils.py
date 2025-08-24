# file_utils.py

import os
import requests
import subprocess

import config
from PyPDF2 import PdfReader
import tiktoken
from docx import Document as DocxDocument


from typing import Optional

def download_attachment(reference: str, file_name: str) -> Optional[str]:
    """
    Attempts to download an attachment using two possible URL formats.
    Now tries what was previously Method 2 first, then Method 1 as a fallback.

    :param reference: The unique reference ID (often from the EU solicitation data).
    :param file_name:   The name of the file to be downloaded.
    :return:            The local file path if downloaded successfully, else None.
    """
    os.makedirs(config.ATTACHMENTS_DIR, exist_ok=True)

    # If reference ends with 'en', strip it (mirroring your original logic).
    if reference.endswith("en"):
        reference = reference[:-2]

    # Construct two possible download URLs:
    file_url_2 = (
        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities"
        f"/tender-details/docs/{reference}/{file_name}"
    )
    file_url_1 = (
        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities"
        f"/tender-details/docs/etender/{reference}/{file_name}"
    )

    file_path = os.path.join(config.ATTACHMENTS_DIR, file_name)

    # Try Method 2 first:
    resp = requests.get(file_url_2)
    if resp.status_code == 200:
        with open(file_path, "wb") as f:
            f.write(resp.content)
        print(f"✅ Downloaded (Method 2): {file_name}")
        return file_path

    # Fallback to Method 1:
    print(f"⚠️ Failed Method 2 for {file_name}, trying Method 1...")
    resp = requests.get(file_url_1)
    if resp.status_code == 200:
        with open(file_path, "wb") as f:
            f.write(resp.content)
        print(f"✅ Downloaded (Method 1): {file_name}")
        return file_path

    print(f"❌ Failed to download {file_name} with both methods.")
    return None


def download_attachment_sam(resource_id: str, filename: str) -> Optional[str]:
    """
    Download and save an attachment from SAM.gov based on its resource_id.
    Returns the local filepath if successful, else None.
    """
    url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resource_id}/download"
    resp = requests.get(url, stream=True)
    if resp.status_code == 200:
        os.makedirs(config.ATTACHMENTS_DIR, exist_ok=True)
        filepath = os.path.join(config.ATTACHMENTS_DIR, filename)
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)
        print(f"✅ Downloaded: {filename}")
        return filepath
    else:
        print(f"❌ Error downloading {filename}: HTTP {resp.status_code}")
        return None


def extract_text_from_pdfs(pdf_files: list[str]) -> str:
    """
    Extracts text from a list of PDF files and returns the combined text.
    If a file can't be read, logs a warning and continues.

    :param pdf_files: List of PDF file paths.
    :return:          Combined extracted text from all pages of all PDFs,
                      or "No extractable text." if none.
    """
    combined_segments = []

    for pdf in pdf_files:
        print(f"🔍 Extracting text from PDF: {pdf}")
        try:
            reader = PdfReader(pdf)
            pages_text = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    pages_text.append(txt)
            if pages_text:
                combined_segments.append(" ".join(pages_text))
        except Exception as e:
            print(f"⚠️ Error extracting text from PDF {pdf}: {e}")

    if combined_segments:
        return "\n\n".join(combined_segments)
    else:
        return "No extractable text."


def extract_text_from_docx(file_path: str) -> str:
    """
    Extracts text from a .docx file using python-docx.
    :param file_path: Path to the local .docx.
    :return:          Combined text of all non-blank paragraphs, or "" on failure.
    """
    try:
        doc = DocxDocument(file_path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paras)
    except Exception as e:
        print(f"⚠️ Error extracting text from .docx {file_path}: {e}")
        return ""


def extract_text_from_doc(file_path: str) -> str:
    """
    Extracts text from a .doc file by calling the `antiword` command‐line tool.
    Returns the extracted text or "" if antiword is not installed / fails.
    :param file_path: Path to the local .doc.
    :return:          Text extracted via antiword, or "" on error.
    """
    try:
        # Run: antiword <file_path>
        completed = subprocess.run(
            ["antiword", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,  # We'll handle non-zero exit ourselves
        )

        if completed.returncode == 0:
            text = completed.stdout.decode("utf-8", errors="ignore")
            return text
        else:
            err = completed.stderr.decode("utf-8", errors="ignore")
            print(f"⚠️ antiword failed on {file_path}: {err.strip()}")
            return ""
    except FileNotFoundError:
        print(f"⚠️ antiword is not installed. Cannot extract text from {file_path}")
        return ""
    except Exception as e:
        print(f"⚠️ Unexpected error running antiword on {file_path}: {e}")
        return ""

def extract_text_from_xlsx(file_path: str) -> str:
    """
    Extracts text from .xls/.xlsx by reading all sheets via pandas.
    """
    try:
        import pandas as pd
        sheets = pd.read_excel(file_path, sheet_name=None)
        parts = []
        for name, df in sheets.items():
            parts.append(f"[Sheet: {name}]")
            # Keep it readable: no index, limit very wide spreadsheets
            parts.append(df.to_string(index=False, max_rows=100, max_cols=20))
        return "\n\n".join(parts).strip()
    except Exception as e:
        print(f"⚠️ Error extracting text from spreadsheet {file_path}: {e}")
        return ""


def extract_text_from_files(file_paths: list[str]) -> str:
    """
    Given a list of file paths (.pdf, .docx, .doc), extract their text
    and return a single concatenated string. Unsupported extensions are skipped.

    :param file_paths: List of local file paths.
    :return:           Combined text from all supported files, or
                       "No extractable text." if none succeeded.
    """
    segments = []

    for fp in file_paths:
        if not os.path.exists(fp):
            continue

        ext = os.path.splitext(fp.lower())[1]
        print(f"⮕ Now processing '{fp}', detected extension = '{ext}'")
        if ext == ".pdf":
            print("processing pdf")
            print(fp)
            pdf_txt = extract_text_from_pdfs([fp])
            if pdf_txt and pdf_txt != "No extractable text.":
                segments.append(pdf_txt)

        elif ext == ".docx":
            print("processing docx")
            print(fp)
            docx_txt = extract_text_from_docx(fp)
            if docx_txt:
                print(docx_txt)
                segments.append(docx_txt)

        elif ext == ".doc":
            doc_txt = extract_text_from_doc(fp)
            if doc_txt:
                segments.append(doc_txt)
        
        elif ext in (".xls", ".xlsx"):
            xls_txt = extract_text_from_xlsx(fp)
            if xls_txt:
                segments.append(xls_txt)


        else:
            print(f"⚠️ Skipping unsupported file type: {fp}")
            continue

    if segments:
        return "\n\n".join(segments)
    else:
        return "No extractable text."


def truncate_to_token_limit(text: str, max_tokens: int, model: str = "gpt-4") -> str:
    """
    Truncate a long text to fit under the specified token limit for a given model.
    Relies on tiktoken to count and decode tokens.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    tokens = encoding.encode(text)
    print(f"🔢 Original token count: {len(tokens)}")

    if len(tokens) <= max_tokens:
        return text

    truncated = tokens[:max_tokens]
    print(f"⚠️ Truncated to {len(truncated)} tokens")
    return encoding.decode(truncated)


def filter_attachments(file_paths: list[str]) -> list[str]:
    """
    Given a list of local file‐paths, return only those that:
      • actually exist on disk, AND
      • are ≤ 1 MB in size, OR
      • whose filename (lowercased) contains any of:
          “rfp”, “request for proposal”, “proposal”, “sow”, “statement of work”

    :param file_paths: List of local file paths (any extension).
    :return:           A filtered list containing only paths that satisfy the rules.
    """
    kept = []
    for f in file_paths:
        if not os.path.exists(f):
            continue

        name = os.path.basename(f).lower()
        size_mb = os.path.getsize(f) / (1024 * 1024)
        keep = (size_mb <= 1) or any(
            k in name
            for k in ("rfp", "request for proposal", "proposal", "sow", "statement of work")
        )
        if keep:
            kept.append(f)

    return kept
