import json
import os
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Mengubah URL thumbnail menjadi HD."""
    if not url: return ""
    # Ganti w=xx menjadi w=128
    new_url = re.sub(r'w=\d+', 'w=128', url)
    new_url = re.sub(r'h=\d+', 'h=128', new_url)
    return new_url

def parse_iso_date_to_wib(iso_date_str):
    """Konversi waktu UTC dari JSON ke WIB."""
    try:
        # Format di JSON: 2026-01-06T17:00:00Z
        clean_iso = iso_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        dt_wib = dt_utc.astimezone(WIB)
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M")
        }
    except:
        return {"date": "TBD", "time": "TBD"}

def run():
    with sync_playwright() as p:
        print("🚀 Mengakses OneFootball...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Buka halaman
        page.goto("https://onefootball.com/id/pertandingan", wait_until="domcontentloaded")
        
        # --- METODE EXTRACTION ---
        # Kita tidak scrape elemen visual (div/img).
        # Kita ambil data JSON asli yang tersembunyi di tag <script id="__NEXT_DATA__">
        
        print("📦 Mengambil Raw Data (JSON)...")
        
        # Ambil isi HTML
        content = page.content()
        
        # Cari script __NEXT_DATA__ menggunakan Regex
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', content)
        
        matches_data = []

        if match:
            json_str = match.group(1)
            raw_data = json.loads(json_str)
            
            # Navigasi struktur JSON OneFootball yang rumit
            # props -> pageProps -> containers
            try:
                containers = raw_data['props']['pageProps']['containers']
                
                print(f"🔍 Menganalisa {len(containers)} blok data...")

                for container in containers:
                    # Kita cari tipe 'matchCardsList'
                    # Struktur JSON bisa berbeda-beda, kita coba akses dengan aman
                    comp_data = {}
                    
                    # Cek tipe fullWidth -> component
                    if 'fullWidth' in container.get('type', {}):
                        comp_data = container['fullWidth']['component']
                    
                    # Pastikan ini adalah list pertandingan
                    content_type = comp_data.get('contentType', {})
                    
                    if 'matchCardsList' in content_type:
                        match_list_obj = content_type['matchCardsList']
                        
                        # 1. Ambil Info Liga
                        section_header = match_list_obj.get('sectionHeader', {})
                        league_name = section_header.get('title', 'Unknown League')
                        league_round = section_header.get('subtitle', '') # Matchday/Round
                        
                        # Ambil Logo Liga
                        league_logo_raw = section_header.get('entityLogo', {}).get('path', '')
                        league_logo = get_high_res_image(league_logo_raw)
                        
                        # 2. Ambil List Match
                        cards = match_list_obj.get('matchCards', [])
                        
                        for card in cards:
                            # Skip jika ini bukan pertandingan (misal iklan)
                            if 'homeTeam' not in card:
                                continue

                            # Ambil Waktu
                            kickoff_iso = card.get('kickoff', '')
                            wib_info = parse_iso_date_to_wib(kickoff_iso)
                            
                            # Ambil Tim Home
                            home = card.get('homeTeam', {})
                            home_name = home.get('name', '')
                            home_score = home.get('score', '')
                            home_logo_raw = home.get('imageObject', {}).get('path', '')
                            
                            # Ambil Tim Away
                            away = card.get('awayTeam', {})
                            away_name = away.get('name', '')
                            away_score = away.get('score', '')
                            away_logo_raw = away.get('imageObject', {}).get('path', '')
                            
                            # Link Match
                            match_link = "https://onefootball.com" + card.get('link', '')

                            match_item = {
                                "league_name": league_name,
                                "league_round": league_round,
                                "league_logo": league_logo,
                                "match_date": wib_info['date'],
                                "match_time": wib_info['time'],
                                "home_team": home_name,
                                "home_logo": get_high_res_image(home_logo_raw),
                                "home_score": home_score,
                                "away_team": away_name,
                                "away_logo": get_high_res_image(away_logo_raw),
                                "away_score": away_score,
                                "link": match_link
                            }
                            matches_data.append(match_item)
                            
            except KeyError as e:
                print(f"❌ Struktur JSON berubah: {e}")
        else:
            print("❌ Gagal menemukan data __NEXT_DATA__")

        # Sorting: Tanggal -> Jam -> Liga
        matches_data.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))

        # Simpan
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matches_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ BERHASIL! {len(matches_data)} pertandingan tersimpan.")
        print("   Metode: Direct JSON Extraction (100% Akurat)")
        
        browser.close()

if __name__ == "__main__":
    run()
