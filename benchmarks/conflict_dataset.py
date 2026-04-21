"""
Conflict-detection benchmark dataset.

Each candidate is a new requirement we imagine someone adding to the
50-req e-commerce corpus (see retrieval_dataset.py). Labels capture
the ground truth: which existing REQ-ids a reviewer should flag — and
what kind of relationship it is.

Label categories:
  contradiction  — logical conflict (different numbers / opposing rules)
  overlap        — semantically the same rule restated (redundancy)
  related-ok     — same topic, different aspect, no conflict
  unrelated      — control; no existing req this should touch

The `conflicts_with` field is the set of existing REQ-ids a reviewer
would flag as a true conflict (contradiction or overlap). For
related-ok and unrelated candidates this is empty — any flag from
Loom on those candidates is a false positive.

Loom's algorithm (docs.check_conflicts) is similarity-based: it flags
same-domain similarity >0.85 or cross-domain >0.9, plus same-domain
keyword overlap ≥3 non-stopwords. It does NOT parse numbers or
negation. The `hard` marker on a contradiction means we're testing
a case the similarity heuristic should still catch (because the
reqs share vocabulary), while `logic-only` marks contradictions that
need actual semantic understanding of negation/numbers to detect —
these are expected misses, not pass/fail cases.
"""
from __future__ import annotations

# (candidate_text, domain, conflicts_with: set[str], category, note)
CANDIDATES: list[tuple[str, str, set[str], str, str]] = [
    # =========================================================
    # Contradictions — should be caught
    # =========================================================
    (
        "Session tokens expire after sixty days of user inactivity",
        "behavior", {"REQ-auth-03"},
        "contradiction",
        "different number for the same session-expiry rule",
    ),
    (
        "Orders over $75 qualify for free standard shipping",
        "behavior", {"REQ-shp-01"},
        "contradiction",
        "different threshold for same free-shipping rule",
    ),
    (
        "Returns are accepted within sixty days of delivery",
        "behavior", {"REQ-ret-01"},
        "contradiction",
        "different return window",
    ),
    (
        "Cart contents persist for seven days when the shopper is logged in",
        "behavior", {"REQ-cart-01"},
        "contradiction",
        "different cart retention period",
    ),
    (
        "Passwords must be at least 8 characters with one digit and one symbol",
        "data", {"REQ-auth-02"},
        "contradiction",
        "different min length for password policy",
    ),
    (
        "Refunds must be issued within ten business days of the return being received",
        "behavior", {"REQ-ret-02"},
        "contradiction",
        "different refund SLA",
    ),
    (
        "Low-inventory alerts fire when a SKU drops below five units on hand",
        "behavior", {"REQ-adm-02"},
        "contradiction",
        "different low-stock threshold",
    ),
    (
        "The checkout flow may span up to five screens",
        "ui", {"REQ-chk-01"},
        "contradiction",
        "different max screen count for checkout",
    ),

    # =========================================================
    # Contradictions that need actual reasoning (logic-only)
    # The similarity heuristic will likely MISS these. We include
    # them to quantify the miss rate on real-world adversarial cases.
    # =========================================================
    (
        "Guest checkout is not permitted; a full account is required before buying",
        "behavior", {"REQ-cart-02"},
        "contradiction-logic",
        "logical opposite — guest checkout is/isn't allowed",
    ),
    (
        "Product reviews may be posted by any registered user, purchase not required",
        "behavior", {"REQ-prd-03"},
        "contradiction-logic",
        "removes the verified-purchase constraint",
    ),
    (
        "Administrators may sign in with only a username and password",
        "behavior", {"REQ-cmp-02"},
        "contradiction-logic",
        "opposes 2FA requirement",
    ),

    # =========================================================
    # Overlaps — redundant restatements. Should be caught.
    # =========================================================
    (
        "After a sale completes, the customer receives an email receipt within one minute",
        "behavior", {"REQ-not-01"},
        "overlap",
        "restates confirmation-email-within-60s",
    ),
    (
        "Credit cards accepted are Visa, Mastercard, Amex, and Discover",
        "architecture", {"REQ-pay-01"},
        "overlap",
        "near-identical restatement of payment methods",
    ),
    (
        "We deliver to 45 non-US countries",
        "behavior", {"REQ-shp-05"},
        "overlap",
        "restates international shipping list size",
    ),
    (
        "Product images need to be a minimum of 1200x1200px and under 500KB",
        "data", {"REQ-prd-01"},
        "overlap",
        "restates image requirements",
    ),
    (
        "The order-history screen displays the current state of any ongoing return",
        "ui", {"REQ-ret-05"},
        "overlap",
        "restates return-status visibility",
    ),

    # =========================================================
    # Related-but-compatible — same domain, no conflict.
    # Any flag from Loom here is a FALSE POSITIVE.
    # =========================================================
    (
        "Session cookies must be marked Secure and HttpOnly",
        "architecture", set(),
        "related-ok",
        "security attribute on cookies, not about expiry",
    ),
    (
        "Failed login attempts are logged with the source IP address",
        "data", set(),
        "related-ok",
        "logging behavior, not the rate-limit rule",
    ),
    (
        "Returned items must be in the original packaging when sent back",
        "behavior", set(),
        "related-ok",
        "additional return rule, doesn't conflict with window or refund SLA",
    ),
    (
        "Product images may optionally include a short looping video",
        "ui", set(),
        "related-ok",
        "additive image option, not a resolution rule",
    ),
    (
        "Abandoned carts may be recovered by clicking a link in the reminder email",
        "ui", set(),
        "related-ok",
        "UX detail, not a contradiction with the 24h timing rule",
    ),
    (
        "Inventory counts are synced with the warehouse every 15 minutes",
        "architecture", set(),
        "related-ok",
        "inventory plumbing, unrelated to the low-stock alert threshold",
    ),
    (
        "Gift card codes are 16 alphanumeric characters",
        "data", set(),
        "related-ok",
        "format detail, unrelated to the tax-before-gift-card rule",
    ),
    (
        "Shipping carriers supported include UPS, FedEx, and USPS",
        "architecture", set(),
        "related-ok",
        "carrier list, separate concern from free-shipping threshold",
    ),

    # =========================================================
    # Unrelated — control. Flags here are pure false positives.
    # =========================================================
    (
        "Shoppers can leave wishlist items visible to friends via a share link",
        "ui", set(),
        "unrelated",
        "wishlist sharing, no existing rule touches it",
    ),
    (
        "Staff may annotate customer orders with internal notes up to 2000 characters",
        "data", set(),
        "unrelated",
        "admin tooling detail",
    ),
    (
        "Homepage banner images rotate every five seconds",
        "ui", set(),
        "unrelated",
        "marketing UI detail",
    ),
    (
        "Support tickets are routed to teams based on product category",
        "architecture", set(),
        "unrelated",
        "customer service concern, nothing in corpus",
    ),
]
