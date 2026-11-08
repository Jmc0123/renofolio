"""Generate a large, realistic test data set (100+ records for every data type).

Usage:
    python scripts/generate_test_data.py                 # writes idp_platform.db (replaces it)
    python scripts/generate_test_data.py --db demo.db --seed 7

Demo logins (password for every generated account: Password123):
    customer@demo.com   Customer
    designer@demo.com   Interior Designer
    admin@demo.com      User Admin
    manager@demo.com    Platform Manager
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from werkzeug.security import generate_password_hash  # noqa: E402

from app.common.clock import TIME_FORMAT  # noqa: E402
from app.common.sample_photos import photo_for_category  # noqa: E402
from app.entity.database import init_db, DatabaseConnection  # noqa: E402

PASSWORD = "Password123"
FIRST = ["Aiden", "Bella", "Chen", "Divya", "Ethan", "Farah", "Grace", "Hui Min", "Isaac", "Jia Hui", "Kumar", "Li Wei",
         "Mei Ling", "Nadia", "Omar", "Priya", "Qi", "Rachel", "Siti", "Tan", "Uma", "Vincent", "Wei Jie", "Xin Yi",
         "Yusuf", "Zara", "Arjun", "Bryan", "Clara", "Daniel"]
LAST = ["Tan", "Lim", "Lee", "Ng", "Wong", "Goh", "Chua", "Ong", "Koh", "Teo", "Rahman", "Kaur", "Singh", "Nair",
        "Fernandez", "Ismail", "Chong", "Low", "Yeo", "Sim"]
STYLES = ["Scandinavian", "Japandi", "Industrial", "Minimalist", "Modern Luxe", "Contemporary", "Mid-Century Modern",
          "Bohemian", "Coastal", "Farmhouse", "Traditional", "Art Deco", "Tropical", "Peranakan", "Wabi-Sabi",
          "Rustic", "Mediterranean", "Hollywood Regency", "Eclectic", "Urban Modern"]
ROOMS = ["Kitchen", "Living Room", "Bedroom", "Bathroom", "Home Office", "Dining Room"]
PLACES = ["HDB 4-Room Flat", "HDB 5-Room Flat", "Condominium", "Executive Maisonette", "Landed Terrace",
          "Semi-Detached House", "Studio Apartment", "Penthouse", "Shophouse", "Cluster House"]
AREAS = ["Tampines", "Punggol", "Bishan", "Jurong East", "Toa Payoh", "Bukit Timah", "Sengkang", "Clementi",
         "Ang Mo Kio", "Queenstown", "Bedok", "Woodlands", "Novena", "Serangoon", "Pasir Ris"]
STUDIO_WORDS = ["Atelier", "Studio", "Design House", "Interiors", "Living", "Spaces", "Works", "Collective"]
STUDIO_NAMES = ["Oak", "Linen", "Terracotta", "Willow", "Slate", "Marble", "Cedar", "Ivory", "Juniper", "Clay",
                "Nordic", "Sora", "Haven", "Ember", "Moss", "Pebble", "Rattan", "Birch", "Saffron", "Lumen"]

DEMO_PROJECT_PREVIEWS = {
    9: (
        "Japandi Dining Room - Condominium, Clementi", "idp-009-japandi-dining.webp",
    ),
    97: (
        "Minimalist Dining Room - HDB 4-Room Flat, Punggol", "idp-097-minimalist-dining.webp",
    ),
    85: (
        "Scandinavian Dining Room - Cluster House, Serangoon", "idp-085-scandinavian-dining.webp",
    ),
    280: (
        "Scandinavian Dining Room - Semi-Detached House, Serangoon", "idp-280-scandinavian-dining.webp",
    ),
    231: (
        "Urban Modern Dining Room - Cluster House, Woodlands", "idp-231-urban-modern-dining.webp",
    ),
    130: (
        "Industrial Dining Room - Penthouse, Bedok", "idp-130-industrial-dining.webp",
    ),
    302: (
        "Coastal Home Office - Condominium, Bishan", "idp-302-coastal-office.webp",
    ),
    106: (
        "Mid-Century Modern Home Office - Studio Apartment, Ang Mo Kio", "idp-106-mid-century-office.webp",
    ),
}


# Assigns dedicated demo previews only when both the project and its existing room image match.
def apply_demo_project_previews(conn):
    updates = [
        (f"/static/sample-projects/{filename}", idp_id, title, photo_for_category(title.partition(" - ")[0]))
        for idp_id, (title, filename) in DEMO_PROJECT_PREVIEWS.items()
    ]
    return conn.executemany(
        "UPDATE interior_design_projects SET photo_url = ? WHERE idp_id = ? AND title = ? AND photo_url = ?",
        updates,
    ).rowcount


# Formats a datetime the way the database stores it.
def ts(moment):
    return moment.strftime(TIME_FORMAT)


# "Peranakan Kitchen" -> "Peranakan kitchen": the style keeps its capitals, the room is a common noun.
def describe_room(style_room):
    room = next(r for r in ROOMS if style_room.endswith(r))
    return f"{style_room[:-len(room)]}{room.lower()}"


# "HDB 4-Room Flat" -> "an HDB 4-room flat", "Condominium" -> "a condominium" (HDB keeps its capitals).
def describe_place(place):
    text = place.lower().replace("hdb", "HDB")
    article = "an" if text.startswith(("HDB", "a", "e", "i", "o", "u")) else "a"
    return f"{article} {text}"


# Builds the whole sample database: profiles, accounts, categories, companies, projects, views and saves.
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("IDP_DB_PATH", "idp_platform.db"))
    parser.add_argument("--seed", type=int, default=314)
    parser.add_argument("--customers", type=int, default=150)
    parser.add_argument("--designers", type=int, default=110)
    parser.add_argument("--projects", type=int, default=320)
    parser.add_argument("--days", type=int, default=120, help="spread activity over the last N days")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    if os.path.exists(args.db):
        os.remove(args.db)
    init_db(args.db)
    db = DatabaseConnection()
    now = datetime.now().replace(microsecond=0)
    start = now - timedelta(days=args.days)
    rand_time = lambda after=start: after + timedelta(seconds=rng.randint(0, max(1, int((now - after).total_seconds()))))
    pw_hash = generate_password_hash(PASSWORD)  # one hash reused: hashing hundreds of passwords is slow
    phone = lambda: rng.choice("689") + "".join(rng.choice("0123456789") for _ in range(7))

    with db.transaction() as conn:
        profile_id = {r[0]: r[1] for r in conn.execute("SELECT role_code, profile_id FROM user_profiles")}

        # ---- user profiles: 4 built-in roles + 96 extra staff roles = 100
        # Each extra profile is based on a staff role (8 November): the account and trust teams work as
        # User Admins, the other teams as Platform Managers.
        teams = ["SUPPORT", "CONTENT", "QUALITY", "FINANCE", "MARKETING", "PARTNER", "TRUST_SAFETY", "DATA"]
        admin_teams = ("SUPPORT", "TRUST_SAFETY")
        custom_profiles = {"USER_ADMIN": [], "PLATFORM_MANAGER": []}
        for i in range(96):
            team = teams[i % len(teams)]
            code = f"{team}_TEAM_{i // len(teams) + 1:02d}"
            base = "USER_ADMIN" if team in admin_teams else "PLATFORM_MANAGER"
            status = "SUSPENDED" if i % 12 == 11 else "ACTIVE"
            created = ts(rand_time())
            new_id = conn.execute(
                "INSERT INTO user_profiles (role_code, role_name, description, base_role, status, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, code.replace("_", " ").title(), f"Staff role for the {team.replace('_', ' ').lower()} team.",
                 base, status, created, created)).lastrowid
            if status == "ACTIVE":
                custom_profiles[base].append(new_id)

        # Inserts one account; profile overrides the built-in profile for staff on a custom team profile.
        def add_account(name, email, role, username=None, created=None, status="ACTIVE", profile=None):
            created = created or ts(rand_time())
            cur = conn.execute(
                "INSERT INTO user_accounts (username, name, email, password_hash, contact_number, profile_id, status, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (username, name, email, pw_hash, phone(), profile or profile_id[role], status, created, created))
            return cur.lastrowid

        # ---- demo accounts with known emails
        early = ts(start - timedelta(days=30))
        demo_customer = add_account("Demo Customer", "customer@demo.com", "CUSTOMER", created=early)
        demo_designer = add_account("Demo Designer", "designer@demo.com", "INTERIOR_DESIGNER", created=early)
        add_account("Demo Admin", "admin@demo.com", "USER_ADMIN", "demo_admin", early)
        add_account("Demo Manager", "manager@demo.com", "PLATFORM_MANAGER", "demo_manager", early)

        # Returns a sample full name for person number i.
        def person(i):
            return f"{FIRST[i % len(FIRST)]} {LAST[(i * 7) % len(LAST)]}"

        customers = [demo_customer] + [
            add_account(person(i), f"customer{i:03d}@example.test", "CUSTOMER",
                        status="SUSPENDED" if i % 40 == 39 else "ACTIVE") for i in range(1, args.customers)]
        designers = [demo_designer] + [
            add_account(person(i + 3), f"designer{i:03d}@example.test", "INTERIOR_DESIGNER",
                        status="SUSPENDED" if i % 50 == 49 else "ACTIVE") for i in range(1, args.designers)]
        # Staff 06-10 use custom team profiles, so the extra profiles have accounts that can log in.
        for i in range(1, 11):
            team_admin = custom_profiles["USER_ADMIN"][i - 6] if i > 5 else None
            team_manager = custom_profiles["PLATFORM_MANAGER"][i - 6] if i > 5 else None
            add_account(person(i + 11), f"admin{i:02d}@example.test", "USER_ADMIN", f"admin{i:02d}", profile=team_admin)
            add_account(person(i + 17), f"manager{i:02d}@example.test", "PLATFORM_MANAGER", f"manager{i:02d}",
                        profile=team_manager)

        # ---- categories: style x room combinations (120)
        category_ids = []
        for style in STYLES:
            for room in ROOMS:
                category_ids.append(conn.execute("INSERT INTO project_categories (name) VALUES (?)",
                                                 (f"{style} {room}",)).lastrowid)
        category_name = {cid: name for cid, name in conn.execute("SELECT category_id, name FROM project_categories")}

        # ---- companies: one per designer (110); contact email and number are required (US23)
        for i, designer_id in enumerate(designers):
            name = f"{STUDIO_NAMES[i % len(STUDIO_NAMES)]} {STUDIO_WORDS[(i * 3) % len(STUDIO_WORDS)]}"
            if i >= len(STUDIO_NAMES):
                name += f" {AREAS[i % len(AREAS)]}"
            created = ts(rand_time())
            slug = name.lower().replace(" ", "")
            conn.execute(
                "INSERT INTO companies (designer_id, company_name, description, address, contact_number, contact_email, "
                "website, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (designer_id, name, f"{name} is a Singapore interior design studio specialising in "
                 f"{rng.choice(STYLES)} and {rng.choice(STYLES)} homes. "
                 f"We have completed over {rng.randint(20, 400)} renovations since {rng.randint(2005, 2022)}.",
                 f"{rng.randint(1, 999)} {AREAS[i % len(AREAS)]} Street {rng.randint(1, 99)}, Singapore",
                 "6" + "".join(rng.choice("0123456789") for _ in range(7)), f"hello@{slug}.example.test",
                 f"https://{slug}.example.test", created, created))

        # ---- interior design projects (320); the demo designer gets 12
        projects = []
        owners = [demo_designer] * 12 + [rng.choice(designers[1:]) for _ in range(args.projects - 12)]
        for owner in owners:
            category_id = rng.choice(category_ids)
            style_room = category_name[category_id]
            place, area = rng.choice(PLACES), rng.choice(AREAS)
            status = rng.choice(["CURRENT", "PAST", "PAST"])
            created_dt = rand_time(start - timedelta(days=60))
            budget = rng.randrange(8000, 180000, 500)
            # Deleting a project now deletes it outright (US30), so no "removed" projects are generated.
            # The random draw is kept so every other generated value stays the same as before.
            _ = ts(rand_time(created_dt)) if rng.random() < 0.03 else None
            removed = None
            idp = conn.execute(
                "INSERT INTO interior_design_projects (designer_id, title, description, category_id, project_status, "
                "budget, photo_url, created_at, updated_at, removed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (owner, f"{style_room} - {place}, {area}",
                 f"A {status.lower()} {describe_room(style_room)} makeover for {describe_place(place)} in {area}. "
                 f"Scope: {rng.choice(['full hacking and rewiring', 'carpentry and lighting', 'flooring and feature walls', 'built-in storage and kitchen cabinets'])}. "
                 f"Timeline about {rng.randint(4, 16)} weeks.",
                 category_id, status, budget, photo_for_category(style_room), ts(created_dt), ts(created_dt), removed)).lastrowid
            projects.append((idp, created_dt))
        apply_demo_project_previews(conn)

        # ---- project views (about 3,000) and favourites (about 700, some removed)
        active_customers = customers[:]
        views = 0
        for idp, created_dt in projects:
            popularity = rng.choice([1, 2, 3, 5, 8, 13, 20])
            for _ in range(rng.randint(0, popularity)):
                viewer = rng.choice(active_customers)
                when = rand_time(max(created_dt, start))
                conn.execute("INSERT INTO project_views (idp_id, customer_id, viewed_at) VALUES (?, ?, ?)",
                             (idp, viewer, ts(when)))
                views += 1
        favourites = 0
        for customer in customers:
            for idp, created_dt in rng.sample(projects, rng.randint(0, 8)):
                saved = rand_time(max(created_dt, start))
                removed = ts(rand_time(saved)) if rng.random() < 0.15 else None
                conn.execute("INSERT INTO favourites (customer_id, idp_id, saved_at, removed_at) VALUES (?, ?, ?, ?)",
                             (customer, idp, ts(saved), removed))
                favourites += 1

    counts = {t: db.scalar(f"SELECT COUNT(*) FROM {t}") for t in
              ("user_profiles", "user_accounts", "companies", "project_categories",
               "interior_design_projects", "project_views", "favourites")}
    print(f"Test data written to {os.path.abspath(args.db)}")
    for table, count in counts.items():
        print(f"  {table:<26}{count:>6}")
    print(f"\nDemo logins (password {PASSWORD}): customer@demo.com, designer@demo.com, admin@demo.com, manager@demo.com")


if __name__ == "__main__":
    main()
