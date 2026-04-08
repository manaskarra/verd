"""Business decision templates.

Each template defines the fields a user fills in and a function
that assembles structured content + claim for run_debate().
"""

TEMPLATES = {
    "location": {
        "id": "location",
        "label": "Should I open / expand to this location?",
        "description": "Evaluate whether a specific location is viable for your business.",
        "icon": "map-pin",
        "fields": [
            {"name": "decision", "label": "What are you deciding?", "type": "text",
             "placeholder": "Open a second cafe in JBR, Dubai"},
            {"name": "location", "label": "Location", "type": "text",
             "placeholder": "JBR Walk, Dubai Marina area"},
            {"name": "budget", "label": "Budget", "type": "text",
             "placeholder": "AED 250,000"},
            {"name": "competitors", "label": "Known competitors nearby", "type": "textarea",
             "placeholder": "3 specialty coffee shops within 200m, 1 major chain"},
            {"name": "target_customer", "label": "Target customer", "type": "text",
             "placeholder": "Tourists and young professionals aged 25-40"},
        ],
    },
    "pricing": {
        "id": "pricing",
        "label": "Should I change my pricing?",
        "description": "Model churn risk, revenue impact, and competitive positioning.",
        "icon": "tag",
        "fields": [
            {"name": "decision", "label": "What are you deciding?", "type": "text",
             "placeholder": "Raise subscription price from $29 to $49/month"},
            {"name": "current_price", "label": "Current price", "type": "text",
             "placeholder": "$29/month"},
            {"name": "proposed_price", "label": "Proposed price", "type": "text",
             "placeholder": "$49/month"},
            {"name": "competitor_pricing", "label": "Competitor pricing", "type": "textarea",
             "placeholder": "Competitor A: $39/mo, Competitor B: $25/mo freemium"},
            {"name": "customer_base", "label": "Current customer base", "type": "text",
             "placeholder": "1,200 active subscribers, 5% monthly churn"},
        ],
    },
    "launch": {
        "id": "launch",
        "label": "Should I launch this product / service?",
        "description": "Stress-test a product launch before committing resources.",
        "icon": "rocket",
        "fields": [
            {"name": "decision", "label": "What are you launching?", "type": "text",
             "placeholder": "Premium co-working space with specialty coffee"},
            {"name": "target_market", "label": "Target market", "type": "text",
             "placeholder": "Freelancers and remote workers in Barcelona"},
            {"name": "budget", "label": "Launch budget", "type": "text",
             "placeholder": "€120,000"},
            {"name": "timeline", "label": "Timeline", "type": "text",
             "placeholder": "3 months to open, break-even in 8 months"},
            {"name": "differentiator", "label": "What makes this different?", "type": "textarea",
             "placeholder": "Only space combining co-working + specialty coffee + events"},
        ],
    },
    "hire": {
        "id": "hire",
        "label": "Should I make this hire?",
        "description": "Evaluate whether a key hire is the right move right now.",
        "icon": "user-plus",
        "fields": [
            {"name": "decision", "label": "What role are you hiring?", "type": "text",
             "placeholder": "Full-time Sales Director at AED 30K/month"},
            {"name": "current_revenue", "label": "Current monthly revenue", "type": "text",
             "placeholder": "AED 85,000/month"},
            {"name": "expected_impact", "label": "Expected impact of this hire", "type": "textarea",
             "placeholder": "Double sales pipeline, close 3 enterprise deals in Q1"},
            {"name": "alternative", "label": "Alternative to hiring", "type": "text",
             "placeholder": "Use freelance sales consultant at AED 10K/month"},
            {"name": "runway", "label": "Current runway", "type": "text",
             "placeholder": "8 months at current burn rate"},
        ],
    },
    "partnership": {
        "id": "partnership",
        "label": "Should I take this deal / partnership?",
        "description": "Evaluate a partnership, supplier deal, or business arrangement.",
        "icon": "handshake",
        "fields": [
            {"name": "decision", "label": "What's the deal?", "type": "text",
             "placeholder": "Exclusive distribution deal with regional supplier"},
            {"name": "terms", "label": "Key terms", "type": "textarea",
             "placeholder": "2-year exclusive, 30% margin, minimum order 500 units/month"},
            {"name": "upside", "label": "Potential upside", "type": "textarea",
             "placeholder": "Guaranteed supply, 15% lower cost than current supplier"},
            {"name": "downside", "label": "Potential downside", "type": "textarea",
             "placeholder": "Locked in for 2 years, can't use other suppliers"},
            {"name": "alternative", "label": "Alternative if you don't take the deal", "type": "text",
             "placeholder": "Continue with 3 non-exclusive suppliers at current rates"},
        ],
    },
    "freeform": {
        "id": "freeform",
        "label": "Custom business question",
        "description": "Ask any business question — no template, full flexibility.",
        "icon": "message-circle",
        "fields": [
            {"name": "decision", "label": "What are you deciding?", "type": "textarea",
             "placeholder": "Describe your business decision in detail..."},
            {"name": "context", "label": "Additional context (optional)", "type": "textarea",
             "placeholder": "Any relevant numbers, constraints, competitors, timeline..."},
        ],
    },
}


def build_debate_input(template_id: str, fields: dict[str, str]) -> tuple[str, str]:
    """Build (content, claim) from a template and user-provided field values.

    Returns the two strings that run_debate() expects.
    """
    template = TEMPLATES.get(template_id)
    if not template:
        raise ValueError(f"Unknown template: {template_id}")

    decision = fields.get("decision", "").strip()
    if not decision:
        raise ValueError("The 'decision' field is required.")

    if template_id == "freeform":
        context = fields.get("context", "").strip()
        return context, decision

    # Build structured context from all non-decision fields
    parts = []
    for field_def in template["fields"]:
        name = field_def["name"]
        if name == "decision":
            continue
        value = fields.get(name, "").strip()
        if value:
            parts.append(f"{field_def['label']}: {value}")

    content = "\n".join(parts)
    claim = f"Should I proceed with this decision: {decision}"

    return content, claim


def get_templates_metadata() -> list[dict]:
    """Return template metadata for the API / frontend."""
    result = []
    for tid, t in TEMPLATES.items():
        result.append({
            "id": t["id"],
            "label": t["label"],
            "description": t["description"],
            "icon": t["icon"],
            "fields": t["fields"],
        })
    return result
