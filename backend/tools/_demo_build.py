"""Build the MunchMate 500-review demo CSV from the authored content pools."""

import csv
import os
import random

from _demo_data import (
    ASK_CLOSERS,
    ASK_OPENERS,
    BUG_TOPICS,
    FEATURE_TOPICS,
    PERF_TOPICS,
    PRAISE_TOPICS,
    SAFE_CLOSERS,
    SAFE_OPENERS,
    SPILL,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "MunchMate_500_reviews.csv")

# Which secondary complaint rides along with each topic. This is how one review
# ends up mentioning two problems, which is what real review corpora look like.
SPILL_FOR = {
    "B1_late_delivery": ["cold", "tracking", "support"],
    "B2_cold_food": ["late", "wrong"],
    "B3_wrong_order": ["missing", "support"],
    "B4_missing_items": ["refund", "support", "wrong"],
    "B5_refund": ["support", "fee"],
    "B6_payment_failed": ["refund", "support"],
    "B7_crash": ["slow", "battery"],
    "B8_cancelled": ["refund", "support"],
    "B9_promo": ["support"],
    "B10_login": ["slow"],
    "X1_tracking_lag": ["late", "tracking"],
    "X2_slow_load": ["slow", "battery"],
    "X3_battery": ["battery", "slow"],
    "X4_buffering": ["slow"],
    "X5_checkout_delay": ["slow"],
    "X6_gps": ["late", "support"],
    "P9_fee_complaints": ["fee", "support"],
}

FIRST_NAMES = [
    "Aarav", "Aditi", "Aditya", "Aisha", "Akash", "Alisha", "Aman", "Amrita", "Ananya",
    "Andrew", "Anil", "Anjali", "Ankit", "Arjun", "Arun", "Ashwin", "Ayesha", "Bhavna",
    "Carlos", "Charu", "Chetan", "Daniel", "Deepa", "Deeksha", "Dev", "Dhruv", "Diana",
    "Ekta", "Farhan", "Fatima", "Gaurav", "Gayatri", "Hannah", "Harini", "Harish",
    "Harsh", "Hema", "Imran", "Indira", "Ishaan", "Ishita", "James", "Jaya", "Jitendra",
    "Kabir", "Kajal", "Kamal", "Karan", "Kavya", "Kiran", "Kritika", "Lakshmi", "Lata",
    "Laura", "Madhav", "Manish", "Meera", "Miguel", "Mira", "Mohit", "Naina", "Nandan",
    "Neha", "Nikhil", "Niranjan", "Nisha", "Olivia", "Pallavi", "Pankaj", "Pooja",
    "Pranav", "Priya", "Rahul", "Rajesh", "Rakesh", "Rani", "Rashmi", "Ravi", "Rehan",
    "Rekha", "Ritesh", "Rohan", "Rohini", "Sahil", "Sameer", "Sana", "Sandeep", "Sara",
    "Sarita", "Shalini", "Shreya", "Siddharth", "Simran", "Sneha", "Sofia", "Sonia",
    "Sumit", "Sunil", "Swati", "Tanvi", "Tara", "Thomas", "Uday", "Uma", "Varun",
    "Vedant", "Vidya", "Vikram", "Vimal", "Vinod", "Vishal", "Yash", "Yusuf", "Zara",
]

LAST_NAMES = [
    "Agarwal", "Ahmed", "Bajaj", "Banerjee", "Batra", "Bhagat", "Bhat", "Bhattacharya",
    "Chandra", "Chauhan", "Chawla", "Das", "Desai", "Deshpande", "Fernandes", "Gandhi",
    "Garcia", "Ghosh", "Gill", "Goel", "Gopal", "Gupta", "Hegde", "Iyer", "Jadhav",
    "Jain", "Jha", "Joshi", "Kamath", "Kapoor", "Kaur", "Khan", "Khanna", "Kohli",
    "Krishnan", "Kulkarni", "Kumar", "Lal", "Leone", "Lopez", "Madan", "Malhotra",
    "Mallick", "Mane", "Mehta", "Menon", "Mishra", "Mohanty", "More", "Murthy",
    "Nair", "Nanda", "Narayan", "Nath", "Nayak", "Padmanabhan", "Patel", "Pathak",
    "Patil", "Pillai", "Prasad", "Puri", "Rajan", "Rana", "Rao", "Reddy", "Roy",
    "Saini", "Salvi", "Sarkar", "Saxena", "Sen", "Shah", "Sharma", "Sheikh", "Shetty",
    "Shukla", "Silva", "Singh", "Sinha", "Soni", "Srinivasan", "Sundaram", "Suri",
    "Tiwari", "Tripathi", "Varghese", "Varma", "Vaz", "Verma", "Yadav", "Zachariah",
]

DOMAINS = ["gmail.com", "gmail.com", "gmail.com", "outlook.com", "yahoo.com", "protonmail.com", "icloud.com"]

# Complaints reach a product team through every channel, not just store reviews.
DEFAULT_SOURCES = [
    "app_review", "app_review", "app_review", "support_ticket",
    "support_ticket", "social_media", "email", "survey",
]


def build_rows():
    rows = []
    for topic in PRAISE_TOPICS + FEATURE_TOPICS + PERF_TOPICS + BUG_TOPICS:
        is_feature = topic in FEATURE_TOPICS
        ratings = []
        for rating, count in sorted(topic["ratings"].items(), reverse=True):
            ratings.extend([rating] * count)
        assert len(ratings) == topic["count"], (topic["id"], len(ratings), topic["count"])
        ratings.sort(reverse=True)

        openers = ASK_OPENERS if is_feature else SAFE_OPENERS
        closers = ASK_CLOSERS if is_feature else SAFE_CLOSERS
        spills = [SPILL[k] for k in SPILL_FOR.get(topic["id"], [])]

        for index in range(topic["count"]):
            core = topic["cores"][index % len(topic["cores"])]
            title = topic["titles"][index % len(topic["titles"])]
            opener = openers[(index * 5) % len(openers)]
            closer = closers[(index * 3) % len(closers)]

            parts = [core]
            if spills and index % 3 != 2:
                pool = spills[index % len(spills)]
                parts.append(pool[(index * 2) % len(pool)])
            parts.append(closer)
            if index % 4 == 1:
                parts.insert(0, opener)

            sources = topic.get("sources") or DEFAULT_SOURCES
            rows.append({
                "topic": topic["id"],
                "title": title,
                "content": " ".join(parts),
                "rating": ratings[index],
                "source": sources[index % len(sources)],
            })
    return rows


def attach_people(rows, rng):
    """Mostly distinct customers, with a few repeat complainers - as real exports are."""
    people = []
    used = set()
    while len(people) < 420:
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        key = (first, last)
        if key in used:
            continue
        used.add(key)
        handle = f"{first.lower()}.{last.lower()}"
        handle += str(rng.randint(2, 97)) if rng.random() < 0.45 else ""
        people.append((f"{first} {last}", f"{handle}@{rng.choice(DOMAINS)}"))

    for row in rows:
        if people and rng.random() < 0.82:
            person = people.pop()
        else:
            person = rng.choice(people) if people else ("Guest", "guest@example.com")
        row["customer_name"], row["customer_email"] = person
    return rows


def main():
    rng = random.Random(7)
    rows = build_rows()
    attach_people(rows, rng)
    rng.shuffle(rows)

    # Keep one row per (title, content) pair: a demo file must not look duplicated.
    seen = set()
    unique = []
    for row in rows:
        key = row["content"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "content", "customer_name", "customer_email", "rating", "source"])
        for row in unique:
            writer.writerow([
                row["title"], row["content"], row["customer_name"],
                row["customer_email"], row["rating"], row["source"],
            ])

    print(f"rows written: {len(unique)}")
    print(f"unique customers: {len({r['customer_email'] for r in unique})}")
    print(f"file: {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
