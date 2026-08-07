"""Project-wide constants."""

from __future__ import annotations

# Redis key namespaces
REDIS_JOB_QUEUE = "zymis:jobs"
REDIS_RESULT_PREFIX = "zymis:result:"
REDIS_STATE_PREFIX = "aiswarm:state:"
REDIS_LOCK_PREFIX = "aiswarm:lock:"

# Default models by role
DEFAULT_BOSS_MODEL = "meta-llama/llama-3.1-70b-instruct"
DEFAULT_MANAGER_MODEL = "meta-llama/llama-3.1-70b-instruct"
DEFAULT_CODER_MODEL = "meta-llama/llama-3.1-405b-instruct"
DEFAULT_CRITIC_MODEL = "meta-llama/llama-3.1-70b-instruct"
DEFAULT_PRECHECK_MODEL = "meta-llama/llama-3.1-8b-instruct"
DEFAULT_PROVIDER = "novita"

# Retry policy
MAX_RETRIES = 5
DEADLOCK_TIMEOUT = 300  # seconds
CHECKPOINT_INTERVAL = 60  # seconds

# Review thresholds
CRITIC_APPROVAL_THRESHOLD = 2   # need 2/3 critics to approve
MIN_CRITIC_SCORE = 70           # below this → REJECT

# Code quality
MIN_CODE_LENGTH = 50            # characters
MAX_PROMPT_FILES = 15
MAX_PROMPT_TOKENS = 100_000

# Storage paths
STORAGE_ROOT = "./storage"
ARTIFACTS_DIR = "./storage/artifacts"
PROMPTS_DIR = "./storage/prompts"
TASKS_DIR = "./storage/tasks"
LOGS_DIR = "./storage/logs"
BENCHMARKS_DIR = "./storage/benchmarks"
VECTOR_DB_DIR = "./storage/vector_db"
CACHE_DIR = "./storage/cache"
CHECKPOINT_DIR = "./storage/checkpoints"
TASK_HISTORY_DIR = "./task_history"
