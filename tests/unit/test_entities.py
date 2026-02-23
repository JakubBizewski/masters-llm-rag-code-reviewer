"""Tests for domain entities."""
import pytest
from datetime import datetime

from acr_system.domain.entities.entities import (
    CIToolResult,
    DiffHunk,
    ParsedCIIssue,
    PullRequest,
    ReviewComment,
)
from acr_system.domain.value_objects.value_objects import FilePath, Language, Severity


class TestDiffHunk:
    """Tests for DiffHunk entity."""
    
    def test_create_diff_hunk(self):
        """Test creating a diff hunk."""
        hunk = DiffHunk(
            file_path=FilePath("src/main.py"),
            old_start_line=10,
            old_line_count=5,
            new_start_line=10,
            new_line_count=6,
            content="@@ -10,5 +10,6 @@\n+new line",
        )
        
        assert hunk.file_path.value == "src/main.py"
        assert hunk.old_start_line == 10
        assert hunk.new_start_line == 10
    
    def test_language_from_extension(self):
        """Test getting language from file extension."""
        hunk = DiffHunk(
            file_path=FilePath("src/main.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=1,
            content="+ print('hello')",
        )
        
        assert hunk.language.name == "python"
    
    def test_is_line_in_hunk(self):
        """Test checking if line is in hunk."""
        hunk = DiffHunk(
            file_path=FilePath("src/main.py"),
            old_start_line=10,
            old_line_count=5,
            new_start_line=10,
            new_line_count=5,
            content="content",
        )
        
        assert hunk.is_line_in_hunk(10) is True
        assert hunk.is_line_in_hunk(12) is True
        assert hunk.is_line_in_hunk(14) is True
        assert hunk.is_line_in_hunk(15) is False
        assert hunk.is_line_in_hunk(9) is False


class TestReviewComment:
    """Tests for ReviewComment entity."""
    
    def test_create_review_comment(self):
        """Test creating a review comment."""
        comment = ReviewComment(
            file_path=FilePath("src/main.py"),
            line_number=42,
            severity=Severity(level=Severity.WARNING),
            message="Consider using type hints",
        )
        
        assert comment.file_path.value == "src/main.py"
        assert comment.line_number == 42
        assert comment.severity.level == "warning"
        assert comment.message == "Consider using type hints"
    
    def test_comment_with_suggestion(self):
        """Test comment with code suggestion."""
        comment = ReviewComment(
            file_path=FilePath("src/main.py"),
            line_number=42,
            severity=Severity(level=Severity.INFO),
            message="Use f-string",
            suggestion='name = f"Hello {user}"',
        )
        
        assert comment.suggestion is not None


class TestParsedCIIssue:
    """Tests for ParsedCIIssue entity."""
    
    def test_create_parsed_ci_issue(self):
        """Test creating a parsed CI issue."""
        issue = ParsedCIIssue(
            tool_name="Ruff",
            file_path="src/main.py",
            line_number=10,
            severity="error",
            issue_code="F401",
            message="Unused import",
        )
        
        assert issue.tool_name == "Ruff"
        assert issue.file_path == "src/main.py"
        assert issue.line_number == 10
    
    def test_to_review_comment(self):
        """Test converting CI issue to review comment."""
        issue = ParsedCIIssue(
            tool_name="Ruff",
            file_path="src/main.py",
            line_number=10,
            severity="error",
            issue_code="F401",
            message="Unused import: typing.Optional",
        )
        
        comment = issue.to_review_comment()
        
        assert isinstance(comment, ReviewComment)
        assert comment.file_path.value == "src/main.py"
        assert comment.line_number == 10
        assert comment.severity.level == "error"
        assert "Ruff" in comment.message
        assert "F401" in comment.message


class TestPullRequest:
    """Tests for PullRequest entity."""
    
    def test_create_pull_request(self):
        """Test creating a pull request."""
        pr = PullRequest(
            pr_number=123,
            repository="owner/repo",
            title="Add new feature",
            description="This PR adds a new feature",
            author="john_doe",
            source_branch="feature/new-feature",
            target_branch="main",
        )
        
        assert pr.pr_number == 123
        assert pr.repository == "owner/repo"
        assert pr.title == "Add new feature"
    
    def test_add_diff_hunk(self):
        """Test adding diff hunk to PR."""
        pr = PullRequest(
            pr_number=123,
            repository="owner/repo",
            title="Test PR",
            description="",
            author="author",
            source_branch="feature",
            target_branch="main",
        )
        
        hunk = DiffHunk(
            file_path=FilePath("src/main.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=1,
            content="+ new line",
        )
        
        pr.add_diff_hunk(hunk)
        
        assert len(pr.diff_hunks) == 1
        assert pr.diff_hunks[0] == hunk
    
    def test_changed_files(self):
        """Test getting changed files."""
        pr = PullRequest(
            pr_number=123,
            repository="owner/repo",
            title="Test PR",
            description="",
            author="author",
            source_branch="feature",
            target_branch="main",
        )
        
        pr.add_diff_hunk(DiffHunk(
            file_path=FilePath("src/main.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=1,
            content="content",
        ))
        
        pr.add_diff_hunk(DiffHunk(
            file_path=FilePath("src/utils.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=1,
            content="content",
        ))
        
        changed_files = pr.changed_files
        assert len(changed_files) == 2
        assert "src/main.py" in changed_files
        assert "src/utils.py" in changed_files
    
    def test_languages(self):
        """Test getting languages in PR."""
        pr = PullRequest(
            pr_number=123,
            repository="owner/repo",
            title="Test PR",
            description="",
            author="author",
            source_branch="feature",
            target_branch="main",
        )
        
        pr.add_diff_hunk(DiffHunk(
            file_path=FilePath("src/main.py"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=1,
            content="content",
        ))
        
        pr.add_diff_hunk(DiffHunk(
            file_path=FilePath("src/app.js"),
            old_start_line=1,
            old_line_count=1,
            new_start_line=1,
            new_line_count=1,
            content="content",
        ))
        
        languages = pr.languages
        assert len(languages) == 2
        lang_names = {lang.name for lang in languages}
        assert "python" in lang_names
        assert "javascript" in lang_names
