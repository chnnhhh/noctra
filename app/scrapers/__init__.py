"""Scraping subsystem for Noctra."""

from .metadata import ScrapingMetadata
from .javdb import JavDBCrawler

__all__ = ['ScrapingMetadata', 'JavDBCrawler']
