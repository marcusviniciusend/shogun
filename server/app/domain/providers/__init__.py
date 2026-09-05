"""Implementações concretas de `PendenciasProvider`."""

from .maestri import MaestriProvider
from .shogun_orquestrador import ShogunOrquestradorProvider

__all__ = ["MaestriProvider", "ShogunOrquestradorProvider"]
