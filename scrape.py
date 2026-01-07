import json
import os
import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# Konfigurasi
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola.json")

def get_matches_for_date(page, target_date_str):
    """
    Fungsi untuk scrape satu halaman tanggal tertentu.
    target_date_str format: YYYY-MM-DD
    """
    url = f"https://onefootball.com/id/pertandingan?date={target_date_str}"
    print(f"\n--- Mengakses jadwal tanggal: {target_date_str} ---")
    
    page.goto(url, wait_until="networkidle", timeout=60000)
    
    # Scroll ke bawah berulang kali untuk memicu lazy load semua liga
    for _ in range(5):
        page.mouse.wheel(0, 1500)
        time.sleep(1)
    
    # Tunggu sebentar agar DOM stabil
    time.sleep(2)

    daily_matches = []

    # 1. Cari Container per Kompetisi (Liga)
    # Di OneFootball, setiap liga dibungkus dalam div yang mengandung 'matchCardsList'
    league_containers = page.locator("div[class*='matchCardsList']").all()

    print(f"Ditemukan {len(league_containers)} kompetisi/liga pada tanggal ini.")

    for container in league_containers:
        try:
            # A. Ambil Nama Liga
            # Biasanya ada di dalam SectionHeader h2 atau a href kompetisi
            league_header = container.locator("h2[class*='Title_leftAlign']").first
            
            if league_header.count() == 0:
                # Fallback jika struktur h2 beda
                league_header = container.locator("a[href*='/kompetisi/']").first

            league_name = league_header.text_content().strip() if league_header.count() > 0 else "Kompetisi Lainnya"
            
            # Ambil Logo Liga (Opsional)
            league_logo_loc = container.locator("img[class*='EntityLogo_entityLogoImage']").first
            league_logo = league_logo_loc.get_attribute("src") if league_logo_loc.count() > 0 else ""

            # B. Ambil List Pertandingan di Liga Tersebut
            match_cards = container.locator("li a[class*='MatchCard_matchCard']").all()

            for card in match_cards:
                try:
                    # Link Match
                    link = "https://onefootball.com" + card.get_attribute("href")

                    # Ambil Nama Tim (Home & Away)
                    team_names_loc = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__name']")
                    team_names = team_names_loc.all_text_contents()

                    # Ambil Logo Tim
                    logos_loc = card.locator("img[class*='ImageWithSets_of-image__img']")
                    logos = [img.get_attribute("src") for img in logos_loc.all()]

                    # Ambil Waktu Mentah (ISO format dari tag <time>)
                    time_loc = card.locator("time").first
                    raw_time = ""
                    readable_time = "TBD"
                    
                    if time_loc.count() > 0:
                        raw_time = time_loc.get_attribute("datetime") # ex: 2026-01-07T17:30:00Z
                        
                        # Format ulang jam menjadi HH:MM
                        try:
                            # Parse ISO format sederhana
                            dt_obj = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
                            # Sesuaikan ke WIB (UTC+7) jika perlu, atau ambil jamnya saja
                            # Di sini kita ambil jamnya saja dari string ISO agar aman
                            readable_time = dt_obj.strftime("%H:%M")
                        except:
                            readable_time = time_loc.text_content().strip()
                    
                    # Ambil Skor (Jika sedang main/selesai)
                    scores_loc = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__score']")
                    scores = scores_loc.all_text_contents()
                    home_score = scores[0] if len(scores) > 0 else ""
                    away_score = scores[1] if len(scores) > 1 else ""

                    # Validasi minimal data
                    if len(team_names) >= 2:
                        home_team = team_names[0].strip()
                        away_team = team_names[1].strip()
                    else:
                        continue

                    home_logo = logos[0] if len(logos) >= 1 else ""
                    away_logo = logos[1] if len(logos) >= 2 else ""

                    # Susun Data
                    match_data = {
                        "date": target_date_str,
                        "time": readable_time,
                        "league": league_name,
                        "league_logo": league_logo,
                        "match_title": f"{home_team} vs {away_team}",
                        "home_team": {
                            "name": home_team,
                            "logo": home_logo,
                            "score": home_score
                        },
                        "away_team": {
                            "name": away_team,
                            "logo": away_logo,
                            "score": away_score
                        },
                        "status": "Finished" if home_score != "" else "Scheduled",
                        "link": link
                    }
                    
                    daily_matches.append(match_data)

                except Exception as e:
                    continue # Skip kartu rusak

        except Exception as e:
            print(f"Error parsing league container: {e}")
            continue
            
    return daily_matches

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        all_matches_3_days = []
        
        # Loop untuk 3 hari (Hari ini, Besok, Lusa)
        start_date = datetime.now()
        
        for i in range(3):
            # Hitung tanggal
            current_date = start_date + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d") # Format YYYY-MM-DD untuk URL
            
            # Scrape
            matches = get_matches_for_date(page, date_str)
            all_matches_3_days.extend(matches)

        # Simpan ke JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_matches_3_days, f, indent=2, ensure_ascii=False)

        print(f"\n==========================================")
        print(f"Total jadwal tersimpan: {len(all_matches_3_days)}")
        print(f"Data disimpan di: {OUTPUT_FILE}")
        print(f"==========================================")
        
        browser.close()

if __name__ == "__main__":
    run()
