from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into the process environment (not just into Settings below) so
# LiteLLM -- which reads provider credentials (OPENAI_API_KEY, GROQ_API_KEY,
# ANTHROPIC_API_KEY, ...) straight from os.environ based on the model string's
# provider prefix -- can find whichever provider's key is set, without this
# app having to special-case any one provider.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""

    careflow_llm_model: str = "gpt-4o-mini"
    careflow_judge_model: str = "gpt-4o-mini"

    careflow_data_dir: Path = Path("./data/careflow")
    careflow_qdrant_path: Path = Path("./data/careflow/qdrant_store")
    careflow_qdrant_collection: str = "careflow_policy_corpus"
    careflow_bm25_index_path: Path = Path("./data/careflow/bm25_index.pkl")
    careflow_patient_memory_db: Path = Path("./data/careflow/memory/patient_memory.sqlite")
    careflow_workflow_checkpoint_db: Path = Path("./data/careflow/memory/workflow_checkpoints.sqlite")

    careflow_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    careflow_reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    careflow_ehr_circuit_failure_threshold: int = 3
    careflow_ehr_circuit_recovery_seconds: float = 30.0
    careflow_ehr_retry_attempts: int = 2

    @property
    def corpus_markdown_dir(self) -> Path:
        return self.careflow_data_dir / "corpus" / "markdown"

    @property
    def corpus_pdf_dir(self) -> Path:
        return self.careflow_data_dir / "corpus" / "pdf"

    @property
    def mock_ehr_dir(self) -> Path:
        return self.careflow_data_dir / "mock_ehr"

    @property
    def intake_messages_path(self) -> Path:
        return self.careflow_data_dir / "intake_messages" / "intake_messages.jsonl"

    @property
    def session_memory_dir(self) -> Path:
        return self.careflow_data_dir / "memory" / "sessions"

    @property
    def human_queue_path(self) -> Path:
        return self.careflow_data_dir / "human_queue.jsonl"

    @property
    def has_llm_key(self) -> bool:
        return bool(self.openai_api_key or self.groq_api_key or self.anthropic_api_key)

    @property
    def has_langfuse_keys(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def golden_eval_path(self) -> Path:
        return self.careflow_data_dir / "eval" / "golden_eval.jsonl"

    @property
    def golden_eval_results_path(self) -> Path:
        return self.careflow_data_dir / "eval" / "golden_eval_results.jsonl"


settings = Settings()
