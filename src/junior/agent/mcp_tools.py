"""MCP tools for ReAct agent that extend existing RepositoryAnalyzer capabilities."""

import json
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

import structlog
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .tools import RepositoryAnalyzer
from ..config import settings


logger = structlog.get_logger(__name__)


class AnalyzeFileInput(BaseModel):
    """Input for analyze_file tool."""
    file_path: str = Field(description="Relative path to the file to analyze")
    focus_area: Optional[str] = Field(
        default=None, 
        description="Specific area to focus on: 'security', 'logic', 'performance', 'imports', 'functions'"
    )


class SearchCodeInput(BaseModel):
    """Input for search_code tool."""
    pattern: str = Field(description="Code pattern, function name, or keyword to search for")
    file_extension: Optional[str] = Field(
        default=None, 
        description="File extension to limit search (e.g., '.py', '.js')"
    )


class GetProjectContextInput(BaseModel):
    """Input for get_project_context tool."""
    context_type: str = Field(
        description="Type of context: 'dependencies', 'structure', 'config', 'tests', 'frameworks'"
    )


class AnalyzeRelatedFilesInput(BaseModel):
    """Input for analyze_related_files tool."""
    base_file: str = Field(description="Base file to find related files for")
    relationship_type: str = Field(
        description="Relationship type: 'imports', 'same_directory', 'tests', 'config'"
    )


class GetFileContentInput(BaseModel):
    """Input for get_file_content tool."""
    file_path: str = Field(description="Relative path to the file")
    max_lines: Optional[int] = Field(
        default=100, 
        description="Maximum number of lines to return (default 100)"
    )


class AnalyzeFileTool(BaseTool):
    """Analyze specific files with different focus areas."""
    
    name: str = "analyze_file"
    description: str = """
    Analyze a specific file in the repository with optional focus area.
    Focus areas: 'security' (auth, secrets, SQL), 'logic' (conditions, loops), 
    'performance' (async, database, caching), 'imports' (dependencies), 'functions' (definitions).
    """
    args_schema: type[BaseModel] = AnalyzeFileInput
    
    def __init__(self, file_contents: Dict[str, str]):
        super().__init__()
        self.file_contents = file_contents
        self.logger = logger.bind(component="AnalyzeFileTool")
    
    def _run(self, file_path: str, focus_area: Optional[str] = None) -> str:
        """Analyze a specific file."""
        try:
            if file_path not in self.file_contents:
                return f"File '{file_path}' not available in current analysis context."
            
            content = self.file_contents[file_path]
            lines = content.split('\n')
            
            analysis = {
                "file_path": file_path,
                "total_lines": len(lines),
                "focus_area": focus_area or "general"
            }
            
            if focus_area == "security":
                patterns = ["password", "secret", "token", "api_key", "auth", "sql", "query", "eval", "exec"]
                matches = []
                for i, line in enumerate(lines):
                    if any(p in line.lower() for p in patterns):
                        matches.append(f"Line {i+1}: {line.strip()}")
                analysis["security_concerns"] = matches[:10]
                
            elif focus_area == "logic":
                patterns = ["if", "else", "elif", "while", "for", "try", "except", "switch", "case"]
                matches = []
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if any(stripped.startswith(p) for p in patterns):
                        matches.append(f"Line {i+1}: {stripped}")
                analysis["logic_structures"] = matches[:15]
                
            elif focus_area == "performance":
                patterns = ["async", "await", "promise", "database", "db", "cache", "query", "request"]
                matches = []
                for i, line in enumerate(lines):
                    if any(p in line.lower() for p in patterns):
                        matches.append(f"Line {i+1}: {line.strip()}")
                analysis["performance_related"] = matches[:10]
                
            elif focus_area == "imports":
                imports = []
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if (stripped.startswith(('import ', 'from ')) or 
                        'require(' in stripped or 'import(' in stripped):
                        imports.append(f"Line {i+1}: {stripped}")
                analysis["imports"] = imports[:20]
                
            elif focus_area == "functions":
                functions = []
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if (stripped.startswith(('def ', 'function ', 'class ', 'async def')) or
                        '=>' in stripped):
                        functions.append(f"Line {i+1}: {stripped}")
                analysis["function_definitions"] = functions[:20]
                
            else:  # general analysis
                important = []
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if (stripped.startswith(('def ', 'class ', 'function ', 'import ', 'from ')) or
                        'export' in stripped or '=>' in stripped):
                        important.append(f"Line {i+1}: {stripped}")
                analysis["key_definitions"] = important[:25]
            
            return json.dumps(analysis, indent=2)
            
        except Exception as e:
            self.logger.error("Failed to analyze file", file_path=file_path, error=str(e))
            return f"Error analyzing file {file_path}: {str(e)}"


class SearchCodeTool(BaseTool):
    """Search for code patterns across files."""
    
    name: str = "search_code"
    description: str = """
    Search for specific code patterns, function names, or keywords across all files.
    Returns matching lines with context and file locations.
    """
    args_schema: type[BaseModel] = SearchCodeInput
    
    def __init__(self, file_contents: Dict[str, str]):
        super().__init__()
        self.file_contents = file_contents
        self.logger = logger.bind(component="SearchCodeTool")
    
    def _run(self, pattern: str, file_extension: Optional[str] = None) -> str:
        """Search for code patterns."""
        try:
            results = []
            
            for file_path, content in self.file_contents.items():
                # Filter by extension if specified
                if file_extension and not file_path.endswith(file_extension):
                    continue
                
                lines = content.split('\n')
                matches = []
                
                for i, line in enumerate(lines):
                    if pattern.lower() in line.lower():
                        # Add context lines
                        context_start = max(0, i-1)
                        context_end = min(len(lines), i+2)
                        context_lines = lines[context_start:context_end]
                        
                        matches.append({
                            "line_number": i + 1,
                            "line": line.strip(),
                            "context": context_lines
                        })
                
                if matches:
                    results.append({
                        "file": file_path,
                        "matches": matches[:5]  # Limit matches per file
                    })
            
            if not results:
                return f"No matches found for pattern '{pattern}'"
            
            # Limit total results to prevent token overflow
            return json.dumps(results[:8], indent=2)
            
        except Exception as e:
            self.logger.error("Failed to search code", pattern=pattern, error=str(e))
            return f"Error searching for '{pattern}': {str(e)}"


class GetProjectContextTool(BaseTool):
    """Get project context information."""
    
    name: str = "get_project_context"
    description: str = """
    Get project context like dependencies, structure, configuration, tests, or frameworks.
    Helps understand the broader project context for better review analysis.
    """
    args_schema: type[BaseModel] = GetProjectContextInput
    
    def __init__(self, project_structure: Dict[str, Any]):
        super().__init__()
        self.project_structure = project_structure
        self.logger = logger.bind(component="GetProjectContextTool")
    
    def _run(self, context_type: str) -> str:
        """Get specific project context."""
        try:
            if context_type == "dependencies":
                return json.dumps({
                    "dependencies": self.project_structure.get("dependencies", {}),
                    "frameworks": self.project_structure.get("frameworks", []),
                    "project_type": self.project_structure.get("project_type", "unknown"),
                    "main_language": self.project_structure.get("main_language", "unknown")
                }, indent=2)
                
            elif context_type == "structure":
                return json.dumps({
                    "directory_structure": self.project_structure.get("directory_structure", {}),
                    "config_files": self.project_structure.get("config_files", []),
                    "test_directories": self.project_structure.get("test_directories", [])
                }, indent=2)
                
            elif context_type == "config":
                return json.dumps({
                    "config_files": self.project_structure.get("config_files", []),
                    "build_files": self.project_structure.get("build_files", []),
                    "ci_files": self.project_structure.get("ci_files", [])
                }, indent=2)
                
            elif context_type == "tests":
                return json.dumps({
                    "test_directories": self.project_structure.get("test_directories", []),
                    "documentation_files": self.project_structure.get("documentation_files", [])
                }, indent=2)
                
            elif context_type == "frameworks":
                return json.dumps({
                    "frameworks": self.project_structure.get("frameworks", []),
                    "project_type": self.project_structure.get("project_type", "unknown"),
                    "main_language": self.project_structure.get("main_language", "unknown")
                }, indent=2)
            
            else:
                return f"Unknown context type '{context_type}'. Available: dependencies, structure, config, tests, frameworks"
                
        except Exception as e:
            self.logger.error("Failed to get project context", context_type=context_type, error=str(e))
            return f"Error getting project context '{context_type}': {str(e)}"


class AnalyzeRelatedFilesTool(BaseTool):
    """Find and analyze files related to a given file."""
    
    name: str = "analyze_related_files"
    description: str = """
    Find files related to a given file by imports, directory location, tests, or configuration.
    Helps understand change impact and dependencies.
    """
    args_schema: type[BaseModel] = AnalyzeRelatedFilesInput
    
    def __init__(self, file_contents: Dict[str, str]):
        super().__init__()
        self.file_contents = file_contents
        self.logger = logger.bind(component="AnalyzeRelatedFilesTool")
    
    def _run(self, base_file: str, relationship_type: str) -> str:
        """Find related files."""
        try:
            if relationship_type == "imports":
                if base_file not in self.file_contents:
                    return f"Base file '{base_file}' not available"
                
                base_content = self.file_contents[base_file]
                base_name = Path(base_file).stem
                
                # Find imports in base file
                imports_in_base = []
                for line in base_content.split('\n'):
                    if 'import' in line or 'require(' in line:
                        imports_in_base.append(line.strip())
                
                # Find files that import base file
                importers = []
                for file_path, content in self.file_contents.items():
                    if file_path != base_file and (base_name in content or base_file in content):
                        importers.append(file_path)
                
                return json.dumps({
                    "imports_in_base": imports_in_base[:15],
                    "files_importing_base": importers[:10]
                }, indent=2)
                
            elif relationship_type == "same_directory":
                base_dir = str(Path(base_file).parent)
                same_dir = [f for f in self.file_contents.keys() 
                           if str(Path(f).parent) == base_dir and f != base_file]
                return json.dumps({"same_directory_files": same_dir}, indent=2)
                
            elif relationship_type == "tests":
                base_name = Path(base_file).stem
                test_files = [f for f in self.file_contents.keys()
                             if ("test" in f.lower() or "spec" in f.lower()) and base_name in f]
                return json.dumps({"test_files": test_files}, indent=2)
                
            elif relationship_type == "config":
                config_extensions = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf'}
                config_files = [f for f in self.file_contents.keys()
                               if Path(f).suffix.lower() in config_extensions]
                return json.dumps({"config_files": config_files}, indent=2)
            
            else:
                return f"Unknown relationship type '{relationship_type}'. Available: imports, same_directory, tests, config"
                
        except Exception as e:
            self.logger.error("Failed to analyze related files", base_file=base_file, error=str(e))
            return f"Error analyzing related files for '{base_file}': {str(e)}"


class GetFileContentTool(BaseTool):
    """Get content of a specific file."""
    
    name: str = "get_file_content"
    description: str = """
    Get the content of a specific file, optionally limiting the number of lines.
    Use this to examine files that weren't included in the initial analysis.
    """
    args_schema: type[BaseModel] = GetFileContentInput
    
    def __init__(self, file_contents: Dict[str, str]):
        super().__init__()
        self.file_contents = file_contents
        self.logger = logger.bind(component="GetFileContentTool")
    
    def _run(self, file_path: str, max_lines: Optional[int] = 100) -> str:
        """Get file content."""
        try:
            if file_path not in self.file_contents:
                return f"File '{file_path}' not available in current analysis context."
            
            content = self.file_contents[file_path]
            lines = content.split('\n')
            
            if max_lines and len(lines) > max_lines:
                limited_content = '\n'.join(lines[:max_lines])
                return f"{limited_content}\n\n... [Content truncated at {max_lines} lines. Total lines: {len(lines)}]"
            
            return content
            
        except Exception as e:
            self.logger.error("Failed to get file content", file_path=file_path, error=str(e))
            return f"Error getting content for '{file_path}': {str(e)}"


def create_mcp_tools(
    file_contents: Dict[str, str], 
    project_structure: Dict[str, Any]
) -> List[BaseTool]:
    """
    Create MCP tools for ReAct agent using existing repository analysis data.
    
    This extends the capabilities of RepositoryAnalyzer by providing interactive
    tools that the LLM can use during review analysis.
    """
    return [
        AnalyzeFileTool(file_contents),
        SearchCodeTool(file_contents),
        GetProjectContextTool(project_structure),
        AnalyzeRelatedFilesTool(file_contents),
        GetFileContentTool(file_contents),
    ]


def get_tool_descriptions() -> str:
    """Get human-readable descriptions of available tools."""
    return """
Available MCP Tools for Code Review:

1. analyze_file(file_path, focus_area) - Analyze specific files with focus areas:
   - security: Find auth, secrets, SQL injection risks
   - logic: Find conditionals, loops, control flow
   - performance: Find async, database, caching code
   - imports: Find dependencies and imports
   - functions: Find function/class definitions

2. search_code(pattern, file_extension) - Search for patterns across files:
   - Find function calls, variable usage, specific keywords
   - Filter by file extension (.py, .js, etc.)

3. get_project_context(context_type) - Get project information:
   - dependencies: Project dependencies and frameworks
   - structure: Directory structure and organization
   - config: Configuration and build files
   - tests: Test directories and files
   - frameworks: Detected frameworks and tech stack

4. analyze_related_files(base_file, relationship_type) - Find related files:
   - imports: What files import/are imported by base file
   - same_directory: Files in same directory
   - tests: Test files for the base file
   - config: Configuration files that may affect base file

5. get_file_content(file_path, max_lines) - Get file content:
   - View files not included in initial analysis
   - Limit output with max_lines parameter

Use these tools to gather additional context during your review analysis.
"""