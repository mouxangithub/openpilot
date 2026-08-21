"""Compatibility shim — use `ai.tools.domains.platform.issue_template_lib` instead."""

from ai.tools.domains.platform import issue_template_lib as _impl
from ai.tools.domains.platform.issue_template_lib import *  # noqa: F403

# Private helpers used by forge/github.py — not re-exported by `import *`.
_parse_github_issue_yaml = _impl._parse_github_issue_yaml
decode_github_content = _impl.decode_github_content
load_local_repo_templates = _impl.load_local_repo_templates
