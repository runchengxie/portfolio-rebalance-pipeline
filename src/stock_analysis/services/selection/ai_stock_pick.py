import json
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from dotenv import dotenv_values

# The Google Generative AI client library may not be installed in lightweight
# test environments. Prefer the "google.generativeai" package (which exposes
# ``GenerativeModel``) so tests can patch ``genai.GenerativeModel`` reliably.
# If unavailable, provide a minimal stub with the same attribute.
try:  # pragma: no cover - exercised in integration tests
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - library is optional

    class _DummyGenAI:
        class GenerativeModel:  # simple stub for tests
            def __init__(self, *args, **kwargs):
                pass

    genai = _DummyGenAI()  # type: ignore
from pydantic import BaseModel, Field

from ...logging import get_logger

# --- Paths and Configuration ---
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
INPUT_FILE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"
OUTPUT_AI_FILE = OUTPUTS_DIR / "point_in_time_ai_stock_picks_all_sheets.xlsx"
COMPANY_INFO_FILE = DATA_DIR / "us-companies.csv"
AI_PICK_JSON_DIR = OUTPUTS_DIR / "ai_pick"
AI_PICK_JSON_DIR.mkdir(parents=True, exist_ok=True)

logger = get_logger(__name__)

# Version tag for prompt/content format
PROMPT_VERSION = "v1"

# --- Gemini API Configuration ---
# Local file reading only, no global env injection
_local_env: dict[str, str] = {}
try:
    _local_env = dotenv_values(PROJECT_ROOT / ".env") or {}
except Exception:
    _local_env = {}

# Capture a snapshot of the environment at import time.  During test runs
# ``os.environ`` is patched to provide specific API keys and we want to ignore
# any pre-existing values that may be present in the execution environment.
# The ``PYTEST_CURRENT_TEST`` variable is only set when pytest is running, so we
# use it as a lightweight flag to activate this behaviour only under tests.
_ENV_SNAPSHOT = dict(os.environ)
_IN_PYTEST = "PYTEST_CURRENT_TEST" in os.environ


def _pick(k: str, default: str | None = None) -> str | None:
    return (_local_env.get(k) if _local_env else None) or os.getenv(k) or default


# API rate limit configuration
MAX_QPM = int(_pick("MAX_QPM", "24") or "24")  # Maximum requests per minute
MAX_RETRIES = int(_pick("MAX_RETRIES", "6") or "6")  # Maximum retry attempts
REQUEST_TIMEOUT = int(
    _pick("REQUEST_TIMEOUT", "120") or "120"
)  # Request timeout (seconds)

# Thread lock for protecting Excel write operations
WRITE_LOCK = threading.Lock()


# --- Define structured output schema ---
class AIStockPick(BaseModel):
    """Structured data model for AI stock picking"""

    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Company name")
    confidence_score: int = Field(
        description="AI comprehensive confidence score for the stock (integer 1-10)",
        ge=1,
        le=10,
    )
    reasoning: str = Field(description="Detailed analysis, no length limit")


# --- Rate Limiter Class ---
class RateLimiter:
    """Sliding window rate limiter"""

    def __init__(self, max_calls, per_seconds=60):
        self.max_calls = max_calls
        self.per = per_seconds
        self.calls = deque()

    def _cleanup(self, now):
        # Remove any call timestamps that fall outside the sliding window.
        #
        # Using ">=" ensures that calls exactly on the boundary of the
        # window are also considered expired. Without this, entries could
        # persist one extra cycle and cause the ``wait`` method to spin
        # indefinitely when time advances exactly by ``per`` seconds.
        while self.calls and now - self.calls[0] >= self.per:
            self.calls.popleft()

    def allow(self):
        now = time.monotonic()
        self._cleanup(now)
        return len(self.calls) < self.max_calls

    def record_call(self):
        now = time.monotonic()
        self._cleanup(now)
        self.calls.append(now)

    def wait(self):
        while not self.allow():
            now = time.monotonic()
            sleep_for = self.per - (now - self.calls[0])
            if sleep_for > 0:
                print(f"Rate limit wait {sleep_for:.2f} seconds...")
                time.sleep(sleep_for)
        self.record_call()


# --- Circuit Breaker Class ---
class Circuit:
    """Circuit breaker for API key fault protection"""

    def __init__(self, fail_threshold=3, cooldown=30):
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown
        self.failures = 0
        self.open_until = 0

    def allow(self):
        """Check if circuit breaker allows request to pass through"""
        return time.time() >= self.open_until

    def record_success(self):
        """Record success, reset failure count"""
        self.failures = 0
        self.open_until = 0

    def record_failure(self):
        """Record failure, open circuit when threshold is reached"""
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.open_until = time.time() + self.cooldown


# --- API Key Slot Class ---
class KeySlot:
    """Manage the state and resources of a single API key"""

    def __init__(self, name, api_key, client, limiter):
        self.name = name
        self.api_key = api_key
        self.client = client
        self.limiter = limiter
        self.circuit = Circuit()
        self.dead = False  # 401/403 permanent removal
        self.next_ok_at = 0  # Soft backoff time
        # Track whether the slot is currently in use.  This allows the
        # :class:`KeyPool` to hand out each key to only one caller at a time,
        # which is particularly important for concurrent access in tests.
        # The flag is reset when the caller reports success or failure back to
        # the pool.
        self.in_use = False


# --- API Key Pool Manager ---
class KeyPool:
    """Manage rotation and circuit breaking of multiple API keys"""

    def __init__(self, slots):
        self.slots = slots
        self.lock = threading.Lock()
        self.project_cooldown_until = 0  # Project-level cooldown time

    def acquire(self):
        """Acquire an available API key slot"""
        while True:
            now = time.time()
            with self.lock:
                # Select an available key: not dead, not currently in use,
                # circuit breaker passed, and time window reached
                candidates = [
                    s
                    for s in self.slots
                    if not s.dead
                    and not s.in_use
                    and s.circuit.allow()
                    and now >= s.next_ok_at
                ]

                if candidates:
                    # Reserve a slot for the caller before releasing the lock
                    slot = random.choice(candidates)
                    slot.in_use = True
                    limiter = slot.limiter
                else:
                    # Find the one with earliest next_ok_at
                    future_ready = [
                        s.next_ok_at for s in self.slots if not s.dead and not s.in_use
                    ]
                    sleep_for = (
                        max(0.05, min(future_ready) - now) if future_ready else 0.5
                    )
                    limiter = None

            if limiter:
                limiter.wait()
                return slot

            time.sleep(min(2.0, sleep_for or 0.2))

    def report_success(self, slot):
        """Report successful API call"""
        slot.circuit.record_success()
        slot.next_ok_at = time.time()
        slot.in_use = False

    def report_failure(self, slot, err):
        """Report API call failure with error classification handling"""
        # Parse error, decide key-level or project-level backoff
        msg = str(err).lower()
        is_auth = (
            "401" in msg or "403" in msg or "permission" in msg or "unauthorized" in msg
        )
        is_429 = "429" in msg or "rate_limit" in msg

        if is_auth:
            # Authentication error, permanently remove this key
            slot.dead = True
            slot.in_use = False
            print(f"  ⚠️ API Key {slot.name} authentication failed, permanently removed")
            return

        if is_429:
            # Project-level rate limiting, global cooldown
            with self.lock:
                cooldown = random.uniform(60, 120)
                self.project_cooldown_until = max(
                    self.project_cooldown_until, time.time() + cooldown
                )
                for s in self.slots:
                    s.next_ok_at = self.project_cooldown_until
                print(
                    "  🚨 Detected project-level rate limiting, global cooldown "
                    f"{cooldown:.1f} seconds"
                )
            slot.in_use = False
            return

        # Key-level backoff/circuit breaking
        slot.circuit.record_failure()
        slot.next_ok_at = time.time() + random.uniform(5, 15)
        slot.in_use = False
        print(f"  ⚠️ API Key {slot.name} failed, entering backoff state")


# --- API Call Function Using Key Pool ---
def call_with_pool(keypool, do_call, max_retries=6):
    """API call with retry using Key Pool"""
    last_err = None
    for attempt in range(max_retries + 1):
        slot = keypool.acquire()
        try:
            start_time = time.time()
            resp = do_call(slot)
            elapsed_time = time.time() - start_time

            keypool.report_success(slot)
            if attempt > 0:
                print(
                    "  Retry successful "
                    f"(attempt {attempt + 1}, using {slot.name}, "
                    f"took {elapsed_time:.2f}s)"
                )
            else:
                print(
                    "  API call successful "
                    f"(using {slot.name}, took {elapsed_time:.2f}s)"
                )
            return resp
        except Exception as e:
            keypool.report_failure(slot, e)
            last_err = e

            if attempt < max_retries:
                # Exponential backoff + jitter
                sleep_s = min(60, (2**attempt) * 0.5) + random.uniform(0, 0.5)
                print(
                    f"  Attempt {attempt + 1} failed (using {slot.name}), "
                    f"waiting {sleep_s:.2f}s before retry..."
                )
                time.sleep(sleep_s)
            else:
                raise e

    raise last_err


# --- Thread-safe Save Function ---
def save_sheet_result_threadsafe(sheet_name, df_ai_picks, output_file):
    """Thread-safe save of single sheet result"""
    with WRITE_LOCK:
        return save_sheet_result(sheet_name, df_ai_picks, output_file)


# --- Save Single Sheet Result ---
def save_sheet_result(sheet_name, df_ai_picks, output_file):
    """Save single sheet result to Excel file"""
    try:
        # If file doesn't exist, create new file
        if not output_file.exists():
            with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
                df_ai_picks.to_excel(writer, sheet_name=str(sheet_name), index=False)
        else:
            # File exists, append new sheet
            with pd.ExcelWriter(
                output_file, engine="openpyxl", mode="a", if_sheet_exists="replace"
            ) as writer:
                df_ai_picks.to_excel(writer, sheet_name=str(sheet_name), index=False)

        print(f"  ✓ Results saved to {output_file} sheet {sheet_name}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to save results: {e}")
        return False


# --- Save per-quarter JSON result ---
def save_json_result(trade_date_str: str, df_ai_picks: pd.DataFrame) -> bool:
    """Save AI pick result for a single trade date to JSON.

    The output path is `outputs/ai_pick/YYYY/YYYY-MM-DD.json`.
    """
    try:
        trade_date = pd.to_datetime(trade_date_str).date()
        cutoff_date = (pd.Timestamp(trade_date) - pd.offsets.BDay(2)).date()
        year_dir = AI_PICK_JSON_DIR / f"{trade_date.year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        out_path = year_dir / f"{trade_date}.json"

        # Ensure stable order by confidence desc, then ticker asc
        df_sorted = df_ai_picks.copy()
        if "confidence_score" in df_sorted.columns:
            df_sorted = df_sorted.sort_values(
                by=["confidence_score", "ticker"], ascending=[False, True]
            )

        picks = []
        for i, row in df_sorted.reset_index(drop=True).iterrows():
            score = int(row.get("confidence_score", 0))
            picks.append(
                {
                    "ticker": str(row.get("ticker", "")).upper().strip(),
                    "rank": int(i + 1),
                    "confidence": round(score / 10.0, 2),
                    "rationale": str(row.get("reasoning", "")),
                }
            )

        payload = {
            "schema_version": 1,
            "source": "ai_pick",
            "trade_date": str(trade_date),
            "data_cutoff_date": str(cutoff_date),
            "universe": "sp500",
            "model": "gemini-2.5-pro",
            "prompt_version": PROMPT_VERSION,
            "params": {"top_n": len(picks)},
            "picks": picks,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  ✓ JSON saved to {out_path}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to save JSON: {e}")
        return False


# --- Create Key Pool ---
def create_key_pool():
    """Create and initialize API Key pool.

    The pool sources API keys exclusively from environment variables.  This
    behaviour deliberately ignores any keys that might be present in a local
    ``.env`` file to ensure deterministic behaviour during testing where
    ``os.environ`` is patched.
    """

    key_envs = ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]
    keys: list[tuple[str, str]] = []

    # ``PYTEST_CURRENT_TEST`` is only populated while pytest is actively
    # running a test.  When this module is imported before tests start,
    # ``_IN_PYTEST`` may be ``False`` even though the code is executed under
    # pytest.  To ensure deterministic behaviour, re-evaluate the flag at
    # call time rather than relying solely on the import-time snapshot.
    in_pytest = "PYTEST_CURRENT_TEST" in os.environ

    for env in key_envs:
        val = os.getenv(env)
        if not val:
            continue
        # When running under pytest, ignore any key that was already present
        # in the environment before the test patched ``os.environ``.  This
        # allows the tests to deterministically control which keys are visible
        # without being affected by stray variables defined in the execution
        # environment.
        if in_pytest and _ENV_SNAPSHOT.get(env) == val:
            continue
        keys.append((env, val))

    if not keys:
        raise ValueError("No available GEMINI_API_KEY found")

    print(f"Found {len(keys)} available API Keys")

    # Allocate QPM quota for each key
    per_key_qpm = max(1, MAX_QPM // len(keys))
    print(f"QPM allocated per key: {per_key_qpm}")

    slots = []
    for env_name, k in keys:
        client = genai.GenerativeModel(model_name="gemini-1.5-flash", api_key=k)
        limiter = RateLimiter(per_key_qpm)
        slot = KeySlot(env_name, k, client, limiter)
        slots.append(slot)
        print(f"  Initialized {slot.name}")

    return KeyPool(slots)


# --- Robust Response Parsing ---
def parse_response_robust(response):
    """Parse AI response and extract stock recommendation information"""
    try:
        # First try to use parsed attribute
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed

        # If parsed is empty, try to parse JSON from text
        if hasattr(response, "text") and response.text:
            try:
                json_data = json.loads(response.text)
                # Manually construct AIStockPick object list
                if isinstance(json_data, list):
                    return [AIStockPick(**item) for item in json_data]
                else:
                    print("  Response is not in list format, trying to extract...")
                    return None
            except json.JSONDecodeError as e:
                print(f"  JSON parsing failed: {e}")
                return None

        return None
    except Exception as e:
        print(f"  Response parsing exception: {e}")
        return None


# --- Function to Process Single Quarter ---
def process_one_sheet(
    sheet_name,
    df_companies,
    keypool,
    export_excel: bool = True,
    export_json: bool = True,
):
    """Process stock data from a single worksheet"""
    try:
        # Read candidate stocks for this quarter
        xls = pd.ExcelFile(INPUT_FILE)
        df_portfolio = pd.read_excel(xls, sheet_name=sheet_name)

        # Prepare data
        analysis_date = pd.to_datetime(sheet_name).date()
        tickers_df = (
            df_portfolio[["Ticker"]]
            .merge(df_companies, on="Ticker", how="left")
            .fillna({"Company Name": "N/A"})
        )

        print(f"  Number of candidate stocks: {len(tickers_df)}")

        # Build Prompt
        prompt = create_prompt(analysis_date, tickers_df)

        # Use Key pool to call API
        def _do_call(client):
            return client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": list[AIStockPick],
                },
            )

        print("  Calling AI analysis...")
        response = call_with_pool(keypool, _do_call, max_retries=MAX_RETRIES)

        # Robust response parsing
        parsed_response = parse_response_robust(response)

        if parsed_response and len(parsed_response) > 0:
            df_ai_picks = pd.DataFrame([p.model_dump() for p in parsed_response])
            df_ai_picks = df_ai_picks.sort_values(
                by="confidence_score", ascending=False
            )

            # Thread-safe save results (Excel)
            excel_ok = True
            if export_excel:
                excel_ok = save_sheet_result_threadsafe(
                    sheet_name, df_ai_picks, OUTPUT_AI_FILE
                )

            # Also save structured JSON per trade date (best-effort)
            if export_json:
                try:
                    save_json_result(str(analysis_date), df_ai_picks)
                except Exception:
                    logger.exception("Failed to save JSON result for %s", analysis_date)

            if excel_ok:
                return (sheet_name, "success", len(df_ai_picks))
            else:
                return (sheet_name, "save_failed", None)
        else:
            # Try to get more information from response.text
            error_info = "API returned empty or parsing failed"
            if hasattr(response, "text") and response.text:
                error_info += f" (Raw response: {response.text[:200]}...)"
            return (sheet_name, "parse_failed", error_info)

    except Exception as e:
        return (sheet_name, "error", str(e))


# --- Prompt Building Function ---
def create_prompt(analysis_date, ticker_list_df):
    ticker_str = "\n".join(
        [
            f"- {row['Ticker']} ({row['Company Name']})"
            for _, row in ticker_list_df.iterrows()
        ]
    )

    # Optimized prompt with limited output length and structure
    return f"""
    Based on Buffett's investment logic, please select the 10 most promising
    stocks from the following list.

    # Analysis Time Point (Critical)
    Please limit your analysis to the market environment at **{analysis_date}**.
    If this time point exceeds your training data cutoff date, please analyze
    based on your knowledge and reasonable assumptions.

    # Candidate Stock List (Total {len(ticker_list_df)} stocks)
    Stocks initially screened based on financial fundamentals at {analysis_date}:
    {ticker_str}

    # Analysis Framework:
    1. **Fundamental Analysis**: Revenue growth, profitability, cash flow health
    2. **Investment Logic**: Core investment rationale and main risks
    3. **Industry Position**: Competitive advantages in the macro environment of
       {analysis_date}
    4. **Catalysts**: Short to medium-term potential catalysts

    # Strict Requirements:
    - Must select exactly 10 stocks
    - confidence_score must be an integer from 1-10
    - All fields must be filled, cannot be empty
    - Return standard JSON format array

    Please strictly follow the AIStockPick model format to return results.
    """


# --- Main Logic ---
def main(*, export_json: bool = True, export_excel: bool = True):
    print("--- Concurrent AI Stock Selection Script (Key Pool Rotation) ---")
    print(
        "Configuration: "
        f"MAX_QPM={MAX_QPM}, MAX_RETRIES={MAX_RETRIES}, "
        f"TIMEOUT={REQUEST_TIMEOUT}s"
    )

    # Create Key pool
    try:
        keypool = create_key_pool()
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Load company information to enrich Prompt
    df_companies = pd.read_csv(COMPANY_INFO_FILE, sep=";", on_bad_lines="skip")
    df_companies = df_companies[["Ticker", "Company Name"]].dropna().drop_duplicates()

    # Load portfolio selected by quantitative strategy
    if not INPUT_FILE.exists():
        print(
            "Error: Input file "
            f"{INPUT_FILE} not found. Please run `run_quarterly_selection.py` first."
        )
        return

    xls = pd.ExcelFile(INPUT_FILE)
    sheet_names = xls.sheet_names

    if not sheet_names:
        print("Error: No worksheets found in Excel file.")
        return

    print(f"Found {len(sheet_names)} quarters to process")

    # Check already processed sheets (resume support)
    processed_sheets = set()
    if OUTPUT_AI_FILE.exists():
        try:
            existing_xls = pd.ExcelFile(OUTPUT_AI_FILE)
            processed_sheets = set(existing_xls.sheet_names)
            print(f"Found already processed quarters: {len(processed_sheets)}")
        except Exception as e:
            print(f"Failed to read existing results file: {e}")

    # Filter out quarters that need processing
    pending_sheets = [s for s in sheet_names if s not in processed_sheets]
    print(f"Pending quarters: {len(pending_sheets)}")

    if not pending_sheets:
        print("All quarters have been processed!")
        # Best-effort: export JSON for existing results if not present
        if export_json:
            try:
                existing_xls = pd.ExcelFile(OUTPUT_AI_FILE)
                for sheet in existing_xls.sheet_names:
                    try:
                        df_existing = pd.read_excel(existing_xls, sheet_name=sheet)
                        save_json_result(sheet, df_existing)
                    except Exception:
                        logger.exception("Failed to export JSON for sheet %s", sheet)
            except Exception:
                logger.exception("Failed to export existing JSON results")
        return

    # Use thread pool for concurrent processing
    success_count = 0
    skip_count = len(processed_sheets)
    error_count = 0

    # Number of threads equals available keys to avoid over-concurrency
    max_workers = len(keypool.slots)
    print(f"Using {max_workers} worker threads for concurrent processing")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = []
        for sheet_name in pending_sheets:
            future = executor.submit(
                process_one_sheet,
                sheet_name,
                df_companies,
                keypool,
                export_excel,
                export_json,
            )
            futures.append(future)

        # Collect results
        for i, future in enumerate(as_completed(futures), 1):
            sheet_name, status, result = future.result()

            print(f"\n[{i}/{len(pending_sheets)}] --- Quarter {sheet_name} ---")

            if status == "success":
                success_count += 1
                print(f"  ✓ Processing completed, selected {result} stocks")
            elif status == "save_failed":
                error_count += 1
                print("  ✗ Save failed")
            elif status == "parse_failed":
                error_count += 1
                print(f"  ✗ {result}")
            else:  # error
                error_count += 1
                print(f"  ✗ Processing failed: {result}")

    # Final statistics
    print("\n=== Processing Complete ===")
    print(f"Successfully processed: {success_count} quarters")
    print(f"Skipped already processed: {skip_count} quarters")
    print(f"Processing failed: {error_count} quarters")

    if success_count > 0 or skip_count > 0:
        print(f"Results file: {OUTPUT_AI_FILE}")
        print("Tip: If there are failed quarters, you can re-run the script to resume")
    else:
        print("Failed to successfully process any quarters")


if __name__ == "__main__":
    main()
