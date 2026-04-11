from acr_system.domain.entities.entities import ReviewComment
from acr_system.domain.value_objects.value_objects import FilePath, Severity
from acr_system.infrastructure.config.project_config import ProjectConfig, PublishConfig
from acr_system.infrastructure.config.yaml_config_loader import YAMLConfigLoader


def _comment(message: str, severity: str, rule_name: str | None = None) -> ReviewComment:
    return ReviewComment(
        file_path=FilePath("acr_system/domain/services/services.py"),
        line_number=41,
        severity=Severity(level=severity),
        message=message,
        rule_name=rule_name,
    )


def test_publish_filter_respects_min_severity() -> None:
    cfg = ProjectConfig(publish_config=PublishConfig(min_severity=Severity.WARNING))

    comments = [
        _comment("Informational only", Severity.INFO),
        _comment("Action needed", Severity.WARNING),
        _comment("Must fix", Severity.ERROR),
    ]

    filtered = cfg.filter_comments_for_publication(comments)

    assert len(filtered) == 2
    assert all(c.severity.level in {Severity.WARNING, Severity.ERROR} for c in filtered)


def test_publish_filter_excludes_by_patterns_and_rule_name() -> None:
    cfg = ProjectConfig(
        publish_config=PublishConfig(
            min_severity=Severity.INFO,
            exclude_rule_names=["style_hint"],
            exclude_message_patterns=[r"more descriptive", r"documentation|api contracts"],
        )
    )

    comments = [
        _comment(
            "The new method name is more descriptive than the old one.",
            Severity.INFO,
            rule_name="llm_review",
        ),
        _comment(
            "Ensure this change is reflected in documentation or API contracts.",
            Severity.INFO,
            rule_name="llm_review",
        ),
        _comment(
            "Unused variable causes dead code path.",
            Severity.WARNING,
            rule_name="style_hint",
        ),
        _comment(
            "Division by zero is guaranteed at runtime.",
            Severity.ERROR,
            rule_name="llm_review",
        ),
    ]

    filtered = cfg.filter_comments_for_publication(comments)

    assert len(filtered) == 1
    assert filtered[0].message == "Division by zero is guaranteed at runtime."


def test_yaml_loader_parses_publish_policy() -> None:
    data = {
        "publish": {
            "min_severity": "warning",
            "exclude_rule_names": ["style_hint"],
            "exclude_message_patterns": ["documentation"],
            "exclude_positive_feedback": True,
        }
    }

    loader = YAMLConfigLoader(vcs_repository=None)  # type: ignore[arg-type]
    cfg = loader._parse_config(data)  # pylint: disable=protected-access

    assert cfg.publish_config.min_severity == "warning"
    assert cfg.publish_config.exclude_rule_names == ["style_hint"]
    assert cfg.publish_config.exclude_message_patterns == ["documentation"]
    assert cfg.publish_config.exclude_positive_feedback is True
