"""MCP (Model Context Protocol) tools for repository analysis."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set

import git
import structlog
from asyncio_throttle import Throttler

from .config import settings

logger = structlog.get_logger(__name__)


class MCPRepositoryAnalyzer:
    """Repository analyzer using MCP tools for deep code understanding."""
    
    def __init__(self):
        self.logger = logger.bind(component="MCPRepositoryAnalyzer")
        self.throttler = Throttler(rate_limit=10, period=1)  # 10 operations per second
        
        # File extensions to analyze
        self.code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.go', '.rs', '.rb', '.php', '.cs', '.swift', '.kt', '.scala',
            '.sh', '.bash', '.ps1', '.sql', '.yaml', '.yml', '.json', '.xml',
            '.toml', '.ini', '.cfg', '.conf', '.dockerfile', '.tf', '.hcl'
        }
        
        # Configuration files that indicate project structure
        self.config_files = {
            'package.json', 'requirements.txt', 'Pipfile', 'pyproject.toml',
            'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle', 'composer.json',
            'Gemfile', 'mix.exs', 'stack.yaml', 'project.clj', 'deps.edn',
            'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
            'kubernetes.yaml', 'k8s.yaml', '.gitignore', '.dockerignore',
            'Makefile', 'CMakeLists.txt', 'meson.build', 'BUILD', 'WORKSPACE'
        }
    
    async def analyze_repository(
        self, 
        repository: str, 
        head_sha: str, 
        base_sha: str,
        max_files: int = 100
    ) -> Dict:
        """Analyze repository structure and get relevant file contents."""
        self.logger.info("Starting repository analysis", 
                         repo=repository, 
                         head_sha=head_sha[:8], 
                         base_sha=base_sha[:8])
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                repo_path = Path(temp_dir) / "repo"
                
                # Clone repository
                await self._clone_repository(repository, repo_path, head_sha)
                
                # Get changed files
                changed_files = await self._get_changed_files(repo_path, base_sha, head_sha)
                
                # Analyze project structure
                project_structure = await self._analyze_project_structure(repo_path)
                
                # Get file contents for analysis
                file_contents = await self._get_relevant_file_contents(
                    repo_path, 
                    changed_files, 
                    project_structure,
                    max_files
                )
                
                return {
                    "project_structure": project_structure,
                    "file_contents": file_contents,
                    "changed_files": changed_files,
                    "analysis_summary": {
                        "total_files_analyzed": len(file_contents),
                        "changed_files_count": len(changed_files),
                        "project_type": project_structure.get("project_type", "unknown"),
                        "main_language": project_structure.get("main_language", "unknown")
                    }
                }
                
        except Exception as e:
            self.logger.error("Repository analysis failed", error=str(e))
            raise
    
    async def _clone_repository(self, repository: str, repo_path: Path, sha: str):
        """Clone repository to local path."""
        self.logger.info("Cloning repository", repo=repository, sha=sha[:8])
        
        # Construct clone URL with token
        if repository.startswith("http"):
            clone_url = repository
        else:
            # Assume it's owner/repo format
            clone_url = f"https://github.com/{repository}.git"
        
        # Add GitHub token if available
        if settings.github_token:
            # Insert token into URL
            clone_url = clone_url.replace("https://", f"https://{settings.github_token}@")
        
        # Clone with better depth strategy for PR analysis
        try:
            # Try shallow clone first
            repo = git.Repo.clone_from(
                clone_url,
                repo_path,
                depth=50,  # Get some history for better diff analysis
                single_branch=False,  # We need both base and head branches
            )
            
            # Checkout specific SHA
            try:
                repo.git.fetch("origin", sha)
                repo.git.checkout(sha)
                self.logger.info("Successfully checked out SHA", sha=sha[:8])
            except Exception as e:
                self.logger.warning("Could not checkout specific SHA, trying to fetch more", error=str(e))
                # Try fetching more history
                repo.git.fetch("--unshallow")
                repo.git.checkout(sha)
                
        except Exception as e:
            self.logger.error("Failed to clone repository", error=str(e))
            # Fallback: clone without depth limit
            repo = git.Repo.clone_from(clone_url, repo_path)
            repo.git.checkout(sha)
    
    async def _get_changed_files(self, repo_path: Path, base_sha: str, head_sha: str) -> List[str]:
        """Get list of changed files between commits."""
        try:
            repo = git.Repo(repo_path)
            
            # Try to get base commit
            try:
                repo.git.fetch("origin", base_sha)
                base_commit = repo.commit(base_sha)
                head_commit = repo.commit(head_sha)
                
                # Get diff between commits
                diff = base_commit.diff(head_commit)
                changed_files = []
                
                for item in diff:
                    if item.b_path:  # File exists in head
                        changed_files.append(item.b_path)
                    elif item.a_path:  # File deleted
                        changed_files.append(item.a_path)
                
                return changed_files
                
            except Exception:
                # Fallback: get all files if we can't do proper diff
                self.logger.warning("Could not perform git diff, analyzing all files")
                return []
                
        except Exception as e:
            self.logger.error("Failed to get changed files", error=str(e))
            return []
    
    async def _analyze_project_structure(self, repo_path: Path) -> Dict:
        """Analyze project structure and technology stack."""
        self.logger.info("Analyzing project structure", path=str(repo_path))
        
        structure = {
            "project_type": "unknown",
            "main_language": "unknown",
            "frameworks": [],
            "dependencies": {},
            "directory_structure": {},
            "config_files": [],
            "test_directories": [],
            "documentation_files": [],
            "build_files": [],
            "ci_files": []
        }
        
        try:
            # Scan directory structure
            structure["directory_structure"] = await self._scan_directory_structure(repo_path)
            
            # Detect project type and language
            await self._detect_project_type(repo_path, structure)
            
            # Find important files
            await self._categorize_files(repo_path, structure)
            
            # Analyze dependencies
            await self._analyze_dependencies(repo_path, structure)
            
            return structure
            
        except Exception as e:
            self.logger.error("Project structure analysis failed", error=str(e))
            return structure
    
    async def _scan_directory_structure(self, repo_path: Path, max_depth: int = 3) -> Dict:
        """Scan directory structure up to max_depth."""
        def scan_recursive(path: Path, current_depth: int = 0) -> Dict:
            if current_depth >= max_depth:
                return {}
            
            structure = {}
            try:
                for item in path.iterdir():
                    if item.name.startswith('.'):
                        continue
                    
                    if item.is_dir():
                        structure[item.name] = scan_recursive(item, current_depth + 1)
                    else:
                        # Count files by extension
                        ext = item.suffix.lower()
                        if ext not in structure:
                            structure[ext] = 0
                        structure[ext] += 1
                        
            except PermissionError:
                pass
            
            return structure
        
        return scan_recursive(repo_path)
    
    async def _detect_project_type(self, repo_path: Path, structure: Dict):
        """Detect project type and main language."""
        # Check for specific configuration files
        if (repo_path / "package.json").exists():
            structure["project_type"] = "nodejs"
            structure["main_language"] = "javascript"
        elif (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
            structure["project_type"] = "python"
            structure["main_language"] = "python"
        elif (repo_path / "Cargo.toml").exists():
            structure["project_type"] = "rust"
            structure["main_language"] = "rust"
        elif (repo_path / "go.mod").exists():
            structure["project_type"] = "go"
            structure["main_language"] = "go"
        elif (repo_path / "pom.xml").exists() or (repo_path / "build.gradle").exists():
            structure["project_type"] = "java"
            structure["main_language"] = "java"
        elif (repo_path / "Dockerfile").exists():
            structure["project_type"] = "containerized"
        
        # Detect frameworks
        if structure["project_type"] == "nodejs":
            await self._detect_js_frameworks(repo_path, structure)
        elif structure["project_type"] == "python":
            await self._detect_python_frameworks(repo_path, structure)
    
    async def _detect_js_frameworks(self, repo_path: Path, structure: Dict):
        """Detect JavaScript/Node.js frameworks."""
        package_json_path = repo_path / "package.json"
        if package_json_path.exists():
            try:
                import json
                with open(package_json_path) as f:
                    package_data = json.load(f)
                
                deps = {**package_data.get("dependencies", {}), 
                       **package_data.get("devDependencies", {})}
                
                frameworks = []
                if "react" in deps:
                    frameworks.append("react")
                if "vue" in deps:
                    frameworks.append("vue")
                if "angular" in deps or "@angular/core" in deps:
                    frameworks.append("angular")
                if "express" in deps:
                    frameworks.append("express")
                if "next" in deps:
                    frameworks.append("nextjs")
                if "nuxt" in deps:
                    frameworks.append("nuxtjs")
                if "fastify" in deps:
                    frameworks.append("fastify")
                
                structure["frameworks"] = frameworks
                structure["dependencies"] = deps
                
            except Exception as e:
                self.logger.warning("Failed to parse package.json", error=str(e))
    
    async def _detect_python_frameworks(self, repo_path: Path, structure: Dict):
        """Detect Python frameworks."""
        frameworks = []
        
        # Check for Django
        if (repo_path / "manage.py").exists():
            frameworks.append("django")
        
        # Check for Flask (look for app.py or common patterns)
        for py_file in repo_path.glob("**/*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "from flask import" in content or "import flask" in content:
                    frameworks.append("flask")
                    break
                if "from fastapi import" in content or "import fastapi" in content:
                    frameworks.append("fastapi")
                    break
            except Exception:
                continue
        
        structure["frameworks"] = list(set(frameworks))
    
    async def _categorize_files(self, repo_path: Path, structure: Dict):
        """Categorize files by type."""
        config_files = []
        test_dirs = []
        docs = []
        build_files = []
        ci_files = []
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(repo_path)
                
                # Config files
                if file_path.name.lower() in self.config_files:
                    config_files.append(str(rel_path))
                
                # Documentation
                if file_path.suffix.lower() in {'.md', '.rst', '.txt'} and \
                   any(doc_keyword in file_path.name.lower() 
                       for doc_keyword in ['readme', 'doc', 'changelog', 'license']):
                    docs.append(str(rel_path))
                
                # Build files
                if file_path.name.lower() in {'makefile', 'cmakelists.txt', 'build.sh'}:
                    build_files.append(str(rel_path))
                
                # CI files
                if '.github' in str(rel_path) or '.gitlab-ci' in str(rel_path):
                    ci_files.append(str(rel_path))
            
            elif file_path.is_dir():
                dir_name = file_path.name.lower()
                # Test directories
                if any(test_keyword in dir_name 
                       for test_keyword in ['test', 'tests', 'spec', '__test__']):
                    test_dirs.append(str(file_path.relative_to(repo_path)))
        
        structure["config_files"] = config_files
        structure["test_directories"] = test_dirs
        structure["documentation_files"] = docs
        structure["build_files"] = build_files
        structure["ci_files"] = ci_files
    
    async def _analyze_dependencies(self, repo_path: Path, structure: Dict):
        """Analyze project dependencies."""
        try:
            # Python dependencies
            if (repo_path / "requirements.txt").exists():
                with open(repo_path / "requirements.txt") as f:
                    deps = [line.strip().split("==")[0].split(">=")[0].split("<=")[0] 
                           for line in f if line.strip() and not line.startswith("#")]
                    structure["dependencies"]["python"] = deps
            
            # Already handled in detect_js_frameworks for Node.js
            
        except Exception as e:
            self.logger.warning("Failed to analyze dependencies", error=str(e))
    
    async def _get_relevant_file_contents(
        self, 
        repo_path: Path, 
        changed_files: List[str], 
        project_structure: Dict,
        max_files: int
    ) -> Dict[str, str]:
        """Get file contents for relevant files with smart prioritization."""
        self.logger.info("Getting file contents", 
                         changed_files_count=len(changed_files), 
                         max_files=max_files)
        
        file_contents = {}
        files_to_analyze = []
        
        # Priority 1: Always include changed files (highest priority)
        for file_path in changed_files:
            full_path = repo_path / file_path
            if full_path.exists() and self._should_analyze_file(full_path):
                files_to_analyze.append((file_path, "changed", 100))
        
        # Priority 2: Include critical config files
        critical_configs = ["package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"]
        for config_file in project_structure.get("config_files", []):
            if len(files_to_analyze) >= max_files:
                break
            file_name = Path(config_file).name
            if file_name in critical_configs:
                files_to_analyze.append((config_file, "config", 90))
        
        # Priority 3: Include files in same directories as changed files (for context)
        context_files_added = 0
        for changed_file in changed_files[:5]:  # Limit context search
            if context_files_added >= 10:  # Max 10 context files
                break
                
            changed_path = Path(changed_file)
            parent_dir = repo_path / changed_path.parent
            
            if parent_dir.exists() and parent_dir.is_dir():
                for sibling in parent_dir.iterdir():
                    if context_files_added >= 10 or len(files_to_analyze) >= max_files:
                        break
                    
                    if sibling.is_file() and self._should_analyze_file(sibling):
                        rel_path = str(sibling.relative_to(repo_path))
                        # Don't duplicate changed files
                        if rel_path not in [f[0] for f in files_to_analyze]:
                            files_to_analyze.append((rel_path, "context", 50))
                            context_files_added += 1
        
        # Priority 4: Include main entry points (lower priority)
        entry_points = ["main.py", "index.js", "app.py", "server.py", "main.go"]
        for entry_point in entry_points:
            if len(files_to_analyze) >= max_files:
                break
            entry_path = repo_path / entry_point
            if entry_path.exists() and str(entry_point) not in [f[0] for f in files_to_analyze]:
                files_to_analyze.append((entry_point, "entry", 30))
        
        # Sort by priority and take top files
        files_to_analyze.sort(key=lambda x: x[2], reverse=True)
        priority_files = files_to_analyze[:max_files]
        
        # Read file contents with throttling
        for file_path, file_type, priority in priority_files:
            async with self.throttler:
                try:
                    full_path = repo_path / file_path
                    if full_path.exists() and full_path.stat().st_size < 500_000:  # 500KB limit per file
                        content = full_path.read_text(encoding="utf-8", errors="ignore")
                        # Truncate very long files
                        if len(content) > 10000:  # 10K characters max
                            content = content[:10000] + "\n... [file truncated for analysis]"
                        file_contents[file_path] = content
                        self.logger.debug("Loaded file", path=file_path, type=file_type, priority=priority)
                except Exception as e:
                    self.logger.warning("Failed to read file", file=file_path, error=str(e))
        
        self.logger.info("File contents loaded", 
                        count=len(file_contents),
                        changed_files=len([f for f in priority_files if f[1] == "changed"]),
                        config_files=len([f for f in priority_files if f[1] == "config"]),
                        context_files=len([f for f in priority_files if f[1] == "context"]))
        return file_contents
    
    def _should_analyze_file(self, file_path: Path) -> bool:
        """Check if file should be analyzed."""
        # Size limit
        try:
            if file_path.stat().st_size > 1_000_000:  # 1MB
                return False
        except Exception:
            return False
        
        # Extension check
        if file_path.suffix.lower() not in self.code_extensions:
            # Also include files without extensions that might be important
            if file_path.suffix == "" and file_path.name.lower() not in self.config_files:
                return False
        
        # Skip binary files
        if file_path.suffix.lower() in {'.exe', '.bin', '.so', '.dylib', '.dll', 
                                       '.png', '.jpg', '.jpeg', '.gif', '.svg',
                                       '.pdf', '.zip', '.tar', '.gz'}:
            return False
        
        return True