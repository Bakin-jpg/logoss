import json
import os
import time
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_hd.json")

# Zona Waktu Indonesia Barat (UTC+7)
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Mengubah URL gambar thumbnail OneFootball menjadi HD."""
    if not url:
        return ""
    # Ganti ukuran w=22/h=22 menjadi w=128 (atau lebih besar)
    # Hapus parameter dpr untuk mendapatkan gambar murni atau set dpr=2
    # Contoh: https://image-service...transform?w=22... -> w=128
    
    # Cara regex aman: ganti parameter w=... dengan w=128
    new_url = re.sub(r'w=\d+', 'w=128', url)
    new_url = re.sub(r'h=\d+', 'h=128', new_url)
    return new_url

def parse_iso_date_to_wib(iso_date_str):
    """
    Mengubah format ISO UTC (2026-01-07T17:30:00Z) 
    menjadi Format Tanggal & Jam WIB.
    """
    try:
        # Hapus 'Z' ubah jadi +00:00 biar dikenali sebagai UTC
        clean_iso = iso_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        
        # Konversi ke WIB
        dt_wib = dt_utc.astimezone(WIB)
        
        # Return object dictionary biar gampang dipakai
        return {
            "full_datetime": dt_wib.isoformat(),
            "date_display": dt_wib.strftime("%Y-%m-%d"), # Tanggal Lokal (Bisa beda dgn tanggal scrape)
            "time_display": dt_wib.strftime("%H:%M")     # Jam Lokal (WIB)
        }
    except Exception as e:
        return {"full_datetime": iso_date_str, "date_display": "N/A", "time_display": "N/A"}

def scrape_matches_by_date(page, date_str):
    """Scrape data pertandingan berdasarkan tanggal URL."""
    url = f"https://onefootball.com/id/pertandingan?date={date_str}"
    print(f"\n--- ⏳ Sedang scrape jadwal URL tanggal: {date_str} ---")
    
    page.goto(url, wait_until="networkidle", timeout=60000)
    
    # Scroll perlahan agar gambar ter-load (penting!)
    for _ in range(7):
        page.mouse.wheel(0, 1000)
        time.sleep(1) # Delay biar script JS website jalan dulu
    
    matches_list = []

    # OneFootball membagi per kompetisi. 
    # Kita cari elemen kontainer yang membungkus Header Liga + List Match
    
    # Selector ini mencari blok pembungkus list kartu pertandingan
    # Biasanya struktur: 
    # <div> -> <div class="SectionHeader...">LIGA</div> -> <ul class="MatchCardsList...">MATCHES</ul>
    
    # Kita cari semua container list pertandingan
    # Selector class MatchCardsList_matches...
    match_lists_ul = page.locator("ul[class*='MatchCardsList_matches']").all()
    
    print(f"   Ditemukan {len(match_lists_ul)} grup kompetisi/liga.")

    for ul_element in match_lists_ul:
        try:
            # 1. CARI JUDUL LIGA
            # Logika: Judul liga biasanya ada di "atas" elemen UL ini (previous sibling atau parent search)
            # Kita coba cari elemen SectionHeader terdekat di dalam parent yang sama
            
            # Naik ke parent div pembungkus
            parent_container = ul_element.locator("xpath=..") 
            
            # Cari Header Liga di dalam parent tersebut
            league_header = parent_container.locator("a[class*='SectionHeader_link']").first
            
            league_name = "Unknown League"
            league_logo_hd = ""

            if league_header.count() > 0:
                # Ambil nama liga dari h2 di dalam header
                h2_title = parent_container.locator("h2[class*='Title_leftAlign']").first
                if h2_title.count() > 0:
                    league_name = h2_title.text_content().strip()
                
                # Ambil Logo Liga
                img_league = league_header.locator("img").first
                if img_league.count() > 0:
                    src = img_league.get_attribute("src")
                    league_logo_hd = get_high_res_image(src)

            # 2. ITERASI PERTANDINGAN DI DALAM LIST INI
            cards = ul_element.locator("li a[class*='MatchCard_matchCard']").all()
            
            for card in cards:
                try:
                    match_link = "https://onefootball.com" + card.get_attribute("href")
                    
                    # Ambil Nama Tim
                    team_names_loc = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__name']")
                    all_teams = team_names_loc.all_text_contents()
                    
                    if len(all_teams) < 2:
                        continue # Skip kalau data gak lengkap
                        
                    home_name = all_teams[0].strip()
                    away_name = all_teams[1].strip()

                    # Ambil Logo Tim & HD-kan
                    logos_loc = card.locator("img[class*='ImageWithSets_of-image__img']")
                    home_logo_raw = logos_loc.nth(0).get_attribute("src") if logos_loc.count() > 0 else ""
                    away_logo_raw = logos_loc.nth(1).get_attribute("src") if logos_loc.count() > 1 else ""
                    
                    home_logo_hd = get_high_res_image(home_logo_raw)
                    away_logo_hd = get_high_res_image(away_logo_raw)

                    # Ambil Waktu & Tanggal
                    # Penting: Ambil atribut datetime, bukan teks "Besok"/"Hari ini"
                    time_elem = card.locator("time").first
                    iso_time = ""
                    wib_info = {"date_display": date_str, "time_display": "TBD"} # Default
                    
                    if time_elem.count() > 0:
                        iso_time = time_elem.get_attribute("datetime") # Format: 2026-01-07T17:30:00Z
                        if iso_time:
                            wib_info = parse_iso_date_to_wib(iso_time)

                    # Ambil Skor (Jika live/selesai)
                    scores_loc = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__score']")
                    scores = scores_loc.all_text_contents()
                    home_score = scores[0] if len(scores) > 0 else "-"
                    away_score = scores[1] if len(scores) > 1 else "-"
                    
                    # Cek Status
                    status = "Jadwal"
                    if home_score != "-" and away_score != "-":
                        status = "Selesai/Live"

                    # Simpan Data
                    match_data = {
                        "league_name": league_name,
                        "league_logo": league_logo_hd,
                        "match_date": wib_info['date_display'], # Tanggal sesuai WIB
                        "match_time": wib_info['time_display'], # Jam sesuai WIB
                        "home_team": home_name,
                        "home_logo": home_logo_hd,
                        "home_score": home_score,
                        "away_team": away_name,
                        "away_logo": away_logo_hd,
                        "away_score": away_score,
                        "link": match_link
                    }
                    
                    matches_list.append(match_data)
                    
                except Exception as e:
                    print(f"Error parsing kartu match: {e}")
                    continue

        except Exception as e:
            print(f"Error parsing grup liga: {e}")
            continue

    return matches_list

def run():
    with sync_playwright() as p:
        # Setup Browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 1000}, # Layar lebar biar layout desktop
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        all_matches = []
        
        # --- LOGIKA LOOPING 3 HARI ---
        today = datetime.now()
        
        for i in range(3):
            # i=0 (Hari ini), i=1 (Besok), i=2 (Lusa)
            current_check_date = today + timedelta(days=i)
            date_url_format = current_check_date.strftime("%Y-%m-%d")
            
            # Jalankan scrape
            daily_data = scrape_matches_by_date(page, date_url_format)
            all_matches.extend(daily_data)
            
            print(f"   ✅ Berhasil ambil {len(daily_data)} pertandingan untuk tanggal URL {date_url_format}")

        # Simpan JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_matches, f, indent=2, ensure_ascii=False)

        print(f"\n🎉 SELESAI! Total {len(all_matches)} pertandingan disimpan di {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    run()
