"""Preregistered counting-authority identity registry."""

from election_guide.authorities.models import Authority, AuthorityRegistry
from election_guide.authorities.registry import read_authority_registry

__all__ = ["Authority", "AuthorityRegistry", "read_authority_registry"]
