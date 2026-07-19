"""Fine-tune DistilBERT on synthetic seed data (Phase 5 classifier decision).

Labels are the seeded category names (scripts/seed.py). Training data is
synthetic — templated ticket texts per category — because no historical ticket
data exists yet; retrain on real tickets once the feedback loop
(ai_classification_history.corrected_*) has accumulated labels.

    .venv/bin/python -m scripts.train_classifier      # from backend/

Writes model + tokenizer to Settings.classifier_dir (ml_models/classifier).
"""

import random

import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.config import get_settings

BASE_MODEL = "distilbert-base-uncased"
EPOCHS = 6
BATCH_SIZE = 8
LR = 5e-5

# ponytail: hand-written synthetic examples keyed to the seeded taxonomy.
# This is a placeholder signal by design — the user-chosen classifier needs
# training data and none exists yet. Replace with real corrected tickets later.
SEED_EXAMPLES: dict[str, list[str]] = {
    "Refunds": [
        "I want my money back for last month's charge",
        "Please refund the duplicate payment on my account",
        "I was charged twice and need a refund",
        "Requesting a refund for the subscription I cancelled",
        "The product didn't work, I'd like a full refund",
        "How long does it take to get refunded after cancellation",
        "Refund still not received after two weeks",
        "I returned the item but no refund has appeared",
        "Charge me back for the order I never received",
        "Cancel my plan and refund the remaining balance",
    ],
    "Invoices": [
        "I need a copy of my invoice for March",
        "The invoice total doesn't match what I was charged",
        "Please add our VAT number to the invoice",
        "Where can I download my billing invoices",
        "Invoice shows the wrong company address",
        "I need an itemized invoice for accounting",
        "Can you resend invoice number 4521",
        "Our finance team needs invoices in PDF format",
        "The invoice due date is incorrect",
        "Billing statement is missing last month's invoice",
    ],
    "Login Issues": [
        "I can't log in to my account",
        "Password reset email never arrives",
        "Two factor authentication code is not working",
        "My account is locked after too many attempts",
        "Login page keeps saying invalid credentials",
        "I forgot my password and the reset link is broken",
        "Single sign on redirects to an error page",
        "Session expires immediately after signing in",
        "Cannot access my account since the email change",
        "The app logs me out every few minutes",
    ],
    "Bug Report": [
        "The dashboard crashes when I open reports",
        "Export button does nothing when clicked",
        "Getting a 500 error when saving my profile",
        "Charts render blank on the analytics page",
        "The mobile app freezes on startup",
        "File upload fails with an unknown error",
        "Search returns no results even for exact matches",
        "Notifications arrive hours late",
        "Date picker shows the wrong month",
        "App displays NaN instead of totals",
    ],
    "General": [
        "What are your support hours",
        "How do I upgrade my plan",
        "Do you offer discounts for nonprofits",
        "Where can I find the product documentation",
        "I'd like to give some feedback about the service",
        "Can I change the language of the interface",
        "How many users does my plan include",
        "Is there a mobile app available",
        "What is your data retention policy",
        "How do I contact sales about enterprise pricing",
    ],
}

PREFIXES = ["", "Hi, ", "Hello team, ", "Urgent: ", "Question: ", "Help - "]


def build_dataset() -> tuple[list[str], list[int], dict[int, str]]:
    labels = sorted(SEED_EXAMPLES)
    id2label = dict(enumerate(labels))
    label2id = {v: k for k, v in id2label.items()}
    texts, ys = [], []
    for label, examples in SEED_EXAMPLES.items():
        for example in examples:
            for prefix in PREFIXES:  # cheap augmentation
                texts.append(prefix + example)
                ys.append(label2id[label])
    return texts, ys, id2label


def main() -> None:
    random.seed(0)
    torch.manual_seed(0)
    texts, ys, id2label = build_dataset()
    out_dir = get_settings().classifier_dir

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(id2label),
        id2label=id2label,
        label2id={v: k for k, v in id2label.items()},
    )

    encodings = tokenizer(texts, truncation=True, max_length=64, padding=True, return_tensors="pt")
    dataset = list(zip(encodings["input_ids"], encodings["attention_mask"], ys, strict=True))
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    model.train()
    for epoch in range(EPOCHS):
        total = 0.0
        for input_ids, attention_mask, y in loader:
            optimizer.zero_grad()
            output = model(input_ids=input_ids, attention_mask=attention_mask, labels=y)
            output.loss.backward()
            optimizer.step()
            total += float(output.loss)
        print(f"epoch {epoch + 1}/{EPOCHS} loss={total / len(loader):.4f}")

    model.eval()
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"Saved classifier ({len(id2label)} labels) to {out_dir}")


if __name__ == "__main__":
    main()
