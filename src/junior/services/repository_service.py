"""Repository analysis service."""

import structlog

from ..agent import RepositoryAnalyzer

logger = structlog.get_logger(__name__)


class RepositoryService:
    """Service for repository analysis operations."""

    def __init__(self):
        self.logger = logger.bind(component="RepositoryService")
        self._analyzer = None

    def _get_analyzer(self) -> RepositoryAnalyzer:
        """Get MCP analyzer instance."""
        if not self._analyzer:
            self._analyzer = RepositoryAnalyzer()
        return self._analyzer

    async def analyze_repository(
        self, repository: str, head_sha: str, base_sha: str
    ) -> tuple[dict[str, str], dict]:
        """Analyze repository structure and get relevant file contents."""
        try:
            # Use MCP tools to analyze repository
            mcp_analyzer = self._get_analyzer()
            analysis_result = await mcp_analyzer.analyze_repository(
                repository=repository, head_sha=head_sha, base_sha=base_sha
            )

            return analysis_result["file_contents"], analysis_result[
                "project_structure"
            ]

        except Exception as e:
            self.logger.error(
                "Repository analysis failed", repo=repository, error=str(e)
            )
            # Return empty analysis if MCP fails
            return {}, {}
