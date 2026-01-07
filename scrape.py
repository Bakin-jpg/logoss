import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_hari_ini.json")
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Ubah URL gambar jadi HD (128px)."""
    if not url: return ""
    new_url = re.sub(r'w=\d+', 'w=128', url)
    new_url = re.sub(r'h=\d+', 'h=128', new_url)
    return new_url

def parse_iso_date_to_wib(iso_date_str):
    """Ubah waktu ISO UTC ke WIB."""
    try:
        clean_iso = iso_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        dt_wib = dt_utc.astimezone(WIB)
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M")
        }
    except:
        return {"date": "TBD", "time": "TBD"}

def find_match_containers(data):
    """
    Fungsi Pintar: Mencari data pertandingan di kedalaman JSON mana pun.
    Mencari objek yang memiliki 'matchCards' dan 'sectionHeader'.
    """
    found = []
    if isinstance(data, dict):
        # Cek apakah ini container pertandingan yang kita cari
        if 'matchCards' in data and isinstance(data['matchCards'], list):
            if len(data['matchCards']) > 0:
                found.append(data)
        
        # Jika bukan, cari lagi di anak-anaknya
        for k, v in data.items():
            found.extend(find_match_containers(v))
            
    elif isinstance(data, list):
        for item in data:
            found.extend(find_match_containers(item))
            
    return found

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper OneFootball (Metode Smart JSON)...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        url = "https://onefootball.com/id/pertandingan"
        
        try:
            # Tunggu halaman siap
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Coba ambil data JSON yang tertanam (Cara Paling Akurat & Cepat)
            print("📦 Mencoba ekstrak data JSON internal...")
            
            # Ambil teks dari dalam tag script secara langsung (Lebih aman dari regex)
            json_str = page.locator("#__NEXT_DATA__").text_content()
            
            if json_str:
                raw_data = json.loads(json_str)
                matches_data = []
                
                # Gunakan pencarian rekursif untuk menemukan blok pertandingan
                match_containers = find_match_containers(raw_data)
                print(f"🔍 Ditemukan {len(match_containers)} blok kompetisi dari JSON.")
                
                for container in match_containers:
                    # 1. Info Liga
                    header = container.get('sectionHeader', {})
                    league_name = header.get('title', 'Unknown League')
                    league_round = header.get('subtitle', '') # Ini Data Matchday/Round
                    
                    league_logo_raw = header.get('entityLogo', {}).get('path', '')
                    league_logo = get_high_res_image(league_logo_raw)
                    
                    # 2. List Match
                    for card in container.get('matchCards', []):
                        # Pastikan ini data match valid
                        if 'homeTeam' not in card or 'kickoff' not in card:
                            continue
                            
                        # Waktu
                        kickoff_iso = card.get('kickoff')
                        wib = parse_iso_date_to_wib(kickoff_iso)
                        
                        # Tim
                        home = card.get('homeTeam', {})
                        away = card.get('awayTeam', {})
                        
                        match_item = {
                            "league_name": league_name,
                            "league_round": league_round,
                            "league_logo": league_logo,
                            "match_date": wib['date'],
                            "match_time": wib['time'],
                            "home_team": home.get('name', ''),
                            "home_logo": get_high_res_image(home.get('imageObject', {}).get('path', '')),
                            "home_score": home.get('score', ''),
                            "away_team": away.get('name', ''),
                            "away_logo": get_high_res_image(away.get('imageObject', {}).get('path', '')),
                            "away_score": away.get('score', ''),
                            "link": "https://onefootball.com" + card.get('link', '')
                        }
                        matches_data.append(match_item)
                
                # Sorting
                matches_data.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
                
                # Simpan
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(matches_data, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ SUKSES! {len(matches_data)} pertandingan tersimpan.")
                
            else:
                print("⚠️ Tag __NEXT_DATA__ tidak ditemukan (Mungkin diblokir/Captcha).")
                # Disini bisa ditambahkan logika fallback scrolling jika mau, 
                # tapi biasanya JSON method selalu berhasil jika page load sukses.
                
        except Exception as e:
            print(f"❌ Terjadi kesalahan: {e}")
            
        browser.close()

if __name__ == "__main__":
    run()
