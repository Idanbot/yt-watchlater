# /// script
# requires-python = ">=3.11"
# dependencies = ["polars>=1.0"]
# ///
"""Parse watch-later JSONL + raw playlist HTML; emit ingest dataset and insights."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import polars as pl
ROOT = Path(__file__).resolve().parent
JSONL = ROOT / "youtube_watch_later_categorized.jsonl"
HTML = ROOT / "raw-html-body.txt"
TRIAGE = ROOT / "youtube_watch_later_triage.jsonl"
OUT = ROOT / "out"

VIDEO_BLOCK_RE = re.compile(r"<ytd-playlist-video-renderer\b")
WATCH_V_RE = re.compile(r"/watch\?v=([A-Za-z0-9_-]{11})")
INDEX_RE = re.compile(
    r'<yt-formatted-string id="index"[^>]*>\s*(\d+)\s*</yt-formatted-string>'
)
T_SEC_RE = re.compile(r"(?:&amp;|&)t=(\d+)s")
VIDEO_INFO_RE = re.compile(
    r'<yt-formatted-string id="video-info"[^>]*>(.*?)</yt-formatted-string>',
    re.S,
)
SPAN_RE = re.compile(r"<span[^>]*>([^<]*)</span>")
HANDLE_RE = re.compile(
    r'id="channel-name"[\s\S]{0,2500}?<a class="yt-simple-endpoint style-scope yt-formatted-string"[^>]*href="(/@[A-Za-z0-9._-]+)"'
)
CHANNEL_TITLE_RE = re.compile(
    r'<yt-formatted-string id="text"[^>]*title="([^"]*)"[^>]*ytd-channel-name'
)
JSON_VID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
HEBREW_RE = re.compile(r"[\u0590-\u05FF]")


def parse_duration_seconds(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.strip().split(":")
    if not parts or any(not p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 1:
        return nums[0]
    return None


def parse_views(text: str | None) -> int | None:
    if not text:
        return None
    raw = text.strip().lower().replace(",", "")
    raw = raw.replace(" views", "").replace(" view", "").strip()
    if raw in {"no", "no views"}:
        return 0
    mult = 1.0
    if raw.endswith("k"):
        mult = 1_000.0
        raw = raw[:-1]
    elif raw.endswith("m"):
        mult = 1_000_000.0
        raw = raw[:-1]
    elif raw.endswith("b"):
        mult = 1_000_000_000.0
        raw = raw[:-1]
    try:
        return int(float(raw) * mult)
    except ValueError:
        return None


def duration_bucket(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return "<1m"
    if seconds < 5 * 60:
        return "1-5m"
    if seconds < 12 * 60:
        return "5-12m"
    if seconds < 20 * 60:
        return "12-20m"
    if seconds < 40 * 60:
        return "20-40m"
    if seconds < 60 * 60:
        return "40-60m"
    if seconds < 2 * 3600:
        return "1-2h"
    return "2h+"


CHANNEL_CAT: dict[str, tuple[str, str]] = {
    "3Blue1Brown": ("Science & Education", "Mathematics"),
    "Veritasium": ("Science & Education", "Science"),
    "Kurzgesagt – In a Nutshell": ("Science & Education", "Science"),
    "SciShow": ("Science & Education", "Science"),
    "StarTalk": ("Science & Education", "Science"),
    "Real Engineering": ("Science & Education", "Science"),
    "Kyle Hill": ("Science & Education", "Science"),
    "Ridddle": ("Science & Education", "Science"),
    "Insane Curiosity": ("Science & Education", "Science"),
    "Thoughty2": ("Science & Education", "Science"),
    "Primer": ("Science & Education", "Science"),
    "Welch Labs": ("Science & Education", "Mathematics"),
    "Zach Star": ("Science & Education", "Mathematics"),
    "Reducible": ("Science & Education", "Mathematics"),
    "Spanning Tree": ("Science & Education", "Mathematics"),
    "Nemean": ("Science & Education", "Mathematics"),
    "The Stickman Scientist": ("Science & Education", "Science"),
    "Rational Animations": ("Science & Education", "Science"),
    "The Nature of Things": ("Science & Education", "Science"),
    "Covert Cabal": ("Science & Education", "Science"),
    "Sideprojects": ("Science & Education", "Science"),
    "Around The World Explained": ("Science & Education", "Education"),
    "The Paint Explainer": ("Science & Education", "Education"),
    "TED": ("Science & Education", "Education"),
    "Two Minute Papers": ("AI", "Models & Coding Agents"),
    "Feynman Archives": ("Science & Education", "Physics"),
    "TehPhysicalist": ("Science & Education", "Physics"),
    "Let's Get Rusty": ("Programming", "Rust"),
    "fasterthanlime": ("Programming", "Rust"),
    "Hussein Nasser": ("Programming", "APIs & Backend"),
    "ByteByteGo": ("Programming", "System Design"),
    "Abdul Bari": ("Programming", "Algorithms & Data Structures"),
    "WilliamFiset": ("Programming", "Algorithms & Data Structures"),
    "Colin Galen": ("Programming", "Algorithms & Data Structures"),
    "Clément Mihailescu": ("Programming", "Algorithms & Data Structures"),
    "Soof Golan": ("Programming", "Algorithms & Data Structures"),
    "Hello, my name is nim": ("Programming", "Algorithms & Data Structures"),
    "The Cherno": ("Programming", "C / C++"),
    "Jacob Sorber": ("Programming", "C / C++"),
    "Core Dumped": ("Programming", "C / C++"),
    "Eskil Steenberg": ("Programming", "C / C++"),
    "Molly Rocket": ("Programming", "C / C++"),
    "Creel": ("Programming", "C / C++"),
    "Anthony GG": ("Programming", "Go"),
    "Telusko": ("Programming", "Java"),
    "Laur Spilca": ("Programming", "Java"),
    "Dive Into Development": ("Programming", "Java"),
    "in28minutes": ("Programming", "Java"),
    "Sebastian Daschner": ("Programming", "Java"),
    "Devoxx": ("Programming", "Java"),
    "Ben Awad": ("Programming", "JavaScript / TypeScript"),
    "JSConf": ("Programming", "JavaScript / TypeScript"),
    "Beyond Fireship": ("Programming", "Web Development"),
    "Traversy Media": ("Programming", "Web Development"),
    "Lama Dev": ("Programming", "Web Development"),
    "TomDoesTech": ("Programming", "APIs & Backend"),
    "0x4rk0": ("Programming", "APIs & Backend"),
    "Directus": ("Programming", "APIs & Backend"),
    "Olly Rosewell": ("Programming", "APIs & Backend"),
    "Bernhard Wenzel Training": ("Programming", "APIs & Backend"),
    "Jakob Jenkov": ("Programming", "Software Engineering"),
    "The Pragmatic Engineer": ("Programming", "Software Engineering"),
    "A Life Engineered": ("Programming", "Software Engineering"),
    "A Life Engineered and The Pragmatic Engineer": ("Programming", "Software Engineering"),
    "Engineering with Utsav": ("Programming", "Software Engineering"),
    "LearnThatStack": ("Programming", "Software Engineering"),
    "Pull Request": ("Programming", "Software Engineering"),
    "Reversim": ("Programming", "Software Engineering"),
    "Chris Titus Tech": ("Programming", "Software Engineering"),
    "Canopy Games": ("Programming", "Programming General"),
    "Tsoding": ("Programming", "Programming General"),
    "Tsoding Daily": ("Programming", "Programming General"),
    "ThePrimeagenHighlights": ("Programming", "Programming General"),
    "Sourcegraph": ("Programming", "Programming General"),
    "ForrestKnight": ("Programming", "Programming General"),
    "Kyle Cook from Web Dev Simplified": ("Programming", "Programming General"),
    "Boot dev": ("Programming", "Programming General"),
    "Awesome": ("Programming", "Programming General"),
    "Nextcore": ("Programming", "Programming General"),
    "Dorian Develops": ("Career & Productivity", "Work & Career"),
    "Joma Tech": ("Career & Productivity", "Work & Career"),
    "TechLead": ("Career & Productivity", "Work & Career"),
    "Simple Programmer": ("Career & Productivity", "Work & Career"),
    "Andy Sterkowitz": ("Career & Productivity", "Work & Career"),
    "The Serious CTO": ("Career & Productivity", "Work & Career"),
    "Matt C Smith": ("Career & Productivity", "Work & Career"),
    "Millionaire Millennial": ("Career & Productivity", "Work & Career"),
    "Tina Huang": ("Career & Productivity", "Learning"),
    "Studying With Alex": ("Career & Productivity", "Learning"),
    "typecraft": ("Programming", "Editors & Tooling"),
    "Vimothee": ("Programming", "Editors & Tooling"),
    "TJ DeVries": ("Programming", "Editors & Tooling"),
    "Josean Martinez": ("Programming", "Editors & Tooling"),
    "TheVimeagen": ("Programming", "Editors & Tooling"),
    "Traap": ("Programming", "Editors & Tooling"),
    "Elijah Manor": ("Programming", "Editors & Tooling"),
    "chris@machine": ("Programming", "Editors & Tooling"),
    "Jess Archer": ("Programming", "Editors & Tooling"),
    "thoughtbot": ("Programming", "Editors & Tooling"),
    "TheAltF4Stream": ("Programming", "Editors & Tooling"),
    "HerdingBits": ("Programming", "Editors & Tooling"),
    "Theory of Everything": ("Programming", "Editors & Tooling"),
    "MAKC": ("Programming", "Editors & Tooling"),
    "Dong Zhou": ("Programming", "Editors & Tooling"),
    "Axlefublr (she\\they)": ("Programming", "Editors & Tooling"),
    "DevOnDuty": ("Programming", "Editors & Tooling"),
    "devaslife": ("Programming", "Editors & Tooling"),
    "Jake Wiesler": ("Programming", "Editors & Tooling"),
    "linkarzu": ("Programming", "Editors & Tooling"),
    "linkarzu and 2 more": ("Programming", "Editors & Tooling"),
    "System Crafters": ("Programming", "Editors & Tooling"),
    "Marco Peluso": ("Programming", "Editors & Tooling"),
    "DistroTube": ("DevOps & Cloud", "Linux & Shell"),
    "Luke Smith": ("DevOps & Cloud", "Linux & Shell"),
    "Mischa van den Burg": ("DevOps & Cloud", "Linux & Shell"),
    "Sol Does Tech": ("DevOps & Cloud", "Linux & Shell"),
    "Just me and Opensource": ("DevOps & Cloud", "Linux & Shell"),
    "NetworkChuck": ("DevOps & Cloud", "Linux & Shell"),
    "Perion Network": ("Programming", "Databases"),
    "Dojo Tech": ("Programming", "Databases"),
    "Giraffe Academy": ("Programming", "Programming General"),
    "Sebastian Lague": ("Programming", "Programming General"),
    "strager": ("Programming", "Programming General"),
    "Internet of Bugs": ("Programming", "Programming General"),
    "MeshPit": ("Programming", "C / C++"),
    "Nathan Baggs": ("Programming", "Programming General"),
    "Bitwise": ("Programming", "Programming General"),
    "Soon": ("Programming", "Programming General"),
    "Learn Fast Make Things": ("Programming", "Programming General"),
    "Nir Lichtman": ("Programming", "Programming General"),
    "Tech With Nikola": ("Programming", "Programming General"),
    "Tech With Soleyman": ("Programming", "Programming General"),
    "Developete": ("Programming", "Programming General"),
    "Adib Hanna": ("Programming", "Programming General"),
    "Quazi Johir": ("Psychology & Philosophy", "Self Improvement"),
    "PinkDraconian": ("Cybersecurity", "Malware & Reverse Engineering"),
    "InsiderPhD": ("Cybersecurity", "Ethical Hacking"),
    "Intigriti": ("Cybersecurity", "Ethical Hacking"),
    "crow": ("Cybersecurity", "Ethical Hacking"),
    "SecAura": ("Cybersecurity", "Ethical Hacking"),
    "Default sec": ("Cybersecurity", "Ethical Hacking"),
    "The Dark Needle": ("Cybersecurity", "Ethical Hacking"),
    "Gbay99": ("Cybersecurity", "Ethical Hacking"),
    "NoMagic": ("Cybersecurity", "Ethical Hacking"),
    "Black Hat": ("Cybersecurity", "Security Engineering"),
    "Hallden": ("Cybersecurity", "OSINT & Privacy"),
    "The Hated One": ("Cybersecurity", "OSINT & Privacy"),
    "Techlore": ("Cybersecurity", "OSINT & Privacy"),
    "Loi Liang Yang": ("Cybersecurity", "OSINT & Privacy"),
    "FujiLabs528": ("Cybersecurity", "Ethical Hacking"),
    "DJ Ware": ("Cybersecurity", "Security Engineering"),
    "Jack Rhysider": ("Cybersecurity", "Ethical Hacking"),
    "Wendover Productions": ("Cybersecurity", "Network Security"),
    "stuffy24": ("Cybersecurity", "OSINT & Privacy"),
    "TAUVOD": ("Cybersecurity", "Security Engineering"),
    "מכללת פרקטיקיו - קורסי תכנות / סייבר / ניהול רשת": ("Cybersecurity", "Ethical Hacking"),
    "אבי סביליה - מדריך סייבר": ("Cybersecurity", "Ethical Hacking"),
    "Hanging Pawns": ("Gaming", "Chess"),
    "Chess Vibes": ("Gaming", "Chess"),
    "ChessPage1": ("Gaming", "Chess"),
    "Chess Thugs": ("Gaming", "Chess"),
    "GothamChess": ("Gaming", "Chess"),
    "Daniel Naroditsky": ("Gaming", "Chess"),
    "Remote Chess Academy": ("Gaming", "Chess"),
    "mortal chess": ("Gaming", "Chess"),
    "TheBackyardProfessor": ("Gaming", "Chess"),
    "Lord Ravenscraft": ("Gaming", "Chess"),
    "Game Maker's Toolkit": ("Gaming", "Games"),
    "RamenStyle": ("Gaming", "Games"),
    "DevGAMM": ("Gaming", "Games"),
    "PewDiePie": ("Gaming", "Games"),
    "Flashback MMA": ("Health & Fitness", "Fitness"),
    "3Blue1Brown": ("Science & Education", "Mathematics"),
    "Andrew Huberman": ("Health & Fitness", "Medicine & Biology"),
    "Huberman Lab Clips": ("Health & Fitness", "Medicine & Biology"),
    "Seth Capehart MD": ("Health & Fitness", "Medicine & Biology"),
    "Darren Chai, MD": ("Health & Fitness", "Medicine & Biology"),
    "DoctorJonGo": ("Health & Fitness", "Medicine & Biology"),
    "Ben Azadi": ("Health & Fitness", "Nutrition"),
    "Cembryfit": ("Health & Fitness", "Fitness"),
    "Levy's Fit (LBSEP)": ("Health & Fitness", "Fitness"),
    "Exercise4CheatMeals": ("Health & Fitness", "Nutrition"),
    "Strength Side and The Kneesovertoesguy": ("Health & Fitness", "Fitness"),
    "Karate TV": ("Health & Fitness", "Fitness"),
    "Nsima Inyang": ("Health & Fitness", "Fitness"),
    "Mark Bell's Power Project": ("Health & Fitness", "Fitness"),
    "Noel Deyzel": ("Health & Fitness", "Fitness"),
    "Maurice Moves": ("Health & Fitness", "Fitness"),
    "Haebyung Dance": ("Health & Fitness", "Fitness"),
    "דניאל דושי": ("Health & Fitness", "Medicine & Biology"),
    "ד״ר זיו אב": ("Health & Fitness", "Medicine & Biology"),
    "RESPIRE": ("Health & Fitness", "Mental Health"),
    "BeerBiceps": ("Health & Fitness", "Mental Health"),
    "Clark Kegley": ("Psychology & Philosophy", "Self Improvement"),
    "Improvement Pill": ("Psychology & Philosophy", "Self Improvement"),
    "The Art of Improvement": ("Psychology & Philosophy", "Self Improvement"),
    "Be Inspired": ("Psychology & Philosophy", "Self Improvement"),
    "Be Inspired | STUDIO": ("Psychology & Philosophy", "Self Improvement"),
    "Better Than Yesterday": ("Psychology & Philosophy", "Self Improvement"),
    "Stellar Thoughts": ("Psychology & Philosophy", "Self Improvement"),
    "Fuel The Mind": ("Psychology & Philosophy", "Self Improvement"),
    "BetterU": ("Psychology & Philosophy", "Self Improvement"),
    "One Percent Better": ("Psychology & Philosophy", "Self Improvement"),
    "LITTLE BIT BETTER": ("Psychology & Philosophy", "Self Improvement"),
    "easy, actually": ("Psychology & Philosophy", "Self Improvement"),
    "Better Ideas": ("Psychology & Philosophy", "Self Improvement"),
    "Freedom in Thought": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Academy of Ideas": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "After Skool": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Einzelgänger": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Unsolicited advice": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Ayn Rand Institute": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Michael Sugrue": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Psyphoria": ("Psychology & Philosophy", "Psychology"),
    "PsycheDepth": ("Psychology & Philosophy", "Psychology"),
    "PsycheCore": ("Psychology & Philosophy", "Psychology"),
    "Jung Thoughts": ("Psychology & Philosophy", "Psychology"),
    "Newel of Knowledge": ("Psychology & Philosophy", "Self Improvement"),
    "Kaal Raam": ("Psychology & Philosophy", "Self Improvement"),
    "Be Invictus": ("Psychology & Philosophy", "Self Improvement"),
    "Outperform | Marvin Payne": ("Psychology & Philosophy", "Self Improvement"),
    "Iman Gadzhi": ("Career & Productivity", "Productivity"),
    "Dan Martell": ("Career & Productivity", "Productivity"),
    "Joanna Wiebe": ("Career & Productivity", "Productivity"),
    "Thomas Frank Explains": ("Career & Productivity", "Productivity"),
    "ParkNotes": ("Career & Productivity", "Productivity"),
    "Intermittent Diversion": ("Career & Productivity", "Productivity"),
    "Charles Duhigg": ("Career & Productivity", "Productivity"),
    "Tim Ferriss": ("Career & Productivity", "Productivity"),
    "The Art of Living Free": ("Psychology & Philosophy", "Self Improvement"),
    "David Schlais": ("Psychology & Philosophy", "Self Improvement"),
    "Chill Dude Explains": ("Career & Productivity", "Learning"),
    "Stephen Petro": ("Career & Productivity", "Learning"),
    "MyNonLeatherLife": ("Psychology & Philosophy", "Relationships"),
    "The Happy Wife School": ("Psychology & Philosophy", "Relationships"),
    "Casey Zander": ("Psychology & Philosophy", "Relationships"),
    "Bulldog Mindset": ("Psychology & Philosophy", "Relationships"),
    "Traditional Values": ("Psychology & Philosophy", "Relationships"),
    "high value male": ("Psychology & Philosophy", "Relationships"),
    "The Unplugged Alpha": ("Psychology & Philosophy", "Relationships"),
    "The Alpha Path": ("Psychology & Philosophy", "Relationships"),
    "Make Them Pay!": ("Psychology & Philosophy", "Relationships"),
    "Robert Geronimo": ("Psychology & Philosophy", "Relationships"),
    "Oliver Cowlishaw": ("Psychology & Philosophy", "Relationships"),
    "More Charisma on Command": ("Psychology & Philosophy", "Relationships"),
    "Henry Grey Earls": ("Psychology & Philosophy", "Relationships"),
    "Craig Perry": ("Psychology & Philosophy", "Relationships"),
    "תקשורת אמיתית - הצלחה עם נשים": ("Psychology & Philosophy", "Relationships"),
    "Social Freedom": ("Psychology & Philosophy", "Relationships"),
    "Captain Sinbad": ("Psychology & Philosophy", "Relationships"),
    "CalveŽilla": ("Psychology & Philosophy", "Relationships"),
    "Older Brother": ("Psychology & Philosophy", "Relationships"),
    "WISE JOE": ("Psychology & Philosophy", "Relationships"),
    "Orion Taraban": ("Psychology & Philosophy", "Relationships"),
    "Data Male": ("Psychology & Philosophy", "Relationships"),
    "Shoe0nHead": ("Entertainment", "Comedy & Commentary"),
    "Moon": ("Politics & Society", "Society & Culture"),
    "Asmongold Clips": ("Entertainment", "Comedy & Commentary"),
    "The Babylon Bee": ("Entertainment", "Comedy & Commentary"),
    "PewDiePie": ("Entertainment", "Comedy & Commentary"),
    "exurb2a": ("Entertainment", "Comedy & Commentary"),
    "FLAGRANT CLIPS": ("Entertainment", "Comedy & Commentary"),
    "JRE Clips": ("Entertainment", "Comedy & Commentary"),
    "Daily Dose of JRE": ("Entertainment", "Comedy & Commentary"),
    "Shawn Ryan Show": ("Entertainment", "Comedy & Commentary"),
    "Plotberg": ("Entertainment", "Movies & TV"),
    "Quinn's Ideas": ("Entertainment", "Movies & TV"),
    "Mr. Robot": ("Entertainment", "Movies & TV"),
    "KEXP": ("Entertainment", "Music"),
    "גדי טאוב: שומר סף": ("Politics & Society", "Israel"),
    "חדשות 13": ("Politics & Society", "Israel"),
    "TOV אקטואליה יהודית": ("Politics & Society", "Israel"),
    "כאן 11 - תאגיד השידור הישראלי": ("Politics & Society", "Israel"),
    "כאן | חדשות - תאגיד השידור הישראלי": ("Politics & Society", "Israel"),
    "i24NEWS עברית": ("Politics & Society", "Israel"),
    "ynet": ("Politics & Society", "Israel"),
    "TheMarker Online": ("Politics & Society", "Israel"),
    "John Smith": ("Politics & Society", "Israel"),
    "Moshe Fabrikant": ("Politics & Society", "Israel"),
    "מחוברים בגבעה": ("Politics & Society", "Israel"),
    "הדרך הקלה": ("Politics & Society", "Israel"),
    "לאומנות": ("Politics & Society", "Israel"),
    "גיאו-פוליטיקה - זיו רפפורט": ("Politics & Society", "Geopolitics"),
    "אבי זלינגר חדשות 1 אבי זלינגר": ("Politics & Society", "Israel"),
    "אלעד שאול - עורך דין": ("Politics & Society", "Israel"),
    "סטג'ר - הערוץ הרשמי": ("Politics & Society", "Israel"),
    "פודקאסט על המשמעות - תמיר דורטל": ("Politics & Society", "Israel"),
    "Fox News": ("Politics & Society", "Society & Culture"),
    "PragerU": ("Politics & Society", "Political Theory"),
    "Destiny": ("Politics & Society", "Society & Culture"),
    "Elephants in Rooms - Ken LaCorte": ("Politics & Society", "Society & Culture"),
    "LegalEagle": ("Politics & Society", "Society & Culture"),
    "The Wall Street Journal": ("Politics & Society", "Society & Culture"),
    "Elex Michaelson": ("Politics & Society", "Society & Culture"),
    "Bloodlines & Borders": ("Politics & Society", "Geopolitics"),
    "American Afterimage": ("Politics & Society", "Society & Culture"),
    "Forward Observations": ("Politics & Society", "Geopolitics"),
    "Living Ironically in Europe": ("Politics & Society", "Society & Culture"),
    "Nate The Lawyer": ("Politics & Society", "Society & Culture"),
    "Kings and Generals": ("Science & Education", "History"),
    "Unknown Frequencies": ("Science & Education", "History"),
    "Serious History": ("Science & Education", "History"),
    "Into the Shadows": ("Science & Education", "History"),
    "The Fat Electrician": ("Science & Education", "History"),
    "Forgotten Weapons": ("Science & Education", "History"),
    "Pax Tube": ("Science & Education", "History"),
    "Godburn": ("Science & Education", "History"),
    "Joseph Everett - WIL": ("Science & Education", "History"),
    "Joseph Everett": ("Science & Education", "History"),
    "Mark Tilbury": ("Business & Finance", "Personal Finance"),
    "Codie Sanchez": ("Business & Finance", "Entrepreneurship"),
    "Naval": ("Business & Finance", "Entrepreneurship"),
    "Valuetainment": ("Business & Finance", "Entrepreneurship"),
    "My First Million": ("Business & Finance", "Entrepreneurship"),
    "Simon Squibb": ("Business & Finance", "Entrepreneurship"),
    "Leila Hormozi": ("Business & Finance", "Entrepreneurship"),
    "Dan Koe": ("Business & Finance", "Entrepreneurship"),
    "Iman Gadzhi": ("Career & Productivity", "Productivity"),
    "Linus Tech Tips": ("Technology", "PC Hardware"),
    "Dawid Does Tech Stuff": ("Technology", "PC Hardware"),
    "This Does Not Compute": ("Technology", "PC Hardware"),
    "MONOCHROME": ("Technology", "PC Hardware"),
    "ExplainingComputers": ("Technology", "PC Hardware"),
    "Sebi's Random Tech": ("Technology", "PC Hardware"),
    "TechnicallyAlex": ("Technology", "Phones & Mobile"),
    "techless": ("Technology", "PC Hardware"),
    "The Serial Port": ("Technology", "Electronics"),
    "Watchfinder & Co.": ("Lifestyle", "Watches"),
    "Analog Watch Club": ("Lifestyle", "Watches"),
    "The 1010 Watch Club": ("Lifestyle", "Watches"),
    "Just the Watch": ("Lifestyle", "Watches"),
    "Welcome to the Watchmosphere": ("Lifestyle", "Watches"),
    "Binging with Babish": ("Lifestyle", "Food & Coffee"),
    "Clay Hayes": ("Lifestyle", "Travel"),
    "TheUrbanPrepper": ("Lifestyle", "Travel"),
    "Garand Thumb": ("Lifestyle", "Travel"),
    "Big Think": ("Science & Education", "Education"),
    "Big Think and Big Think Clips": ("Science & Education", "Education"),
    "Big Think and 2 more": ("Science & Education", "Education"),
    "Big Think and Tiago Forte": ("Career & Productivity", "Productivity"),
    "Big Think and Yuval Noah Harari": ("Science & Education", "Education"),
    "The Diary Of A CEO": ("Career & Productivity", "Work & Career"),
    "The Diary Of A CEO and We Need To Talk": ("Psychology & Philosophy", "Relationships"),
    "Lex Fridman": ("Science & Education", "Science"),
    "AI News & Strategy Daily | Nate B Jones": ("AI", "LLMs"),
    "David Ondrej": ("AI", "Local LLMs"),
    "Species | Documenting AGI": ("AI", "LLMs"),
    "b2studios": ("AI", "Agents & Automation"),
    "Eero Alvar": ("AI", "Agents & Automation"),
    "YBCTooCold": ("Entertainment", "Comedy & Commentary"),
    "Chase Hughes": ("Psychology & Philosophy", "Psychology"),
    "Beo Beo": ("Entertainment", "Comedy & Commentary"),
    "Nikos Sotirakopoulos": ("Politics & Society", "Political Theory"),
    "Joseph D. Warren": ("Psychology & Philosophy", "Self Improvement"),
    "Anthony Vicino": ("Career & Productivity", "Productivity"),
    "The Arrow": ("Psychology & Philosophy", "Self Improvement"),
    "MindFlow": ("Psychology & Philosophy", "Self Improvement"),
    "Brofessor Stein": ("Psychology & Philosophy", "Self Improvement"),
    "Stefanovic": ("Career & Productivity", "Work & Career"),
    "Apex Aura": ("Psychology & Philosophy", "Self Improvement"),
    "Gerbert Johnson": ("Psychology & Philosophy", "Relationships"),
    "ICT Archivist": ("Psychology & Philosophy", "Relationships"),
    "Jesse Enkamp": ("Health & Fitness", "Fitness"),
    "Jocko Podcast": ("Psychology & Philosophy", "Self Improvement"),
    "Echelon Front": ("Psychology & Philosophy", "Self Improvement"),
    "Huberman Lab Clips and The Prof G Pod – Scott Galloway": ("Psychology & Philosophy", "Psychology"),
    "The Diary Of A CEO and Dr. Pradip Jamnadas, MD": ("Health & Fitness", "Medicine & Biology"),
    "The Diary Of A CEO and Natalie Dawson": ("Psychology & Philosophy", "Relationships"),
    "The Diary Of A CEO and Chris Koerner on The Koerner Office Podcast": ("Career & Productivity", "Work & Career"),
    "The Diary Of A CEO and The Roman Forum with Roman Yampolskiy": ("AI", "LLMs"),
    "מר שיבולת Tech": ("Technology", "Tech News & Commentary"),
    "סלע מאיר - ספריית שיבולת": ("Politics & Society", "Israel"),
    "אורי ישראלי": ("Psychology & Philosophy", "Stoicism & Philosophy"),
    "Tamir Mandowsky": ("Career & Productivity", "Work & Career"),
    "Lattice": ("Career & Productivity", "Work & Career"),
    "Awesome": ("Programming", "Programming General"),
}

_TITLE_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(p, re.I), cat, sub)
    for p, cat, sub in [
        (r"\[private video\]", "Unavailable", "Private"),
        (r"\[deleted video\]", "Unavailable", "Deleted"),
        (r"\[unavailable video\]", "Unavailable", "Unavailable"),
        (r"\b(neovim|nvim|lazyvim|harpoon|vimtutor|vimtutor)\b", "Programming", "Editors & Tooling"),
        (r"\b(tmux|vim\b|emacs|vscode|vs code|intellij)\b", "Programming", "Editors & Tooling"),
        (r"\b(buffer overflow|reverse shell|metasploit|bug bounty|pegasus|osint|wireshark|nmap|payloads?|exploit|pentest|ethical hacking|cybersecurity|סייבר|הצפנה)\b", "Cybersecurity", "Ethical Hacking"),
        (r"\b(jwt|oauth|tls|https?|websocket|postman|graphql|rest api|micro-?services?)\b", "Programming", "APIs & Backend"),
        (r"\b(kubernetes|k8s|docker|terraform|ansible|ci/?cd|blue green)\b", "DevOps & Cloud", "Cloud & Infrastructure"),
        (r"\b(linux|ubuntu|arch(linux)?|hyprland|distro|ssh|dotfiles|xrdp)\b", "DevOps & Cloud", "Linux & Shell"),
        (r"\b(kafka|rabbitmq|sqs|event-driven)\b", "Programming", "System Design"),
        (r"\b(hash tables?|linked lists?|binary search|quick sort|merge sort|bubble sort|selection sort|insertion sort|linear search|interpolation search|tree traversal|graph theory|recursion|dynamic arrays?|avl tree|backtracking|divide and conquer|pigeonhole|fourier|laplace|convolution|fft|hashmaps?|dictionaries)\b", "Programming", "Algorithms & Data Structures"),
        (r"\b(design pattern|solid|single responsibility|observer pattern|strategy pattern|system design|cognitive load|monorepo)\b", "Programming", "Software Engineering"),
        (r"\b(spring boot|spring security|junit|mockito|hibernate)\b", "Programming", "Java"),
        (r"\b(\brust\b|golang|\bgo pointers|\bgo concurrency|\bgo routines)\b", "Programming", "Programming General"),
        (r"\b(react|redux|typescript|javascript|js generators|callbacks? and promises|regular expressions?|\bregex\b)\b", "Programming", "React / Frontend"),
        (r"\b(c\+\+|transistor|assembly|pwn|teaching myself c)\b", "Programming", "C / C++"),
        (r"\b(python|django|fastapi)\b", "Programming", "Python"),
        (r"\b(sql|postgres|elasticsearch|rdbms|בסיסי נתונים)\b", "Programming", "Databases"),
        (r"\b(haskell|monads?|type theory|virtual memory|semaphore|sockets?)\b", "Programming", "Programming General"),
        (r"\b(programmer|software engineers?|software development|tech jobs?|in tech|cse projects|god programmer)\b", "Programming", "Programming General"),
        (r"\b(llm|chatgpt|openai|claude|gemini|coding agent|local (ai|llm)|ollama|ai trading|n8n|private ai)\b", "AI", "LLMs"),
        (r"\bchess\b|סיציליאן|kakashi|jiraiya|jutsu", "Gaming", "Chess"),
        (r"\b(neovim|vim)\b", "Programming", "Editors & Tooling"),
        (r"\b(testosterone|ozempic|creatine|huberman|sleep|diet|calorie|workout|fitness|push.?ups|cortisol|calisthenics|mewing|visceral fat)\b", "Health & Fitness", "Fitness"),
        (r"\b(procrastinat|self-sabotage|willpower|meditation|stoic|jung|charisma|assertiveness|self-talk|self-doubt|psycho-cybernetics|mind traps|mental models|plato|machiavelli)\b", "Psychology & Philosophy", "Self Improvement"),
        (r"\b(women|female|dating|girlfriend|masculinity|red flags|friendzone|orgasm|porn|nofap|wives|seduce|feminists)\b", "Psychology & Philosophy", "Relationships"),
        (r"חדשות|צהל|צה\"ל|איראן|עזה|הרמטכ|בחירות|דמוקרט", "Politics & Society", "Israel"),
        (r"\b(israel|gaza|iran|geopolitic|hamas|epstein|mossad|oct 7)\b", "Politics & Society", "Geopolitics"),
        (r"\b(fourier|partial differential|normal distribution|group theory|matrices|hamming|godel|euler's totient)\b", "Science & Education", "Mathematics"),
        (r"\b(nuclear|quantum|fusion|physics|feynman|transistor|steels and heat)\b", "Science & Education", "Physics"),
        (r"\b(history|documentary|odyssey|siege of|ww2|revolt|ancient civilization|auschwitz)\b", "Science & Education", "History"),
        (r"\b(layoffs?|salary|cto|software engineer career|learn to code|tech jobs|get into tech|hiring in)\b", "Career & Productivity", "Work & Career"),
        (r"\b(invest|get rich|personal finance|money|millionaire|finances|levels of wealth)\b", "Business & Finance", "Personal Finance"),
        (r"\b(thinkpad|laptop|keyboard|monitor|pc build|hardware|meshtastic|drone review|built my own phone)\b", "Technology", "PC Hardware"),
        (r"\b(watch collecting|watchmaking|seiko|rolex)\b", "Lifestyle", "Watches"),
        (r"\b(cka exam|kubernetes)\b", "DevOps & Cloud", "Kubernetes"),
        (r"\b(gimp|photoshop)\b", "Technology", "Electronics"),
    ]
]


def recategorize(title: str, channel: str, category: str, sub_category: str) -> tuple[str, str]:
    if category != "Other":
        return category, sub_category
    t = title or ""
    ch = channel or ""
    low = t.strip().lower()
    if low == "[private video]":
        return "Unavailable", "Private"
    if low == "[deleted video]":
        return "Unavailable", "Deleted"
    if low == "[unavailable video]":
        return "Unavailable", "Unavailable"
    mapped = CHANNEL_CAT.get(ch)
    if mapped:
        return mapped
    blob = f"{ch} {t}"
    for rx, cat, sub in _TITLE_RULES:
        if rx.search(blob):
            return cat, sub
    if HEBREW_RE.search(blob):
        if re.search(r"קורס|ריאקט|redux|פיתון|ג'אווה|תכנות|קוד", blob):
            return "Programming", "Programming General"
        return "Politics & Society", "Israel"
    if re.search(r"\b(programmer|software|coder|coding|dev\b|in tech)\b", blob, re.I):
        return "Programming", "Programming General"
    if re.search(r"\bai\b", blob, re.I):
        return "AI", "LLMs"
    if re.search(r"\b(book|mindset|life|success|identity|smart|consistent|fear|therapist|iq)\b", blob, re.I):
        return "Psychology & Philosophy", "Self Improvement"
    if re.search(r"\b(sex|lust|girls|wives|seduce)\b", blob, re.I):
        return "Psychology & Philosophy", "Relationships"
    if re.search(r"\b(fat|body|exercise|grip|physique)\b", blob, re.I):
        return "Health & Fitness", "Fitness"
    return "Other", "Unsorted"


def age_bucket(text: str | None) -> str:
    if not text:
        return "unknown"
    s = text.lower()
    if "minute" in s or "hour" in s:
        return "today"
    if "day" in s:
        return "this week"
    if "week" in s:
        return "this month"
    m = re.search(r"(\d+)\s+month", s)
    if m:
        n = int(m.group(1))
        if n <= 3:
            return "1-3 months"
        return "3-12 months"
    if "month" in s:
        return "1-3 months"
    if "year" in s:
        return "1 year+"
    return "unknown"



def parse_video_info(block: str) -> tuple[str | None, str | None]:
    m = VIDEO_INFO_RE.search(block)
    if not m:
        return None, None
    spans = [s.strip() for s in SPAN_RE.findall(m.group(1))]
    spans = [s for s in spans if s and s != "•"]
    views = next((s for s in spans if "view" in s.lower()), None)
    ago = next((s for s in spans if s != views), None)
    return views, ago


def extract_json_progress(html: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in re.finditer(r'percentDurationWatched":(\d+)', html):
        window = html[max(0, m.start() - 2500) : m.start()]
        vids = JSON_VID_RE.findall(window)
        if vids:
            out.setdefault(vids[-1], {})["percentDurationWatched"] = int(m.group(1))
    for m in re.finditer(r'startTimeSeconds":(\d+)', html):
        window = html[max(0, m.start() - 2500) : m.start()]
        vids = JSON_VID_RE.findall(window)
        if vids:
            out.setdefault(vids[-1], {})["startTimeSeconds"] = int(m.group(1))
    return out


def extract_html_rows(html: str) -> list[dict]:
    json_prog = extract_json_progress(html)
    parts = VIDEO_BLOCK_RE.split(html)
    rows: list[dict] = []
    seen: set[str] = set()
    for block in parts[1:]:
        vid_m = WATCH_V_RE.search(block)
        if not vid_m:
            continue
        video_id = vid_m.group(1)
        if video_id in seen:
            continue
        seen.add(video_id)
        idx_m = INDEX_RE.search(block)
        thumb_href = re.search(
            rf'<a id="thumbnail"[^>]*href="([^"]*{re.escape(video_id)}[^"]*)"',
            block,
        )
        href = thumb_href.group(1) if thumb_href else ""
        t_m = T_SEC_RE.search(href)
        views_text, published_ago = parse_video_info(block)
        handle_m = HANDLE_RE.search(block)
        ch_m = CHANNEL_TITLE_RE.search(block)
        thumb_m = re.search(
            rf'src="(https://i\.ytimg\.com/vi/{re.escape(video_id)}[^"]+)"',
            block,
        )
        jp = json_prog.get(video_id, {})
        rows.append(
            {
                "videoId": video_id,
                "htmlIndex": int(idx_m.group(1)) if idx_m else None,
                "watched": ">WATCHED</yt-formatted-string>" in block
                or jp.get("percentDurationWatched") is not None,
                "hasResumeRenderer": "resume-playback-renderer" in block,
                "resumeSeconds": jp.get("startTimeSeconds")
                or (int(t_m.group(1)) if t_m else None),
                "jsonWatchedPercent": jp.get("percentDurationWatched"),
                "viewsText": views_text,
                "publishedAgo": published_ago,
                "channelHandle": handle_m.group(1) if handle_m else None,
                "htmlChannel": ch_m.group(1) if ch_m and ch_m.group(1) else None,
                "thumbnailUrl": (
                    thumb_m.group(1).replace("&amp;", "&") if thumb_m else None
                ),
            }
        )
    return rows


def renderer_block(html: str, video_id: str) -> str | None:
    parts = VIDEO_BLOCK_RE.split(html)
    needle = f"/watch?v={video_id}"
    for block in parts[1:]:
        if needle in block:
            return block
    return None


def probe_video(html: str, video_id: str) -> dict:
    block = renderer_block(html, video_id)
    if block is None:
        return {"videoId": video_id, "found": False}
    views_text, published_ago = parse_video_info(block)
    handle_m = HANDLE_RE.search(block)
    overlay_idx = block.find('id="overlays"')
    overlay_snip = block[overlay_idx : overlay_idx + 900] if overlay_idx >= 0 else ""
    thumb_href = re.search(
        rf'<a id="thumbnail"[^>]*href="([^"]*{re.escape(video_id)}[^"]*)"',
        block,
    )
    href = thumb_href.group(1) if thumb_href else ""
    t_m = T_SEC_RE.search(href)
    jp = extract_json_progress(html).get(video_id, {})
    return {
        "videoId": video_id,
        "found": True,
        "watched": ">WATCHED</yt-formatted-string>" in block,
        "hasResumeRenderer": "resume-playback-renderer" in block,
        "resumeSeconds": jp.get("startTimeSeconds")
        or (int(t_m.group(1)) if t_m else None),
        "jsonWatchedPercent": jp.get("percentDurationWatched"),
        "jsonStartSeconds": jp.get("startTimeSeconds"),
        "viewsText": views_text,
        "publishedAgo": published_ago,
        "channelHandle": handle_m.group(1) if handle_m else None,
        "overlayHasPercentAttr": "percent" in overlay_snip.lower(),
        "thumbnailHrefHasT": bool(t_m),
    }


def hours(seconds: float | int | None) -> float:
    if not seconds:
        return 0.0
    return round(float(seconds) / 3600.0, 2)


def table_to_records(df: pl.DataFrame) -> list[dict]:
    return df.to_dicts()


def pie_slices(
    rows: list[dict], label_key: str, *, top: int = 8
) -> list[dict]:
    ordered = sorted(rows, key=lambda r: int(r.get("n") or 0), reverse=True)
    head = ordered[:top]
    tail = ordered[top:]
    out = [
        {
            "label": str(r.get(label_key) or "(none)"),
            "n": int(r.get("n") or 0),
            "hours": float(r.get("hours") or 0),
        }
        for r in head
    ]
    if tail:
        out.append(
            {
                "label": "Other",
                "n": sum(int(r.get("n") or 0) for r in tail),
                "hours": round(sum(float(r.get("hours") or 0) for r in tail), 1),
            }
        )
    return out


def _insight_cards(
    ingest: pl.DataFrame,
    *,
    n: int,
    total_sec: int,
    remaining_sec: int,
    resume_sec: int,
    by_cat: pl.DataFrame,
    by_channel: pl.DataFrame,
    by_bucket: pl.DataFrame,
    easy_n: int,
) -> list[dict]:
    top_cat = by_cat.row(0, named=True)
    long = ingest.filter(pl.col("durationBucket") == "2h+")
    long_h = hours(int(long["durationSeconds"].fill_null(0).sum()))
    fcc = ingest.filter(pl.col("channel") == "freeCodeCamp.org")
    fcc_h = hours(int(fcc["durationSeconds"].fill_null(0).sum()))
    other_n = ingest.filter(pl.col("category") == "Other").height
    other_pct = round(100 * other_n / max(n, 1), 1)
    unavail_n = ingest.filter(pl.col("category") == "Unavailable").height
    unplayed_n = (
        ingest.filter(pl.col("watchState") == "unplayed").height
        if "watchState" in ingest.columns
        else 0
    )
    stale_n = (
        ingest.filter(pl.col("ageBucket") == "1 year+").height
        if "ageBucket" in ingest.columns
        else 0
    )
    chess_n = ingest.filter(pl.col("subCategory") == "Chess").height
    hebrew_n = int(ingest["hasHebrew"].sum())
    cards = [
        {
            "id": "debt",
            "title": "Queue is 137 days of video",
            "body": f"{hours(total_sec)} h queued. At 2h/day that is {round(hours(total_sec)/2)} days.",
            "value": f"{hours(total_sec)} h",
        },
        {
            "id": "marathons",
            "title": "2h+ owns the clock",
            "body": f"{long.height} videos ≥2h = {long_h} h ({round(100*long_h/max(hours(total_sec),0.01),1)}% of runtime).",
            "value": f"{long.height}",
            "filter": {"durationBucket": "2h+"},
        },
        {
            "id": "programming",
            "title": f"{top_cat['category']} is {top_cat['pct']}% of count",
            "body": f"{top_cat['n']} videos, {top_cat['hours']} h.",
            "value": f"{top_cat['pct']}%",
            "filter": {"category": top_cat["category"]},
        },
        {
            "id": "other",
            "title": "Other leftover",
            "body": f"{other_n} still Other ({other_pct}%). Target was <5%.",
            "value": f"{other_pct}%",
            "filter": {"category": "Other"},
        },
        {
            "id": "unavail",
            "title": "Gone from YouTube",
            "body": f"{unavail_n} private/deleted/unavailable. Safe first delete batch.",
            "value": str(unavail_n),
            "filter": {"category": "Unavailable"},
        },
        {
            "id": "unplayed",
            "title": "Never started",
            "body": f"{unplayed_n} have no watched overlay and no resume timestamp.",
            "value": str(unplayed_n),
            "filter": {"watched": "no"},
        },
        {
            "id": "stale",
            "title": "Older than a year",
            "body": f"{stale_n} published 1 year+. Likely duplicated by newer videos.",
            "value": str(stale_n),
        },
        {
            "id": "hebrew",
            "title": "Hebrew titles",
            "body": f"{hebrew_n} titles contain Hebrew. Own filter in browse.",
            "value": str(hebrew_n),
        },
        {
            "id": "chess",
            "title": "Chess pile",
            "body": f"{chess_n} recategorized into Gaming / Chess from Other.",
            "value": str(chess_n),
            "filter": {"category": "Gaming", "subCategory": "Chess"},
        },
        {
            "id": "fcc",
            "title": "freeCodeCamp is a second queue",
            "body": f"{fcc.height} videos, {fcc_h} h.",
            "value": f"{fcc_h} h",
            "filter": {"channel": "freeCodeCamp.org"},
        },
        {
            "id": "easy",
            "title": "Dead or already watched",
            "body": f"{easy_n} private/deleted/mostly-watched (HTML priority ≤ 3).",
            "value": str(easy_n),
        },
    ]
    if "recommendedAction" not in ingest.columns:
        return cards
    def act(name: str) -> int:
        return ingest.filter(pl.col("recommendedAction") == name).height
    delete_n = act("deleteCandidate")
    peek_n = act("peek1m")
    soon_n = act("watchSoon")
    keep_n = act("keepReference")
    flags = (
        ingest.select(pl.col("flags").list.explode(empty_as_null=True).alias("f"))
        .drop_nulls()
        .group_by("f")
        .agg(n=pl.len())
        if "flags" in ingest.columns
        else pl.DataFrame({"f": [], "n": []})
    )
    def flag_n(name: str) -> int:
        hit = flags.filter(pl.col("f") == name)
        return int(hit["n"][0]) if hit.height else 0
    mean_del = round(float(ingest["deleteScore"].mean() or 0), 1)
    mean_val = round(float(ingest["estimatedValue"].mean() or 0), 1)
    cards.extend(
        [
            {
                "id": "delete",
                "title": "Delete candidates",
                "body": f"{delete_n} scored as deleteCandidate. First pass for the YouTube userscript.",
                "value": str(delete_n),
                "filter": {"recommendedAction": "deleteCandidate"},
            },
            {
                "id": "peek",
                "title": "Peek 1 minute",
                "body": f"{peek_n} need a glance before delete (analyzeBeforeDelete). Ambiguous titles / Other-General.",
                "value": str(peek_n),
                "filter": {"recommendedAction": "peek1m"},
            },
            {
                "id": "soon",
                "title": "Watch soon — tiny list",
                "body": f"Only {soon_n} videos scored watchSoon. This is the actual watch pile.",
                "value": str(soon_n),
                "filter": {"recommendedAction": "watchSoon"},
            },
            {
                "id": "keep",
                "title": "Keep as reference",
                "body": f"{keep_n} keepReference. Do not dump these in a bulk remove.",
                "value": str(keep_n),
                "filter": {"recommendedAction": "keepReference"},
            },
            {
                "id": "scores",
                "title": "Mean delete vs value",
                "body": f"deleteScore {mean_del} vs estimatedValue {mean_val}. Higher deleteScore = safer to cut.",
                "value": f"{mean_del} / {mean_val}",
            },
            {
                "id": "redund",
                "title": "High redundancy",
                "body": f"{flag_n('high_redundancy')} flagged high_redundancy. Same advice, many thumbnails.",
                "value": str(flag_n("high_redundancy")),
                "filter": {"flag": "high_redundancy"},
            },
            {
                "id": "class",
                "title": "Needs classification",
                "body": f"{other_n} still Other after recategorize ({other_pct}%). Peek these; labels were empty.",
                "value": str(other_n),
                "filter": {"category": "Other"},
            },
            {
                "id": "goal",
                "title": "High goal fit",
                "body": f"{flag_n('high_goal_fit')} match current goals. Protect these when bulk-deleting.",
                "value": str(flag_n("high_goal_fit")),
                "filter": {"flag": "high_goal_fit"},
            },
            {
                "id": "newer",
                "title": "Replace with newer",
                "body": f"{int(ingest['replaceWithNewerResource'].sum())} marked replaceWithNewerResource.",
                "value": str(int(ingest["replaceWithNewerResource"].sum())),
            },
        ]
    )
    return cards


def main() -> None:
    OUT.mkdir(exist_ok=True)
    html = HTML.read_text(encoding="utf-8", errors="replace")
    html_rows = extract_html_rows(html)
    html_df = pl.DataFrame(html_rows)

    sample = [r["videoId"] for r in html_rows[:3] if r.get("videoId")]
    probe = {
        "sample": [probe_video(html, vid) for vid in sample],
        "html_video_blocks": len(html_rows),
        "html_has_percentDurationWatched": "percentDurationWatched" in html,
        "html_has_startTimeSeconds": "startTimeSeconds" in html,
        "html_resume_renderer_count": html.count("resume-playback-renderer"),
        "html_watched_overlay_count": html.count(">WATCHED</yt-formatted-string>"),
    }
    (OUT / "html_probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")

    videos = pl.read_ndjson(JSONL)
    videos = videos.with_columns(
        pl.col("duration").cast(pl.Utf8),
        pl.col("channel").fill_null("").cast(pl.Utf8),
        pl.col("title").fill_null("").cast(pl.Utf8),
        pl.col("category").fill_null("Other").cast(pl.Utf8),
        pl.col("subCategory").fill_null("General").cast(pl.Utf8),
    )
    duration_seconds = videos["duration"].map_elements(
        parse_duration_seconds, return_dtype=pl.Int64
    )
    videos = videos.with_columns(durationSeconds=duration_seconds)
    videos = videos.with_columns(
        durationBucket=pl.col("durationSeconds").map_elements(
            duration_bucket, return_dtype=pl.Utf8, skip_nulls=False
        ),
        hasHebrew=pl.col("title").map_elements(
            lambda t: bool(HEBREW_RE.search(t or "")), return_dtype=pl.Boolean
        ),
        availability=pl.when(pl.col("title") == "[Private video]")
        .then(pl.lit("private"))
        .when(pl.col("title") == "[Deleted video]")
        .then(pl.lit("deleted"))
        .when(pl.col("title") == "[Unavailable video]")
        .then(pl.lit("unavailable"))
        .when((pl.col("channel") == "") & pl.col("duration").is_null())
        .then(pl.lit("unavailable"))
        .otherwise(pl.lit("ok")),
        isShort=pl.col("title").str.contains(r"(?i)#shorts")
        | (pl.col("durationSeconds").fill_null(10**9) <= 60),
    )
    videos = videos.with_columns(
        videoIdDupCount=pl.len().over("videoId"),
        positionDupCount=pl.len().over("position"),
    )

    joined = videos.join(html_df, on="videoId", how="left")
    joined = joined.with_columns(
        channel=pl.when(pl.col("channel") == "")
        .then(pl.col("htmlChannel").fill_null(""))
        .otherwise(pl.col("channel")),
        viewsApprox=pl.col("viewsText").map_elements(parse_views, return_dtype=pl.Int64),
        htmlMatched=pl.col("watched").is_not_null(),
        watched=pl.col("watched").fill_null(False),
        hasResumeRenderer=pl.col("hasResumeRenderer").fill_null(False),
    )
    recat = [
        recategorize(t, c, cat, sub)
        for t, c, cat, sub in joined.select(
            ["title", "channel", "category", "subCategory"]
        ).iter_rows()
    ]
    joined = joined.with_columns(
        category=pl.Series([p[0] for p in recat]),
        subCategory=pl.Series([p[1] for p in recat]),
        ageBucket=pl.col("publishedAgo").map_elements(
            age_bucket, return_dtype=pl.Utf8, skip_nulls=False
        ),
        watchState=pl.when(pl.col("watched"))
        .then(pl.lit("watched overlay"))
        .when(pl.col("resumeSeconds").is_not_null())
        .then(pl.lit("started"))
        .otherwise(pl.lit("unplayed")),
        language=pl.when(pl.col("hasHebrew"))
        .then(pl.lit("Hebrew"))
        .otherwise(pl.lit("English")),
    )
    computed_pct = (
        pl.when(
            pl.col("resumeSeconds").is_not_null() & (pl.col("durationSeconds") > 0)
        )
        .then((pl.col("resumeSeconds") / pl.col("durationSeconds") * 100).clip(0, 100))
        .otherwise(None)
    )
    joined = joined.with_columns(
        watchedPercent=pl.coalesce(
            pl.col("jsonWatchedPercent").cast(pl.Float64),
            computed_pct,
        ).round(1)
    )
    joined = joined.with_columns(
        remainingSeconds=pl.when(pl.col("watchedPercent") >= 99)
        .then(pl.lit(0))
        .when(pl.col("durationSeconds").is_not_null())
        .then(
            (
                pl.col("durationSeconds") - pl.col("resumeSeconds").fill_null(0)
            ).clip(lower_bound=0)
        )
        .otherwise(None)
    )

    def hints(row: dict) -> list[str]:
        out: list[str] = []
        if row["availability"] != "ok":
            out.append(row["availability"])
        pct = row["watchedPercent"]
        if pct is not None and pct >= 85:
            out.append("already_watched")
        elif pct is not None and pct >= 40:
            out.append("mostly_watched")
        if row["isShort"]:
            out.append("short")
        if (row["durationSeconds"] or 0) >= 2 * 3600:
            out.append("very_long")
        if row["category"] == "Other" and row["subCategory"] == "General":
            out.append("uncategorized")
        if (row["videoIdDupCount"] or 1) > 1:
            out.append("duplicate_id")
        if (row["positionDupCount"] or 1) > 1:
            out.append("duplicate_position")
        if not row["htmlMatched"]:
            out.append("missing_from_html")
        return out

    hint_series = pl.Series(
        "removeHints",
        [hints(r) for r in joined.iter_rows(named=True)],
        dtype=pl.List(pl.Utf8),
    )
    joined = joined.with_columns(hint_series)
    joined = joined.with_columns(
        removePriority=pl.when(pl.col("removeHints").list.contains("private"))
        .then(1)
        .when(pl.col("removeHints").list.contains("deleted"))
        .then(1)
        .when(pl.col("removeHints").list.contains("unavailable"))
        .then(1)
        .when(pl.col("removeHints").list.contains("already_watched"))
        .then(2)
        .when(pl.col("removeHints").list.contains("mostly_watched"))
        .then(3)
        .when(pl.col("removeHints").list.contains("duplicate_id"))
        .then(4)
        .when(pl.col("removeHints").list.contains("short"))
        .then(5)
        .when(pl.col("removeHints").list.contains("very_long"))
        .then(6)
        .otherwise(9),
        searchBlob=pl.concat_str(
            [
                pl.col("title"),
                pl.lit(" "),
                pl.col("channel"),
                pl.lit(" "),
                pl.col("channelHandle").fill_null(""),
                pl.lit(" "),
                pl.col("category"),
                pl.lit(" "),
                pl.col("subCategory"),
                pl.lit(" "),
                pl.col("videoId"),
            ]
        ),
    )

    if TRIAGE.exists():
        scored = pl.read_ndjson(TRIAGE)
        extra = [c for c in scored.columns if c != "videoId" and c not in joined.columns]
        joined = joined.join(scored.select(["videoId", *extra]), on="videoId", how="left")
        if "deleteScore" in joined.columns:
            joined = joined.with_columns(
                deleteBand=pl.when(pl.col("deleteScore").is_null())
                .then(pl.lit("unscored"))
                .when(pl.col("deleteScore") >= 45)
                .then(pl.lit("45+ cut"))
                .when(pl.col("deleteScore") >= 35)
                .then(pl.lit("35-44 lean-out"))
                .when(pl.col("deleteScore") >= 25)
                .then(pl.lit("25-34 mixed"))
                .otherwise(pl.lit("15-24 keep"))
            )
        joined = joined.with_columns(
            searchBlob=pl.concat_str(
                [
                    pl.col("searchBlob"),
                    pl.lit(" "),
                    pl.col("recommendedAction").fill_null(""),
                    pl.lit(" "),
                    pl.col("contentType").fill_null(""),
                    pl.lit(" "),
                    pl.col("triageReason").fill_null(""),
                ]
            )
        )

    ingest_cols = [
        "position",
        "videoId",
        "title",
        "url",
        "channel",
        "channelHandle",
        "duration",
        "durationSeconds",
        "durationBucket",
        "category",
        "subCategory",
        "watched",
        "resumeSeconds",
        "watchedPercent",
        "jsonWatchedPercent",
        "remainingSeconds",
        "viewsText",
        "viewsApprox",
        "publishedAgo",
        "ageBucket",
        "watchState",
        "language",
        "thumbnailUrl",
        "hasHebrew",
        "availability",
        "isShort",
        "htmlMatched",
        "htmlIndex",
        "videoIdDupCount",
        "positionDupCount",
        "removeHints",
        "removePriority",
        "searchBlob",
        "contentType",
        "recommendedAction",
        "triageReason",
        "flags",
        "personalRelevance",
        "deleteScore",
        "estimatedValue",
        "efficiencyScore",
        "redundancyRisk",
        "watchCost",
        "actionabilityScore",
        "triageConfidence",
        "analyzeBeforeDelete",
        "bulkTrainingSource",
        "replaceWithNewerResource",
        "deleteBand",
    ]
    ingest_cols = [c for c in ingest_cols if c in joined.columns]
    ingest = joined.select(ingest_cols).sort(["removePriority", "position"])
    ingest.write_parquet(OUT / "videos.parquet")
    ingest.write_ndjson(OUT / "videos.jsonl")
    csv_df = ingest.with_columns(pl.col("removeHints").list.join("|"))
    if "flags" in csv_df.columns:
        csv_df = csv_df.with_columns(pl.col("flags").list.join("|"))
    csv_df.write_csv(OUT / "videos.csv")

    n = ingest.height
    dur = ingest["durationSeconds"]
    total_sec = int(dur.fill_null(0).sum())
    remaining_sec = int(ingest["remainingSeconds"].fill_null(0).sum())
    resume_sec = int(ingest["resumeSeconds"].fill_null(0).sum())

    by_cat = (
        ingest.group_by("category")
        .agg(
            n=pl.len(),
            hours=pl.col("durationSeconds").fill_null(0).sum() / 3600,
            watched=pl.col("watched").sum(),
            uncategorized_overlap=pl.col("subCategory")
            .eq("General")
            .sum(),
        )
        .with_columns(hours=pl.col("hours").round(1), pct=(pl.col("n") / n * 100).round(1))
        .sort("n", descending=True)
    )
    by_sub = (
        ingest.group_by(["category", "subCategory"])
        .agg(n=pl.len(), hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1))
        .sort("n", descending=True)
    )
    by_channel = (
        ingest.filter(pl.col("channel") != "")
        .group_by("channel")
        .agg(
            n=pl.len(),
            hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1),
            watched=pl.col("watched").sum(),
        )
        .sort("n", descending=True)
        .head(25)
    )
    by_bucket = (
        ingest.group_by("durationBucket")
        .agg(n=pl.len(), hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1))
        .sort("n", descending=True)
    )
    hint_counts = (
        ingest.select(
            pl.col("removeHints").list.explode(empty_as_null=True).alias("hint")
        )
        .drop_nulls()
        .group_by("hint")
        .agg(n=pl.len())
        .sort("n", descending=True)
    )
    easy_remove = ingest.filter(pl.col("removePriority") <= 3).select(
        [
            "position",
            "videoId",
            "title",
            "channel",
            "duration",
            "watchedPercent",
            "availability",
            "removeHints",
            "category",
        ]
    )

    insights = {
        "source": {
            "jsonlRows": n,
            "jsonlUniqueVideoIds": ingest["videoId"].n_unique(),
            "htmlMatched": int(ingest["htmlMatched"].sum()),
            "htmlExtractedUnique": html_df.height,
        },
        "time": {
            "totalHours": hours(total_sec),
            "resumeHours": hours(resume_sec),
            "remainingHours": hours(remaining_sec),
            "medianMinutes": round(float(dur.drop_nulls().median() or 0) / 60, 1),
            "meanMinutes": round(float(dur.drop_nulls().mean() or 0) / 60, 1),
            "maxDuration": ingest.filter(
                pl.col("durationSeconds") == dur.max()
            )
            .select(["title", "channel", "duration", "videoId"])
            .to_dicts(),
        },
        "quality": {
            "privateOrUnavailable": ingest.filter(pl.col("availability") != "ok").height,
            "nullDuration": ingest["durationSeconds"].null_count(),
            "duplicateVideoIds": ingest.filter(pl.col("videoIdDupCount") > 1).height,
            "duplicatePositions": ingest.filter(pl.col("positionDupCount") > 1).height,
            "hebrewTitles": int(ingest["hasHebrew"].sum()),
            "shorts": int(ingest["isShort"].sum()),
            "emptyChannel": ingest.filter(pl.col("channel") == "").height,
        },
        "watchState": {
            "watchedOverlay": int(ingest["watched"].sum()),
            "withResumeTimestamp": ingest["resumeSeconds"].drop_nulls().len(),
            "watchedPctKnown": ingest["watchedPercent"].drop_nulls().len(),
            "jsonPercentRows": ingest["jsonWatchedPercent"].drop_nulls().len(),
            "viewsParsed": ingest["viewsApprox"].drop_nulls().len(),
            "publishedAgoParsed": ingest["publishedAgo"].drop_nulls().len(),
            "watchedMedianPct": (
                round(float(ingest["watchedPercent"].drop_nulls().median()), 1)
                if ingest["watchedPercent"].drop_nulls().len()
                else None
            ),
        },
        "byCategory": table_to_records(by_cat),
        "bySubCategoryTop20": table_to_records(by_sub.head(20)),
        "byDurationBucket": table_to_records(by_bucket),
        "topChannels": table_to_records(by_channel),
        "removeHintCounts": table_to_records(hint_counts),
        "easyRemoveCount": easy_remove.height,
        "pies": {
            "duration": pie_slices(table_to_records(by_bucket), "durationBucket", top=9),
            "category": pie_slices(table_to_records(by_cat), "category", top=8),
            "subCategory": pie_slices(
                by_sub.with_columns(
                    label=pl.concat_str(
                        [pl.col("category"), pl.lit(" / "), pl.col("subCategory")]
                    )
                ).to_dicts(),
                "label",
                top=10,
            ),
            **(
                {
                    "recommendedAction": pie_slices(
                        ingest.group_by("recommendedAction")
                        .agg(
                            n=pl.len(),
                            hours=(
                                pl.col("durationSeconds").fill_null(0).sum() / 3600
                            ).round(1),
                        )
                        .to_dicts(),
                        "recommendedAction",
                        top=8,
                    ),
                    "contentType": pie_slices(
                        ingest.group_by("contentType")
                        .agg(
                            n=pl.len(),
                            hours=(
                                pl.col("durationSeconds").fill_null(0).sum() / 3600
                            ).round(1),
                        )
                        .to_dicts(),
                        "contentType",
                        top=8,
                    ),
                    "deleteBand": pie_slices(
                        ingest.group_by("deleteBand")
                        .agg(
                            n=pl.len(),
                            hours=(
                                pl.col("durationSeconds").fill_null(0).sum() / 3600
                            ).round(1),
                        )
                        .to_dicts(),
                        "deleteBand",
                        top=8,
                    ),
                    "flags": pie_slices(
                        ingest.select(
                            pl.col("flags")
                            .list.explode(empty_as_null=True)
                            .alias("label")
                        )
                        .drop_nulls()
                        .group_by("label")
                        .agg(n=pl.len())
                        .with_columns(hours=pl.lit(0.0))
                        .to_dicts(),
                        "label",
                        top=9,
                    ),
                }
                if "recommendedAction" in ingest.columns
                else {}
            ),
            "availability": pie_slices(
                ingest.group_by("availability")
                .agg(
                    n=pl.len(),
                    hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1),
                )
                .to_dicts(),
                "availability",
                top=6,
            ),
            "watchState": pie_slices(
                ingest.group_by("watchState")
                .agg(
                    n=pl.len(),
                    hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1),
                )
                .to_dicts(),
                "watchState",
                top=5,
            ),
            "language": pie_slices(
                ingest.group_by("language")
                .agg(
                    n=pl.len(),
                    hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1),
                )
                .to_dicts(),
                "language",
                top=4,
            ),
            "age": pie_slices(
                ingest.group_by("ageBucket")
                .agg(
                    n=pl.len(),
                    hours=(pl.col("durationSeconds").fill_null(0).sum() / 3600).round(1),
                )
                .to_dicts(),
                "ageBucket",
                top=8,
            ),
            "channel": pie_slices(table_to_records(by_channel), "channel", top=10),
        },
        "cards": _insight_cards(
            ingest,
            n=n,
            total_sec=total_sec,
            remaining_sec=remaining_sec,
            resume_sec=resume_sec,
            by_cat=by_cat,
            by_channel=by_channel,
            by_bucket=by_bucket,
            easy_n=easy_remove.height,
        ),
        "probe": {
            "sample": probe.get("sample", []),
            "htmlSignalsPresent": {
                "percentDurationWatched": probe["html_has_percentDurationWatched"],
                "startTimeSeconds": probe["html_has_startTimeSeconds"],
                "resumeRendererCount": probe["html_resume_renderer_count"],
                "watchedOverlayCount": probe["html_watched_overlay_count"],
            },
        },
    }
    (OUT / "insights.json").write_text(
        json.dumps(insights, indent=2, default=str), encoding="utf-8"
    )
    easy_remove.write_ndjson(OUT / "easy_remove.jsonl")

    md = []
    md.append("# Watch Later Insights")
    md.append("")
    md.append(f"- Rows: **{n}** unique-ish playlist entries, **{ingest['videoId'].n_unique()}** unique videoIds")
    md.append(f"- HTML matched: **{int(ingest['htmlMatched'].sum())}** / {n} (extracted {html_df.height} unique ids from DOM)")
    md.append(f"- Total runtime: **{hours(total_sec)} h** (median {insights['time']['medianMinutes']} min)")
    md.append(f"- Already-played resume time: **{hours(resume_sec)} h**; remaining if you finish everything: **{hours(remaining_sec)} h**")
    md.append(f"- WATCHED overlay: **{int(ingest['watched'].sum())}**; resume `t=` present: **{ingest['resumeSeconds'].drop_nulls().len()}**")
    md.append(f"- Hebrew titles: **{int(ingest['hasHebrew'].sum())}**; shorts/≤1m: **{int(ingest['isShort'].sum())}**; unavailable: **{insights['quality']['privateOrUnavailable']}**")
    md.append("")
    md.append("## HTML extras vs JSONL")
    md.append("")
    md.append("JSONL has: position, videoId, title, url, channel, duration, category, subCategory.")
    md.append("")
    md.append("")
    md.append("## Easy removals (priority ≤ 3)")
    md.append("")
    md.append(f"**{easy_remove.height}** videos: private/deleted/unavailable, already-watched (≥85% known progress), or mostly-watched (≥40%). WATCHED with unknown percent is **not** auto-flagged.")
    md.append("")
    md.append("Hint counts:")
    for row in hint_counts.iter_rows(named=True):
        md.append(f"- `{row['hint']}`: {row['n']}")
    md.append("")
    md.append("## Categories")
    md.append("")
    md.append("| category | n | % | hours | watched |")
    md.append("|---|---:|---:|---:|---:|")
    for row in by_cat.iter_rows(named=True):
        md.append(
            f"| {row['category']} | {row['n']} | {row['pct']} | {row['hours']} | {row['watched']} |"
        )
    md.append("")
    md.append("## Duration buckets")
    md.append("")
    md.append("| bucket | n | hours |")
    md.append("|---|---:|---:|")
    for row in by_bucket.iter_rows(named=True):
        md.append(f"| {row['durationBucket']} | {row['n']} | {row['hours']} |")
    md.append("")
    md.append("## Top channels")
    md.append("")
    md.append("| channel | n | hours | watched |")
    md.append("|---|---:|---:|---:|")
    for row in by_channel.head(15).iter_rows(named=True):
        md.append(f"| {row['channel']} | {row['n']} | {row['hours']} | {row['watched']} |")
    md.append("")
    md.append("## Ingest files")
    md.append("")
    md.append("UI-ready (filter / search / group / sort):")
    md.append("")
    md.append("- `out/videos.jsonl` — one object per video")
    md.append("- `out/videos.parquet` — same schema")
    md.append("- `out/videos.csv` — spreadsheet fallback")
    md.append("- `out/easy_remove.jsonl` — high-confidence delete candidates")
    md.append("- `out/insights.json` — machine-readable rollups")
    md.append("")
    md.append("Key UI fields: `category`, `subCategory`, `channel`, `durationBucket`, `watched`, `watchedPercent`, `availability`, `hasHebrew`, `isShort`, `removeHints`, `removePriority`, `searchBlob`, `viewsApprox`, `publishedAgo`.")
    md.append("")
    (OUT / "insights.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    web_public = ROOT / "web" / "public"
    if web_public.is_dir():
        shutil.copyfile(OUT / "insights.json", web_public / "insights.json")
        shutil.copyfile(OUT / "videos.jsonl", web_public / "videos.jsonl")

    print(json.dumps(
        {
            "rows": n,
            "htmlMatched": int(ingest["htmlMatched"].sum()),
            "watched": int(ingest["watched"].sum()),
            "totalHours": hours(total_sec),
            "easyRemove": easy_remove.height,
            "out": str(OUT),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
