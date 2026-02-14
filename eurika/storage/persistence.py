"""Legacy re-exports for persistence. Prefer eurika.storage.ProjectMemory.

Single entry point: ProjectMemory(project_root) → .feedback, .learning,
.observations, .history. Implementation modules: observation_memory,
architecture_feedback, architecture_learning; history in eurika.evolution.
"""

from observation_memory import *  # noqa: F401,F403
from architecture_feedback import *  # noqa: F401,F403
from architecture_learning import *  # noqa: F401,F403

