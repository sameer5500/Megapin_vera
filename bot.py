from fastapi import FastAPI
from datetime import datetime
import time

app = FastAPI(title="Vera Challenge Bot")

START_TIME = time.time()

store = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {}
}

versions = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {}
}

sent_suppression = set()
conversation_memory = {}

MAX_ACTIONS_PER_TICK = 20


@app.get("/v1/healthz")
def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": {
            "category": len(store["category"]),
            "merchant": len(store["merchant"]),
            "customer": len(store["customer"]),
            "trigger": len(store["trigger"])
        }
    }


@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": "Team VeraFlow",
        "team_members": ["Sameer"],
        "model": "deterministic rule-based composer",
        "approach": "context-grounded merchant assistant using category, merchant, trigger, and customer context",
        "contact_email": "your-email@example.com",
        "version": "1.0.0",
        "submitted_at": datetime.utcnow().isoformat() + "Z"
    }


@app.post("/v1/context")
def receive_context(data: dict):
    scope = data.get("scope")
    context_id = data.get("context_id")
    version = data.get("version")
    payload = data.get("payload")

    if scope not in store:
        return {
            "accepted": False,
            "reason": "invalid_scope",
            "details": f"Unknown scope: {scope}"
        }

    if not context_id or version is None or payload is None:
        return {
            "accepted": False,
            "reason": "malformed_request",
            "details": "context_id, version, and payload are required"
        }

    current_version = versions[scope].get(context_id, 0)

    if version <= current_version:
        return {
            "accepted": False,
            "reason": "stale_version",
            "current_version": current_version
        }

    store[scope][context_id] = payload
    versions[scope][context_id] = version

    return {
        "accepted": True,
        "ack_id": f"ack_{context_id}_v{version}",
        "stored_at": datetime.utcnow().isoformat() + "Z"
    }


def find_digest_item(category: dict, item_id: str):
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def owner_name(merchant: dict):
    identity = merchant.get("identity", {})
    return identity.get("owner_first_name") or identity.get("name") or "there"


def merchant_salutation(category_slug: str, merchant: dict):
    owner = owner_name(merchant)

    if category_slug == "dentists":
        if owner.lower().startswith("dr."):
            return owner
        return f"Dr. {owner}"

    return owner


def active_offer_titles(merchant: dict):
    return [
        o.get("title")
        for o in merchant.get("offers", [])
        if o.get("status") == "active" and o.get("title")
    ]


def pct(value):
    try:
        return f"{round(value * 100)}%"
    except Exception:
        return str(value)


def compose_research_digest(category, merchant, trigger):
    category_slug = merchant.get("category_slug", "")
    name = merchant_salutation(category_slug, merchant)

    item_id = trigger.get("payload", {}).get("top_item_id")
    digest = find_digest_item(category, item_id)

    customer_aggregate = merchant.get("customer_aggregate", {})
    high_risk = customer_aggregate.get("high_risk_adult_count")

    if digest:
        title = digest.get("title", "new research update")
        source = digest.get("source", "latest category digest")
        summary = digest.get("summary", "")
        trial_n = digest.get("trial_n")
        actionable = digest.get("actionable", "")

        number_text = f"{trial_n:,}-patient trial: " if trial_n else ""

        merchant_anchor = ""
        if high_risk:
            merchant_anchor = f" This is relevant to your {high_risk} high-risk adult patients."

        action_line = f" Practical next step: {actionable}." if actionable else ""

        body = (
            f"{name}, quick update from {source}. "
            f"{number_text}{title}. "
            f"{summary[:180]}"
            f"{merchant_anchor}"
            f"{action_line} "
            f"Want me to draft a 2-line patient WhatsApp from this?"
        )

        rationale = (
            "Research digest trigger handled with source citation, category-specific tone, "
            "study numbers, and merchant-specific patient context."
        )
    else:
        body = (
            f"{name}, a new {category.get('display_name', 'category')} update is available. "
            f"Want me to extract the useful part and draft a customer WhatsApp?"
        )
        rationale = "Fallback research digest message because digest item was not found."

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="open_ended",
        rationale=rationale,
        template_name="vera_research_digest_v1"
    )


def compose_perf_dip(category, merchant, trigger):
    name = merchant_salutation(merchant.get("category_slug", ""), merchant)

    payload = trigger.get("payload", {})
    metric = payload.get("metric", "performance")
    delta_pct = payload.get("delta_pct")
    window = payload.get("window", "recently")
    baseline = payload.get("vs_baseline")

    peer_ctr = category.get("peer_stats", {}).get("avg_ctr")
    current_ctr = merchant.get("performance", {}).get("ctr")

    metric_text = metric.replace("_", " ")

    drop_text = ""
    if delta_pct is not None:
        drop_text = f"{metric_text} is down {abs(round(delta_pct * 100))}% over {window}"
    else:
        drop_text = f"{metric_text} has dropped recently"

    baseline_text = f" vs baseline {baseline}" if baseline else ""

    ctr_text = ""
    if current_ctr and peer_ctr:
        ctr_text = f" Your CTR is {round(current_ctr * 100, 1)}% vs peer avg {round(peer_ctr * 100, 1)}%."

    body = (
        f"{name}, quick flag — {drop_text}{baseline_text}."
        f"{ctr_text} "
        f"Want me to draft one profile/post fix to recover calls this week?"
    )

    rationale = (
        "Performance dip trigger handled with metric delta, merchant performance context, "
        "peer comparison where available, and one low-friction recovery CTA."
    )

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="binary_yes_no",
        rationale=rationale,
        template_name="vera_perf_dip_v1"
    )


def compose_review_theme(category, merchant, trigger):
    name = merchant_salutation(merchant.get("category_slug", ""), merchant)
    payload = trigger.get("payload", {})

    theme = payload.get("theme", "customer feedback").replace("_", " ")
    occurrences = payload.get("occurrences_30d")
    quote = payload.get("common_quote")

    occ_text = f"{occurrences} reviews in 30 days mention " if occurrences else "Recent reviews mention "
    quote_text = f' Common line: "{quote}".' if quote else ""

    body = (
        f"{name}, review pattern spotted — {occ_text}{theme}."
        f"{quote_text} "
        f"Want me to draft a polite review reply + one operational fix message?"
    )

    rationale = (
        "Review-theme trigger handled using exact complaint theme and occurrence count, "
        "with category-safe tone and one concrete next action."
    )

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="binary_yes_no",
        rationale=rationale,
        template_name="vera_review_theme_v1"
    )


def compose_customer_recall(category, merchant, customer, trigger):
    identity = customer.get("identity", {})
    relationship = customer.get("relationship", {})
    preferences = customer.get("preferences", {})
    payload = trigger.get("payload", {})

    customer_name = identity.get("name", "there")
    merchant_name = merchant.get("identity", {}).get("name", "the clinic")

    last_service = payload.get("last_service_date") or relationship.get("last_visit")
    due_date = payload.get("due_date")
    slots = payload.get("available_slots", [])

    active_offers = active_offer_titles(merchant)
    offer_text = active_offers[0] if active_offers else "your regular checkup"

    slot_text = ""
    if len(slots) >= 2:
        slot_text = f"{slots[0].get('label')} ya {slots[1].get('label')}"
    elif len(slots) == 1:
        slot_text = slots[0].get("label")

    lang = identity.get("language_pref", "")
    hi_mix = "hi" in lang.lower()

    if hi_mix:
        body = (
            f"Hi {customer_name}, {merchant_name} here 🦷 "
            f"Aapka 6-month cleaning recall due hai."
        )
        if last_service:
            body += f" Last visit {last_service} tha."
        if slot_text:
            body += f" Apke liye slots ready hain: {slot_text}."
        body += f" {offer_text}. Reply 1 for first slot, 2 for second slot, or tell us a time."
    else:
        body = (
            f"Hi {customer_name}, {merchant_name} here 🦷 "
            f"Your 6-month cleaning recall is due."
        )
        if last_service:
            body += f" Last visit: {last_service}."
        if due_date:
            body += f" Due date: {due_date}."
        if slot_text:
            body += f" Available slots: {slot_text}."
        body += f" {offer_text}. Reply with your preferred slot."

    rationale = (
        "Customer recall trigger handled using customer relationship, preferred language, "
        "available slots, and merchant's active offer."
    )

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="multi_choice_slot",
        rationale=rationale,
        template_name="merchant_recall_reminder_v1",
        customer_id=customer.get("customer_id"),
        send_as="merchant_on_behalf"
    )


def compose_ipl_match(category, merchant, trigger):
    name = merchant_salutation(merchant.get("category_slug", ""), merchant)
    payload = trigger.get("payload", {})

    match = payload.get("match", "IPL match")
    venue = payload.get("venue", "")
    match_time = payload.get("match_time_iso", "")
    is_weeknight = payload.get("is_weeknight")

    offers = active_offer_titles(merchant)
    offer_text = offers[0] if offers else "a match-night combo"

    if is_weeknight is False:
        recommendation = (
            f"Since this is not a weeknight, avoid a heavy dine-in promo; push {offer_text} as delivery-first."
        )
    else:
        recommendation = (
            f"Weeknight matches can lift orders — push {offer_text} before match time."
        )

    body = (
        f"{name}, quick IPL heads-up — {match} at {venue} today."
        f" {recommendation} "
        f"Want me to draft a short WhatsApp + Insta story for tonight?"
    )

    rationale = (
        "IPL trigger handled with match context, merchant's active offer, and restaurant-specific operator advice."
    )

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="binary_yes_no",
        rationale=rationale,
        template_name="vera_ipl_match_v1"
    )


def compose_curious_ask(category, merchant, trigger):
    name = merchant_salutation(merchant.get("category_slug", ""), merchant)
    biz = merchant.get("identity", {}).get("name", "your business")

    body = (
        f"Hi {name}, quick check — what service/product has been most asked-for this week at {biz}? "
        f"I’ll turn your answer into a Google post + 4-line WhatsApp reply. Takes 5 min."
    )

    rationale = (
        "Curious ask trigger handled as a low-friction merchant question with a useful output promised."
    )

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="open_ended",
        rationale=rationale,
        template_name="vera_curious_ask_v1"
    )


def compose_generic(category, merchant, trigger):
    name = merchant_salutation(merchant.get("category_slug", ""), merchant)
    kind = trigger.get("kind", "update").replace("_", " ")

    body = (
        f"{name}, quick update related to {kind}. "
        f"Want me to turn this into one useful customer message or Google post?"
    )

    rationale = (
        "Generic fallback used because no specialized composer matched the trigger kind. "
        "Kept concise and action-oriented."
    )

    return make_action(
        merchant=merchant,
        trigger=trigger,
        body=body,
        cta="binary_yes_no",
        rationale=rationale,
        template_name="vera_generic_v1"
    )


def make_action(
    merchant,
    trigger,
    body,
    cta,
    rationale,
    template_name,
    customer_id=None,
    send_as="vera"
):
    conversation_id = f"conv_{merchant['merchant_id']}_{trigger['id']}"

    conversation_memory[conversation_id] = {
        "merchant_id": merchant["merchant_id"],
        "trigger_id": trigger["id"],
        "turns": []
    }

    return {
        "conversation_id": conversation_id,
        "merchant_id": merchant["merchant_id"],
        "customer_id": customer_id,
        "send_as": send_as,
        "trigger_id": trigger["id"],
        "template_name": template_name,
        "template_params": [body[:250]],
        "body": body.strip(),
        "cta": cta,
        "suppression_key": trigger.get("suppression_key", trigger["id"]),
        "rationale": rationale
    }


@app.post("/v1/tick")
def tick(data: dict):
    actions = []

    for trigger_id in data.get("available_triggers", []):
        if len(actions) >= MAX_ACTIONS_PER_TICK:
            break

        trigger = store["trigger"].get(trigger_id)
        if not trigger:
            continue

        suppression_key = trigger.get("suppression_key", trigger_id)
        if suppression_key in sent_suppression:
            continue

        merchant_id = trigger.get("merchant_id")
        merchant = store["merchant"].get(merchant_id)
        if not merchant:
            continue

        category_slug = merchant.get("category_slug")
        category = store["category"].get(category_slug)
        if not category:
            continue

        kind = trigger.get("kind")

        if trigger.get("scope") == "customer":
            customer_id = trigger.get("customer_id")
            customer = store["customer"].get(customer_id)
            if not customer:
                continue

            if kind == "recall_due":
                action = compose_customer_recall(category, merchant, customer, trigger)
            else:
                action = compose_generic(category, merchant, trigger)

        elif kind == "research_digest":
            action = compose_research_digest(category, merchant, trigger)

        elif kind in ["perf_dip", "seasonal_perf_dip"]:
            action = compose_perf_dip(category, merchant, trigger)

        elif kind == "review_theme_emerged":
            action = compose_review_theme(category, merchant, trigger)

        elif kind == "ipl_match_today":
            action = compose_ipl_match(category, merchant, trigger)

        elif kind == "curious_ask_due":
            action = compose_curious_ask(category, merchant, trigger)

        else:
            action = compose_generic(category, merchant, trigger)

        actions.append(action)
        sent_suppression.add(suppression_key)

    return {"actions": actions}


def is_auto_reply(message: str):
    msg = message.lower()
    phrases = [
        "thank you for contacting",
        "our team will respond",
        "we will respond shortly",
        "we will get back",
        "automated message",
        "business account"
    ]
    return any(p in msg for p in phrases)


def is_stop(message: str):
    msg = message.lower()
    phrases = [
        "stop",
        "not interested",
        "don't message",
        "do not message",
        "unsubscribe",
        "useless",
        "bothering me"
    ]
    return any(p in msg for p in phrases)


def is_positive_intent(message: str):
    msg = message.lower()
    phrases = [
        "yes",
        "ok",
        "okay",
        "send",
        "draft",
        "do it",
        "let's do it",
        "confirm",
        "go ahead",
        "please"
    ]
    return any(p in msg for p in phrases)


@app.post("/v1/reply")
def reply(data: dict):
    conversation_id = data.get("conversation_id", "")
    message = data.get("message", "")
    turn_number = data.get("turn_number", 0)

    if conversation_id not in conversation_memory:
        conversation_memory[conversation_id] = {"turns": []}

    conversation_memory[conversation_id]["turns"].append({
        "turn_number": turn_number,
        "message": message,
        "received_at": data.get("received_at")
    })

    auto_count = sum(
        1 for t in conversation_memory[conversation_id]["turns"]
        if is_auto_reply(t.get("message", ""))
    )

    if is_stop(message):
        return {
            "action": "end",
            "rationale": "Merchant/customer clearly opted out or expressed frustration. Ending conversation."
        }

    if is_auto_reply(message):
        if auto_count == 1:
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": "Detected WhatsApp Business auto-reply. Backing off for 4 hours."
            }
        if auto_count == 2:
            return {
                "action": "wait",
                "wait_seconds": 86400,
                "rationale": "Repeated auto-reply detected. Waiting 24 hours before retry."
            }
        return {
            "action": "end",
            "rationale": "Auto-reply repeated multiple times with no real engagement. Ending conversation."
        }

    if "gst" in message.lower() or "tax filing" in message.lower():
        return {
            "action": "send",
            "body": (
                "That part is better handled by your CA. "
                "Coming back to this business update — want me to draft the customer message first?"
            ),
            "cta": "binary_yes_no",
            "rationale": "Off-topic request declined politely, then redirected to original business task."
        }

    if is_positive_intent(message):
        return {
            "action": "send",
            "body": (
                "Great — here’s a short draft you can use:\n\n"
                "“Quick update from our team: we’re sharing a useful reminder for customers this week. "
                "Reply here if you’d like help choosing the right service or booking a slot.”\n\n"
                "Want me to make this more promotional or more educational?"
            ),
            "cta": "open_ended",
            "rationale": "Positive intent detected; switching from qualification to action with a usable draft."
        }

    return {
        "action": "send",
        "body": "Got it. Want me to draft the customer WhatsApp first?",
        "cta": "binary_yes_no",
        "rationale": "Keeps the conversation focused with a single low-friction next step."
    }
