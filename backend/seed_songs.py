"""
Delux Radio — Database Seeding Script
Parses songs_links.csv and songs_links2.csv to upload only unique songs.
Initializes the admin user (admin / Awsedrft@123).
"""
import sys
import os
import csv
import re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, create_tables, Song, AdminUser
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password[:72].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def extract_video_id(url: str):
    if not url:
        return None
    m = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url)
    return m.group(1) if m else None


def parse_song_info(raw_title: str):
    raw_title = raw_title.strip()
    title = raw_title
    artist = 'Bollywood'
    movie = ''

    # Check for (Movie/Album) at the end
    m_movie = re.search(r'\(([^)]+)\)\s*$', raw_title)
    if m_movie:
        movie = m_movie.group(1).strip()
        raw_title = raw_title[:m_movie.start()].strip()

    # Split by – (en dash), — (em dash), or - (hyphen) with spaces
    parts = re.split(r'\s+[–—-]\s+', raw_title)
    if len(parts) >= 2:
        title = parts[0].strip()
        artist = parts[1].strip()
    else:
        # Split on 2 or more consecutive spaces
        parts = re.split(r'\s{2,}', raw_title)
        if len(parts) >= 2:
            title = parts[0].strip()
            artist = parts[1].strip()
        else:
            title = raw_title

    # Clean leading/trailing quotes and spaces
    title = title.strip('\"\' ')
    artist = artist.strip('\"\' ')
    movie = movie.strip('\"\' ')

    return (title or 'Unknown Title')[:250], (artist or 'Bollywood')[:250], movie[:250]


def load_unique_songs_from_csv():
    """Finds and parses songs_links.csv and songs_links2.csv for unique YouTube video IDs."""
    root_dir = Path(__file__).parent.parent
    backend_dir = Path(__file__).parent

    csv_candidates = [
        root_dir / "songs_links.csv",
        root_dir / "songs_links2.csv",
        backend_dir / "songs_links.csv",
        backend_dir / "songs_links2.csv",
    ]

    found_files = []
    seen_paths = set()
    for p in csv_candidates:
        if p.exists() and p.resolve() not in seen_paths:
            found_files.append(p)
            seen_paths.add(p.resolve())

    if not found_files:
        print("[WARN] No CSV song files found.")
        return []

    seen_ids = set()
    unique_songs = []

    for fpath in found_files:
        print(f"[INFO] Reading {fpath.name}...")
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if not row or len(row) < 2:
                        continue
                    raw_title, url = row[0].strip(), row[1].strip()
                    vid = extract_video_id(url)
                    if not vid or vid in seen_ids:
                        continue
                    seen_ids.add(vid)
                    title, artist, movie = parse_song_info(raw_title)
                    unique_songs.append({
                        "title": title,
                        "artist": artist,
                        "movie": movie,
                        "release_year": 1995,
                        "language": "Hindi",
                        "youtube_video_id": vid,
                        "duration": 240,
                        "active": True
                    })
        except Exception as e:
            print(f"[ERROR] Failed reading {fpath}: {e}")

    print(f"[OK] Total unique songs parsed from CSVs: {len(unique_songs)}")
    return unique_songs


def seed(force_reload=False, seed_songs=True):
    create_tables()
    db = SessionLocal()
    try:
        if not seed_songs:
            deleted = db.query(Song).delete()
            db.commit()
            if deleted > 0:
                print(f"[INFO] Empty catalog mode: {deleted} songs removed.")
            else:
                print("[INFO] Empty catalog mode: 0 songs in catalog.")
        else:
            existing_count = db.query(Song).count()

            if force_reload or existing_count == 0:
                if force_reload:
                    deleted = db.query(Song).delete()
                    db.commit()
                    print(f"[INFO] Cleared {deleted} previous songs.")

                songs_to_insert = load_unique_songs_from_csv()
                existing_vids = {s.youtube_video_id for s in db.query(Song.youtube_video_id).all()}

                inserted = 0
                for s in songs_to_insert:
                    if s["youtube_video_id"] not in existing_vids:
                        db.add(Song(**s))
                        existing_vids.add(s["youtube_video_id"])
                        inserted += 1

                if inserted > 0:
                    db.commit()
                    print(f"[OK] Seeded {inserted} unique songs into the catalog.")
                else:
                    print("[INFO] No new songs to add.")
            else:
                print(f"[INFO] Catalog already has {existing_count} songs. Skipping seed.")

        # Create or update default admin (username: admin / password: Awsedrft@123)
        admin_user = db.query(AdminUser).filter(AdminUser.username == "admin").first()
        hashed = hash_password("Awsedrft@123")
        if not admin_user:
            db.add(AdminUser(username="admin", password_hash=hashed))
            db.commit()
            print("[OK] Default admin created  ->  username: admin  |  password: Awsedrft@123")
        else:
            admin_user.password_hash = hashed
            db.commit()
            print("[INFO] Admin user updated  ->  username: admin  |  password: Awsedrft@123")

    finally:
        db.close()


if __name__ == "__main__":
    force = "--reload" in sys.argv or "--force" in sys.argv
    no_seed = "--no-seed" in sys.argv or "--empty" in sys.argv
    seed(force_reload=force, seed_songs=not no_seed)

