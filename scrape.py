import json
import os
import time
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_lengkap.json")
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Ubah URL gambar jadi HD (128px)."""
    if not url: return ""
    new_url = re.sub(r'w=\d+', 'w=128', url)
    new_url = re.sub(r'h=\d+', 'h=128', new_url)
    return new_url

def parse_iso_date_to_wib(iso_date_str):
    """Ubah waktu ISO ke format WIB yang mudah dibaca."""
    try:
        clean_iso = iso_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        dt_wib = dt_utc.astimezone(WIB)
        return {
            "iso": dt_wib.isoformat(),
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M")
        }
    except:
        return {"iso": "", "date": "TBD", "time": "TBD"}

def slow_scroll(page):
    """
    Scroll perlahan sampai paling bawah untuk memicu lazy loading.
    Teknik ini penting agar semua pertandingan muncul.
    """
    print("   ⬇️  Sedang memuat semua pertandingan (scrolling)...")
    last_height = page.evaluate("document.body.scrollHeight")
    
    while True:
        # Scroll turun 500px setiap kali
        page.mouse.wheel(0, 500)
        time.sleep(0.5) # Tunggu sebentar setiap scroll
        
        new_height = page.evaluate("document.body.scrollHeight")
        current_scroll = page.evaluate("window.scrollY + window.innerHeight")
        
        # Jika sudah mentok bawah atau tidak ada perubahan tinggi
        if current_scroll >= new_height:
            # Coba tunggu sebentar lagi barangkali ada loading spinner
            time.sleep(2)
            new_height_after_wait = page.evaluate("document.body.scrollHeight")
            if new_height_after_wait == new_height:
                break # Selesai scroll
            else:
                last_height = new_height_after_wait
        else:
            last_height = new_height

def scrape_day(page, date_obj):
    date_str = date_obj.strftime("%Y-%m-%d")
    url = f"https://onefootball.com/id/pertandingan?date={date_str}"
    
    print(f"\n[{date_str}] Mengakses URL...")
    page.goto(url, wait_until="networkidle", timeout=90000)
    
    # Lakukan Slow Scroll untuk load semua data
    slow_scroll(page)
    
    matches_on_page = []
    
    # Ambil Container Liga
    # Struktur: Container -> Header (Nama Liga & Matchday) -> List Match
    league_containers = page.locator("div[class*='matchCardsList']").all()
    
    print(f"   Ditemukan {len(league_containers)} seksi liga.")

    for container in league_containers:
        try:
            # 1. AMBIL INFO LIGA & MATCHDAY
            # Biasanya ada di Header link atau div
            header_section = container.locator("div[class*='SectionHeader_container']").first
            
            league_name = "Unknown League"
            league_logo = ""
            match_round = "" # Ini untuk "Matchday 21" atau "Round 1"

            if header_section.count() > 0:
                # Nama Liga (H2)
                h2 = header_section.locator("h2").first
                if h2.count() > 0:
                    league_name = h2.text_content().strip()
                
                # Subtitle / Matchday (H3) - Ini target baru kita
                h3 = header_section.locator("h3[class*='SectionHeader_subtitle']").first
                if h3.count() > 0:
                    match_round = h3.text_content().strip()
                
                # Logo Liga
                img = header_section.locator("img").first
                if img.count() > 0:
                    league_logo = get_high_res_image(img.get_attribute("src"))

            # 2. AMBIL LIST MATCH DI LIGA INI
            cards = container.locator("li a[class*='MatchCard_matchCard']").all()
            
            for card in cards:
                try:
                    # Parse Data Tim
                    teams_els = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__name']").all()
                    if len(teams_els) < 2: continue
                    
                    home_team = teams_els[0].text_content().strip()
                    away_team = teams_els[1].text_content().strip()
                    
                    # Parse Logo Tim (HD)
                    imgs_els = card.locator("img[class*='ImageWithSets_of-image__img']").all()
                    home_logo = get_high_res_image(imgs_els[0].get_attribute("src")) if len(imgs_els) > 0 else ""
                    away_logo = get_high_res_image(imgs_els[1].get_attribute("src")) if len(imgs_els) > 1 else ""
                    
                    # Parse Waktu & Tanggal
                    time_el = card.locator("time").first
                    wib_data = {"date": date_str, "time": "TBD"}
                    if time_el.count() > 0:
                        iso_time = time_el.get_attribute("datetime")
                        if iso_time:
                            wib_data = parse_iso_date_to_wib(iso_time)
                    
                    # Parse Skor
                    scores_els = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__score']").all()
                    home_score = scores_els[0].text_content().strip() if len(scores_els) > 0 else ""
                    away_score = scores_els[1].text_content().strip() if len(scores_els) > 1 else ""
                    
                    link = "https://onefootball.com" + card.get_attribute("href")

                    match_data = {
                        "match_date": wib_data['date'], # Tanggal (YYYY-MM-DD)
                        "match_time": wib_data['time'], # Jam (HH:MM)
                        "league_name": league_name,
                        "league_round": match_round,    # Data Matchday/Round
                        "league_logo": league_logo,
                        "home_team": home_team,
                        "home_logo": home_logo,
                        "home_score": home_score,
                        "away_team": away_team,
                        "away_logo": away_logo,
                        "away_score": away_score,
                        "link": link
                    }
                    matches_on_page.append(match_data)
                    
                except Exception:
                    continue

        except Exception:
            continue
            
    return matches_on_page

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Viewport tinggi agar memuat lebih banyak konten awal
        context = browser.new_context(viewport={"width": 1366, "height": 1000}) 
        page = context.new_page()

        all_data = []
        today = datetime.now()

        # Scrape 3 Hari (Hari ini, Besok, Lusa)
        for i in range(3):
            target_date = today + timedelta(days=i)
            day_matches = scrape_day(page, target_date)
            all_data.extend(day_matches)
            print(f"   ✅ Tersimpan {len(day_matches)} pertandingan.")

        # --- SORTING FINAL ---
        # Mengurutkan berdasarkan:
        # 1. Tanggal Pertandingan (match_date)
        # 2. Jam Pertandingan (match_time)
        # 3. Nama Liga
        print("\n🔄 Mengurutkan data...")
        all_data.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))

        # Simpan JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)

        print(f"\n🎉 SELESAI! {len(all_data)} pertandingan tersimpan dan terurut di {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    run()
