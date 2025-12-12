"""Journaling functionality for reflective agent logging."""

from datetime import datetime
from typing import Any
import os


def format_journal_entry(
    content: str,
    entry_type: str,
    alternatives: list[str] | None = None,
    confidence: str | None = None,
) -> str:
    """Format a journal entry with timestamp and metadata.

    Args:
        content: The reflective journal entry content
        entry_type: Type of entry (e.g., "decision", "learning", "feeling")
        alternatives: Optional list of alternatives considered
        confidence: Optional confidence level ("high", "medium", "low")

    Returns:
        Formatted journal entry string with timestamp and metadata
    """
    # Get current timestamp in local timezone
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Start with timestamp and type
    lines = [f"[{timestamp}] {entry_type}: {content}", ""]

    # Add alternatives if provided
    if alternatives and len(alternatives) > 0:
        alternatives_str = ", ".join(alternatives)
        lines.append(f"Alternatives considered: {alternatives_str}")
        lines.append("")

    # Add confidence if provided
    if confidence:
        lines.append(f"Confidence: {confidence}")
        lines.append("")

    # Add separator
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def construct_journal_path(
    project_dir: str | None,
    agent: str,
) -> str:
    """Construct the journal file path.

    Path structure:
    - With project_dir: {project_dir}/work-logs/{YYYY-MM-DD}/{agent}.log
    - Without project_dir: work-logs/{YYYY-MM-DD}/{agent}.log

    Args:
        project_dir: Optional Obsidian project directory path
        agent: Agent name (e.g., "main", "architect")

    Returns:
        Relative path to journal file
    """
    # Get today's date for the directory
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Construct path based on whether project_dir is provided
    if project_dir:
        # Remove leading/trailing slashes from project_dir for consistency
        project_dir = project_dir.strip("/")
        return f"{project_dir}/work-logs/{date_str}/{agent}.log"
    else:
        return f"work-logs/{date_str}/{agent}.log"


def validate_parameters(
    content: str,
    entry_type: str,
    agent: str,
    confidence: str | None = None,
) -> None:
    """Validate journal entry parameters.

    Args:
        content: The journal entry content
        entry_type: Type of entry
        agent: Agent name
        confidence: Optional confidence level

    Raises:
        ValueError: If parameters are invalid
    """
    if not content or not content.strip():
        raise ValueError("content is required and cannot be empty")

    if not entry_type or not entry_type.strip():
        raise ValueError("type is required and cannot be empty")

    if not agent or not agent.strip():
        raise ValueError("agent is required and cannot be empty")

    # Validate agent name doesn't contain path-breaking characters
    invalid_chars = ['/', '\\', '\0', '\n', '\r']
    for char in invalid_chars:
        if char in agent:
            raise ValueError(f"agent name cannot contain '{char}' character")

    # Validate confidence if provided
    if confidence and confidence not in ["high", "medium", "low"]:
        raise ValueError(f"confidence must be 'high', 'medium', or 'low', got: {confidence}")
