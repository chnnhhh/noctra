"""Scraping subsystem for Noctra."""

from .metadata import ScrapingMetadata
from .official import OfficialMetadataProvider

__all__ = ["ScrapingMetadata", "OfficialMetadataProvider"]
