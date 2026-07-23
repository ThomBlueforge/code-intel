"""Enrichment prompts and the controlled ontology.

Classification always uses these closed vocabularies. If nothing fits, the
model must answer ``Unknown`` rather than invent a label — enforced again at
parse time by the enricher.
"""

from __future__ import annotations

from code_intel.llm.client import ChatMessage
from code_intel.models import Symbol

ARCHITECTURE_LAYERS: frozenset[str] = frozenset(
    {
        "Presentation", "UI", "Controller", "API", "Middleware", "Application",
        "Service", "Domain", "Repository", "Persistence", "Infrastructure",
        "Messaging", "Integration", "Security", "Authentication", "Authorization",
        "Configuration", "Database", "Cache", "CLI", "Background Worker",
        "Shared", "Unknown",
    }
)

BUSINESS_DOMAINS: frozenset[str] = frozenset(
    {
        "Authentication", "Authorization", "Billing", "Payments", "Orders",
        "Inventory", "Products", "Catalog", "CRM", "Customers", "Users",
        "Accounts", "Notifications", "Messaging", "Analytics", "Reporting",
        "Administration", "Search", "Scheduling", "Logging", "Monitoring",
        "Media", "Content", "Shipping", "Tax", "Finance", "Support", "AI/ML",
        "Unknown",
    }
)

RESPONSIBILITIES: frozenset[str] = frozenset(
    {
        "Validation", "Persistence", "Business Logic", "Transformation",
        "Mapping", "Serialization", "Deserialization", "Caching",
        "Authorization", "Authentication", "Routing", "Orchestration",
        "Coordination", "Event Publishing", "Event Handling", "API Client",
        "Database Access", "Configuration", "Utility", "Factory", "Builder",
        "Parsing", "Formatting", "Monitoring", "Metrics", "Testing",
    }
)

_SYSTEM_PROMPT = (
    "You are a precise static code analyst. You describe code that has already "
    "been parsed; you never invent structure. Answer ONLY with a single JSON "
    "object, no prose, no markdown fences. If you are unsure about any field, "
    "use \"Unknown\" (or an empty list) and lower the confidence score. Never "
    "guess."
)

_USER_TEMPLATE = """Classify and summarise this {language} {kind} named `{name}`.

Return JSON with exactly these keys:
- "summary": one or two sentences, plain description of what it does.
- "business_domain": array from this closed set (use ["Unknown"] if unclear): {domains}
- "architecture_layer": one value from this closed set (use "Unknown" if unclear): {layers}
- "responsibilities": array from this closed set: {responsibilities}
- "quality_metrics": object with float values in [0,1] for keys: complexity,
  maintainability, readability, coupling, cohesion, testability, risk,
  stability, reusability, technical_debt.
- "risks": array of short strings (may be empty).
- "technical_debt": array of short strings (may be empty).
- "confidence": float in [0,1] for how confident you are overall.

Source:
```{language}
{code}
```"""

# Guard against sending huge units to a local model.
_MAX_CODE_CHARS = 4000


def build_messages(symbol: Symbol) -> list[ChatMessage]:
    """Build the chat messages that ask the model to enrich ``symbol``."""
    code = symbol.code if len(symbol.code) <= _MAX_CODE_CHARS else symbol.code[:_MAX_CODE_CHARS]
    user = _USER_TEMPLATE.format(
        language=symbol.language,
        kind=symbol.type,
        name=symbol.name,
        domains=", ".join(sorted(BUSINESS_DOMAINS)),
        layers=", ".join(sorted(ARCHITECTURE_LAYERS)),
        responsibilities=", ".join(sorted(RESPONSIBILITIES)),
        code=code,
    )
    return [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user),
    ]
