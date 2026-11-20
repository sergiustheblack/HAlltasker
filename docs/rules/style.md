# Code style

- Type annotations everywhere. `from __future__ import annotations` in every
  module.
- Dataclasses from the architecture are `frozen=True`, except `Link`.
- Core functions are pure: input → output, no global state, no access to the
  time (`now` is passed as a parameter).
- Logger: `_LOGGER = logging.getLogger(__package__)`.
- Comments and docstrings in English, one line, only where the name does not
  explain the purpose.
