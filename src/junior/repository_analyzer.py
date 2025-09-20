"""Repository analysis service for comprehensive code understanding."""

import asyncio
import time
from typing import Dict, List, Optional

import structlog

from .config import settings
from .github_client import GitHubClient
from .mcp_tools import MCPRepositoryAnalyzer
from .models import RepositoryAnalysis

logger = structlog.get_logger(__name__)


class RepositoryAnalyzer:
    """Service for analyzing repository structure and content."""
    
    def __init__(self):
        self.logger = logger.bind(component="RepositoryAnalyzer")
        self.github_client = GitHubClient()
        self.mcp_analyzer = MCPRepositoryAnalyzer()
    
    async def analyze_pr_context(
        self, 
        repository: str, 
        pr_number: int, 
        head_sha: str, 
        base_sha: str
    ) -> Dict:
        """Analyze PR context including repository structure and changed files."""
        start_time = time.time()
        
        self.logger.info("Starting PR context analysis", 
                         repo=repository, 
                         pr=pr_number,
                         head_sha=head_sha[:8],
                         base_sha=base_sha[:8])
        
        try:
            # Get basic PR information
            pr_info = await self._get_pr_info(repository, pr_number)
            
            # Perform repository analysis with MCP tools
            repo_analysis = await self.mcp_analyzer.analyze_repository(
                repository=repository,
                head_sha=head_sha,
                base_sha=base_sha,
                max_files=settings.max_files_per_pr
            )
            
            # Get additional context
            context = await self._enrich_analysis_context(
                repository, 
                repo_analysis,
                pr_info
            )
            
            # Structure the final analysis
            analysis_result = {
                "repository": repository,
                "pr_number": pr_number,
                "pr_info": pr_info,
                "project_analysis": RepositoryAnalysis(
                    project_type=repo_analysis["project_structure"].get("project_type", "unknown"),
                    main_language=repo_analysis["project_structure"].get("main_language", "unknown"),
                    frameworks=repo_analysis["project_structure"].get("frameworks", []),
                    dependencies=repo_analysis["project_structure"].get("dependencies", {}),
                    directory_structure=repo_analysis["project_structure"].get("directory_structure", {}),
                    config_files=repo_analysis["project_structure"].get("config_files", []),
                    test_directories=repo_analysis["project_structure"].get("test_directories", []),
                    total_files_analyzed=repo_analysis["analysis_summary"]["total_files_analyzed"],
                    changed_files_count=repo_analysis["analysis_summary"]["changed_files_count"]
                ),
                "file_contents": repo_analysis["file_contents"],
                "changed_files": repo_analysis["changed_files"],
                "context": context,
                "analysis_time_ms": int((time.time() - start_time) * 1000)
            }
            
            self.logger.info("PR context analysis completed",
                           repo=repository,
                           pr=pr_number,
                           files_analyzed=analysis_result["project_analysis"].total_files_analyzed,
                           processing_time_ms=analysis_result["analysis_time_ms"])
            
            return analysis_result
            
        except Exception as e:
            self.logger.error("PR context analysis failed", 
                            repo=repository, 
                            pr=pr_number, 
                            error=str(e))
            raise
    
    async def _get_pr_info(self, repository: str, pr_number: int) -> Dict:
        """Get comprehensive PR information."""
        try:
            pr_data = await self.github_client.get_pull_request(repository, pr_number)
            
            # Get additional PR files info
            pr_files = await self.github_client.get_pr_files(repository, pr_number)
            
            return {
                "title": pr_data["title"],
                "description": pr_data.get("body", ""),
                "author": pr_data["user"]["login"],
                "base_branch": pr_data["base"]["ref"],
                "head_branch": pr_data["head"]["ref"],
                "state": pr_data["state"],
                "mergeable": pr_data.get("mergeable"),
                "additions": pr_data.get("additions", 0),
                "deletions": pr_data.get("deletions", 0),
                "changed_files_count": pr_data.get("changed_files", 0),
                "created_at": pr_data["created_at"],
                "updated_at": pr_data["updated_at"],
                "files": [
                    {
                        "filename": f.filename,
                        "status": f.status.value,
                        "additions": f.additions,
                        "deletions": f.deletions,
                        "changes": f.additions + f.deletions
                    }
                    for f in pr_files
                ]
            }
            
        except Exception as e:
            self.logger.error("Failed to get PR info", repo=repository, pr=pr_number, error=str(e))
            raise
    
    async def _enrich_analysis_context(
        self, 
        repository: str, 
        repo_analysis: Dict,
        pr_info: Dict
    ) -> Dict:
        """Enrich analysis with additional context."""
        context = {
            "complexity_indicators": {},
            "risk_factors": [],
            "review_focus_areas": [],
            "architectural_concerns": []
        }
        
        try:
            # Analyze complexity indicators
            context["complexity_indicators"] = self._assess_pr_complexity(
                pr_info, 
                repo_analysis
            )
            
            # Identify risk factors
            context["risk_factors"] = self._identify_risk_factors(
                pr_info, 
                repo_analysis
            )
            
            # Suggest review focus areas
            context["review_focus_areas"] = self._suggest_focus_areas(
                pr_info,
                repo_analysis,
                context["risk_factors"]
            )
            
            # Check for architectural concerns
            context["architectural_concerns"] = self._assess_architectural_impact(
                pr_info,
                repo_analysis
            )
            
        except Exception as e:
            self.logger.warning("Failed to enrich context", error=str(e))
        
        return context
    
    def _assess_pr_complexity(self, pr_info: Dict, repo_analysis: Dict) -> Dict:
        """Assess the complexity of the PR."""
        complexity = {
            "size_score": 0,  # 0-10 scale
            "file_diversity_score": 0,  # 0-10 scale
            "structural_impact_score": 0,  # 0-10 scale
            "overall_complexity": "low"  # low, medium, high, critical
        }
        
        # Size-based complexity
        total_changes = pr_info.get("additions", 0) + pr_info.get("deletions", 0)
        files_changed = pr_info.get("changed_files_count", 0)
        
        if total_changes > 1000 or files_changed > 20:
            complexity["size_score"] = 10
        elif total_changes > 500 or files_changed > 10:
            complexity["size_score"] = 7
        elif total_changes > 200 or files_changed > 5:
            complexity["size_score"] = 5
        else:
            complexity["size_score"] = 2
        
        # File diversity complexity
        file_types = set()
        config_file_changes = 0
        
        for file_info in pr_info.get("files", []):
            filename = file_info["filename"]
            file_ext = filename.split(".")[-1] if "." in filename else "no_ext"
            file_types.add(file_ext)
            
            # Check if configuration files are changed
            if any(config in filename.lower() 
                   for config in ["config", "setting", "env", "docker", "package.json", "requirements"]):
                config_file_changes += 1
        
        complexity["file_diversity_score"] = min(len(file_types), 10)
        
        # Structural impact
        if config_file_changes > 0:
            complexity["structural_impact_score"] += 3
        
        if any("test" in f["filename"].lower() for f in pr_info.get("files", [])):
            complexity["structural_impact_score"] += 1
        
        if any(f["filename"].startswith(".") for f in pr_info.get("files", [])):
            complexity["structural_impact_score"] += 2
        
        complexity["structural_impact_score"] = min(complexity["structural_impact_score"], 10)
        
        # Overall complexity assessment
        total_score = (
            complexity["size_score"] + 
            complexity["file_diversity_score"] + 
            complexity["structural_impact_score"]
        ) / 3
        
        if total_score >= 8:
            complexity["overall_complexity"] = "critical"
        elif total_score >= 6:
            complexity["overall_complexity"] = "high"
        elif total_score >= 4:
            complexity["overall_complexity"] = "medium"
        else:
            complexity["overall_complexity"] = "low"
        
        return complexity
    
    def _identify_risk_factors(self, pr_info: Dict, repo_analysis: Dict) -> List[str]:
        """Identify potential risk factors in the PR."""
        risks = []
        
        # Large PR risk
        if pr_info.get("changed_files_count", 0) > 15:
            risks.append("large_pr_size")
        
        # Security-sensitive file changes
        security_files = ["auth", "login", "password", "token", "crypto", "security"]
        for file_info in pr_info.get("files", []):
            if any(sec_keyword in file_info["filename"].lower() for sec_keyword in security_files):
                risks.append("security_sensitive_files")
                break
        
        # Database schema changes
        db_files = ["migration", "schema", "model", "database"]
        for file_info in pr_info.get("files", []):
            if any(db_keyword in file_info["filename"].lower() for db_keyword in db_files):
                risks.append("database_changes")
                break
        
        # Configuration changes
        config_files = ["config", "env", ".env", "docker", "compose", "package.json", "requirements"]
        for file_info in pr_info.get("files", []):
            if any(config in file_info["filename"].lower() for config in config_files):
                risks.append("configuration_changes")
                break
        
        # API changes
        api_keywords = ["api", "endpoint", "route", "controller", "handler"]
        for file_info in pr_info.get("files", []):
            if any(api_keyword in file_info["filename"].lower() for api_keyword in api_keywords):
                risks.append("api_changes")
                break
        
        # Dependency changes
        dep_files = ["package.json", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml"]
        for file_info in pr_info.get("files", []):
            if file_info["filename"] in dep_files:
                risks.append("dependency_changes")
                break
        
        return risks
    
    def _suggest_focus_areas(
        self, 
        pr_info: Dict, 
        repo_analysis: Dict, 
        risk_factors: List[str]
    ) -> List[str]:
        """Suggest areas to focus review on based on analysis."""
        focus_areas = ["logic", "naming"]  # Always check these
        
        # Add focus areas based on risk factors
        if "security_sensitive_files" in risk_factors:
            focus_areas.extend(["security", "critical_bugs"])
        
        if "database_changes" in risk_factors:
            focus_areas.extend(["security", "logic", "critical_bugs"])
        
        if "api_changes" in risk_factors:
            focus_areas.extend(["security", "logic", "performance"])
        
        if "configuration_changes" in risk_factors:
            focus_areas.extend(["security", "logic"])
        
        if "dependency_changes" in risk_factors:
            focus_areas.extend(["security", "critical_bugs"])
        
        # Add focus areas based on project type
        project_type = repo_analysis.get("project_structure", {}).get("project_type", "")
        if project_type in ["python", "nodejs", "java"]:
            focus_areas.append("optimization")
        
        # Always check principles for larger changes
        if pr_info.get("changed_files_count", 0) > 5:
            focus_areas.append("principles")
        
        return list(set(focus_areas))  # Remove duplicates
    
    def _assess_architectural_impact(self, pr_info: Dict, repo_analysis: Dict) -> List[str]:
        """Assess potential architectural impact of changes."""
        concerns = []
        
        # Check for changes to core architecture files
        arch_patterns = ["service", "controller", "model", "repository", "factory", "strategy"]
        for file_info in pr_info.get("files", []):
            filename_lower = file_info["filename"].lower()
            if any(pattern in filename_lower for pattern in arch_patterns):
                concerns.append("core_architecture_changes")
                break
        
        # Check for new dependencies
        if "dependency_changes" in self._identify_risk_factors(pr_info, repo_analysis):
            concerns.append("dependency_architecture_impact")
        
        # Check for interface changes
        interface_keywords = ["interface", "abstract", "base", "contract"]
        for file_info in pr_info.get("files", []):
            if any(keyword in file_info["filename"].lower() for keyword in interface_keywords):
                concerns.append("interface_changes")
                break
        
        # Check for configuration architecture changes
        if any(f["filename"].lower() in ["dockerfile", "docker-compose.yml", "kubernetes.yaml"] 
               for f in pr_info.get("files", [])):
            concerns.append("deployment_architecture_changes")
        
        return concerns