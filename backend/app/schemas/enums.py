from enum import Enum


class Language(str, Enum):
    CPP = "cpp"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    JAVA = "java"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_SMELL = "code_smell"
    MAINTAINABILITY = "maintainability"
    COMPLEXITY = "complexity"
    STYLE = "style"


class FindingSource(str, Enum):
    STATIC_ANALYSIS = "static-analysis"
    COMPILER = "compiler"
    AI = "ai"
    COMPLEXITY_ANALYSIS = "complexity-analysis"
