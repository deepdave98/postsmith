"""Pin the suite to rubric v1.

Fixtures carry v1's version stamp and v1's expectations, and judge_io rejects any judge file whose stamp is
not the rubric in force. Reading the live `evals/rubric/current` symlink therefore made the suite's colour
depend on which rubric happened to be promoted: it went from green to 40 red on 2026-09-20 when v2 was
promoted, with nothing broken. v1 is immutable by contract, so it is the right thing to test against.

Set at import, as an environment variable, because many tests shell out to the tools and a child process
only inherits what is in the environment.
"""
import os

os.environ.setdefault("POSTSMITH_RUBRIC", "v1")
