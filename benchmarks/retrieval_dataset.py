"""
Retrieval benchmark dataset — synthetic e-commerce requirements + labeled queries.

Design rationale:
  - Familiar domain (e-commerce) so queries feel realistic.
  - 50 requirements across 10 domains, 5 each. Dense enough to force
    semantic retrieval to discriminate between related rules.
  - Each query is paired with ONE ground-truth req_id. Corpus was written
    to avoid near-duplicate reqs that would make "one correct answer"
    ambiguous. When in doubt, the req the query most specifically targets
    wins.
  - Queries avoid copying vocabulary from the req text so we're measuring
    semantic match, not keyword hits. Mix of paraphrase, goal-oriented,
    and jargon queries.
  - Difficulty label is informational — lets us see which query styles
    retrieval handles well vs. poorly.
"""
from __future__ import annotations

# Each req: (id, domain, value)
REQUIREMENTS: list[tuple[str, str, str]] = [
    # ---- auth ----
    ("REQ-auth-01", "behavior",     "Users must confirm their email address before completing their first order"),
    ("REQ-auth-02", "data",         "Passwords must be at least 12 characters and contain one digit and one symbol"),
    ("REQ-auth-03", "behavior",     "Session tokens expire after 30 days of user inactivity"),
    ("REQ-auth-04", "architecture", "Social sign-in supported via Google, Apple, and Facebook identity providers"),
    ("REQ-auth-05", "behavior",     "After five failed login attempts within ten minutes, further attempts are rate-limited for one hour"),

    # ---- cart ----
    ("REQ-cart-01", "behavior",     "When a signed-in shopper adds items but does not check out, their cart is preserved for thirty days"),
    ("REQ-cart-02", "behavior",     "Guests may check out without creating an account; the system still generates a lightweight account for order tracking"),
    ("REQ-cart-03", "behavior",     "If a cart has items but no checkout activity for 24 hours, the user receives a reminder email"),
    ("REQ-cart-04", "ui",           "Out-of-stock products remain listed but cannot be added to the cart; an 'Email me when available' control appears instead"),
    ("REQ-cart-05", "data",         "Cart totals display the shopper's local currency inferred from their IP address"),

    # ---- checkout ----
    ("REQ-chk-01",  "ui",           "The checkout flow must complete in no more than three screens"),
    ("REQ-chk-02",  "behavior",     "Sales tax is computed during checkout based on the shipping destination"),
    ("REQ-chk-03",  "architecture", "The payment entry form must never persist raw card data on our servers"),
    ("REQ-chk-04",  "ui",           "Mobile checkout surfaces Apple Pay and Google Pay as first-class payment options"),
    ("REQ-chk-05",  "behavior",     "Promotional codes are validated server-side before the order total is recalculated"),

    # ---- product ----
    ("REQ-prd-01",  "data",         "Product hero images must be at least 1200 by 1200 pixels and no larger than 500 kilobytes"),
    ("REQ-prd-02",  "behavior",     "Search results are ordered by relevance score, then by number of orders in the last 30 days"),
    ("REQ-prd-03",  "behavior",     "Product reviews are only accepted from accounts that have a completed order for that product"),
    ("REQ-prd-04",  "behavior",     "The storefront search tolerates typos — a misspelled query still returns reasonable matches"),
    ("REQ-prd-05",  "behavior",     "Shoppers can save a product to favourites without placing it in their cart"),

    # ---- shipping ----
    ("REQ-shp-01",  "behavior",     "Orders totalling more than fifty dollars ship at no cost using the standard service"),
    ("REQ-shp-02",  "architecture", "Delivery addresses are validated against the USPS address database before an order is accepted"),
    ("REQ-shp-03",  "behavior",     "After payment clears, the warehouse has two business days to hand the parcel to the carrier"),
    ("REQ-shp-04",  "behavior",     "The buyer receives the carrier tracking number by email as soon as the label is generated"),
    ("REQ-shp-05",  "behavior",     "We ship to 45 countries outside the United States; rates are quoted at checkout"),

    # ---- returns ----
    ("REQ-ret-01",  "behavior",     "An item may be returned within thirty days of the delivery date"),
    ("REQ-ret-02",  "behavior",     "When a returned parcel is logged as received, the refund must be issued within five business days"),
    ("REQ-ret-03",  "behavior",     "If an item arrives defective, we cover the return shipping fee"),
    ("REQ-ret-04",  "behavior",     "Clearance-priced items are marked final sale and are not eligible for return"),
    ("REQ-ret-05",  "ui",           "The order history page shows the live status of any in-flight return"),

    # ---- payment ----
    ("REQ-pay-01",  "architecture", "We accept Visa, Mastercard, American Express, and Discover cards"),
    ("REQ-pay-02",  "behavior",     "Orders over one hundred dollars are eligible for monthly installment payments through Affirm"),
    ("REQ-pay-03",  "data",         "Store credit balances have no expiration date"),
    ("REQ-pay-04",  "behavior",     "Gift card value is deducted from the order subtotal before sales tax is calculated"),
    ("REQ-pay-05",  "behavior",     "Refunds are issued to whichever payment instrument was originally charged"),

    # ---- notifications ----
    ("REQ-not-01",  "behavior",     "A confirmation email is dispatched within one minute of a successful purchase"),
    ("REQ-not-02",  "behavior",     "Delivery-progress emails fire at three points: label created, in transit, and delivered"),
    ("REQ-not-03",  "ui",           "Users can disable promotional emails without affecting transactional emails"),
    ("REQ-not-04",  "behavior",     "Text-message alerts are opt-in and require the shopper to verify their mobile number via one-time code"),
    ("REQ-not-05",  "data",         "Per-channel notification preferences are persisted on the user profile"),

    # ---- admin ----
    ("REQ-adm-01",  "ui",           "The operator dashboard surfaces daily revenue, order volume, and visit-to-order conversion"),
    ("REQ-adm-02",  "behavior",     "A low-inventory alert is raised when any SKU drops below ten units on hand"),
    ("REQ-adm-03",  "behavior",     "Catalog price changes require approval from a user with the manager role before publishing"),
    ("REQ-adm-04",  "data",         "Every administrative action is written to an audit log retained for two years"),
    ("REQ-adm-05",  "ui",           "Sales and inventory reports can be exported as CSV or PDF from the dashboard"),

    # ---- compliance ----
    ("REQ-cmp-01",  "data",         "Account deletion leaves order records in place for seven years to satisfy tax retention rules"),
    ("REQ-cmp-02",  "behavior",     "Staff with the administrator role must authenticate with a second factor via authenticator app"),
    ("REQ-cmp-03",  "data",         "EU customers may request an export of all personal data we hold about them, delivered within 30 days"),
    ("REQ-cmp-04",  "architecture", "PII at rest is encrypted; production secrets are rotated every 90 days"),
    ("REQ-cmp-05",  "behavior",     "Cookie consent banner is shown to visitors from the EU and EEA on their first visit"),
]


# Each query: (query_text, expected_req_id, difficulty)
# difficulty values:
#   paraphrase  — rewording that shares some vocabulary
#   goal        — goal-oriented, shares little vocabulary
#   jargon      — uses domain terminology / acronyms
QUERIES: list[tuple[str, str, str]] = [
    # auth
    ("Can a brand-new account place an order right after signing up?",         "REQ-auth-01", "goal"),
    ("What do we require before someone's first checkout?",                    "REQ-auth-01", "paraphrase"),
    ("How strong do passwords have to be?",                                    "REQ-auth-02", "paraphrase"),
    ("Password complexity rules",                                              "REQ-auth-02", "jargon"),
    ("How long can I stay logged in before I have to sign back in?",           "REQ-auth-03", "goal"),
    ("Which third-party logins do we offer?",                                  "REQ-auth-04", "paraphrase"),
    ("SSO providers",                                                          "REQ-auth-04", "jargon"),
    ("What happens after someone keeps getting their password wrong?",         "REQ-auth-05", "goal"),
    ("Brute-force protection on the login form",                               "REQ-auth-05", "jargon"),

    # cart
    ("A logged-in customer puts things in their basket and leaves — how long before those items disappear?", "REQ-cart-01", "goal"),
    ("Do people have to create an account to buy something?",                  "REQ-cart-02", "goal"),
    ("Anonymous checkout support",                                             "REQ-cart-02", "jargon"),
    ("When do we email someone who forgot about their cart?",                  "REQ-cart-03", "paraphrase"),
    ("Abandoned cart recovery",                                                "REQ-cart-03", "jargon"),
    ("What shows up on the product page when something is sold out?",          "REQ-cart-04", "goal"),
    ("How do we decide which currency to display prices in?",                  "REQ-cart-05", "paraphrase"),

    # checkout
    ("Maximum number of steps at checkout",                                    "REQ-chk-01", "jargon"),
    ("Where does sales tax get added to the order?",                           "REQ-chk-02", "paraphrase"),
    ("PCI compliance stance",                                                  "REQ-chk-03", "jargon"),
    ("Do we store credit card numbers anywhere?",                              "REQ-chk-03", "goal"),
    ("What payment options should appear on phones?",                          "REQ-chk-04", "paraphrase"),
    ("Someone entered a discount code — where is it checked?",                 "REQ-chk-05", "goal"),

    # product
    ("What are the image requirements for new products?",                      "REQ-prd-01", "paraphrase"),
    ("How are search results sorted?",                                         "REQ-prd-02", "paraphrase"),
    ("Ranking algorithm for catalog search",                                   "REQ-prd-02", "jargon"),
    ("Can anyone leave a product review?",                                     "REQ-prd-03", "goal"),
    ("Verified purchase reviews",                                              "REQ-prd-03", "jargon"),
    ("What if someone misspells a product name?",                              "REQ-prd-04", "goal"),
    ("Fuzzy search support",                                                   "REQ-prd-04", "jargon"),
    ("Wishlist behavior",                                                      "REQ-prd-05", "jargon"),

    # shipping
    ("When does shipping become free?",                                        "REQ-shp-01", "goal"),
    ("Free shipping threshold",                                                "REQ-shp-01", "jargon"),
    ("How do we check that a delivery address is real?",                       "REQ-shp-02", "paraphrase"),
    ("How quickly do we ship after a purchase?",                               "REQ-shp-03", "paraphrase"),
    ("Order fulfillment SLA",                                                  "REQ-shp-03", "jargon"),
    ("When does the buyer get their tracking link?",                           "REQ-shp-04", "paraphrase"),
    ("Do we ship internationally?",                                            "REQ-shp-05", "goal"),

    # returns
    ("How many days do customers have to send something back?",                "REQ-ret-01", "paraphrase"),
    ("Return window",                                                          "REQ-ret-01", "jargon"),
    ("When does the buyer's money come back?",                                 "REQ-ret-02", "goal"),
    ("Who pays to send back a broken item?",                                   "REQ-ret-03", "goal"),
    ("What items can't be returned?",                                          "REQ-ret-04", "paraphrase"),
    ("Where can the customer track a return in progress?",                     "REQ-ret-05", "paraphrase"),

    # payment
    ("Which credit card brands do we take?",                                   "REQ-pay-01", "paraphrase"),
    ("Can I pay in installments?",                                             "REQ-pay-02", "goal"),
    ("BNPL support",                                                           "REQ-pay-02", "jargon"),
    ("Does store credit ever run out?",                                        "REQ-pay-03", "goal"),
    ("Is tax charged on the full amount or after a gift card?",                "REQ-pay-04", "goal"),
    ("How do we return a customer's money?",                                   "REQ-pay-05", "paraphrase"),

    # notifications
    ("How long after payment does the receipt email arrive?",                  "REQ-not-01", "paraphrase"),
    ("Which events trigger a shipping email?",                                 "REQ-not-02", "paraphrase"),
    ("Can users unsubscribe from marketing mail?",                             "REQ-not-03", "goal"),
    ("How does a shopper start getting text messages from us?",                "REQ-not-04", "paraphrase"),
    ("SMS opt-in flow",                                                        "REQ-not-04", "jargon"),
    ("Where are per-user notification settings kept?",                         "REQ-not-05", "paraphrase"),

    # admin
    ("What does the merchant see when they log in?",                           "REQ-adm-01", "goal"),
    ("Business metrics on the dashboard",                                      "REQ-adm-01", "jargon"),
    ("Low stock warning threshold",                                            "REQ-adm-02", "jargon"),
    ("Who can publish a price change?",                                        "REQ-adm-03", "goal"),
    ("Price change approval workflow",                                         "REQ-adm-03", "jargon"),
    ("How long do we keep the admin action log?",                              "REQ-adm-04", "paraphrase"),
    ("What formats are report exports available in?",                          "REQ-adm-05", "paraphrase"),

    # compliance
    ("If someone deletes their account, do we delete their orders too?",       "REQ-cmp-01", "goal"),
    ("Tax record retention",                                                   "REQ-cmp-01", "jargon"),
    ("Do admins use two-factor authentication?",                               "REQ-cmp-02", "paraphrase"),
    ("GDPR data export",                                                       "REQ-cmp-03", "jargon"),
    ("How does a European customer get a copy of their data?",                 "REQ-cmp-03", "goal"),
    ("Secret rotation schedule",                                               "REQ-cmp-04", "jargon"),
    ("When do EU visitors see the cookie prompt?",                             "REQ-cmp-05", "paraphrase"),

    # intentionally hard ones — none are in the corpus
    # (commented out for now; could be added as 'should return nothing' cases)
]
