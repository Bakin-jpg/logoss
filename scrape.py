import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

URL = "https://onefootball.com/id/pertandingan"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "matches.json")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"Mengakses {URL}...")
        page.goto(URL, wait_until="networkidle")

        # Scroll perlahan ke bawah untuk memicu lazy loading gambar
        # OneFootball memuat gambar saat di-scroll
        for i in range(5): 
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(1000)

        matches_data = []

        # UPDATE SELECTOR:
        # Berdasarkan HTML kamu, kartu pertandingan ada di dalam tag <a> 
        # dengan class yang mengandung "MatchCard_matchCard"
        match_cards = page.locator("a[class*='MatchCard_matchCard']").all()

        print(f"Ditemukan {len(match_cards)} kartu pertandingan.")

        for card in match_cards:
            try:
                # 1. Ambil Link Pertandingan
                link = "https://onefootball.com" + card.get_attribute("href")

                # 2. Ambil Nama Tim
                # Class: SimpleMatchCardTeam_simpleMatchCardTeam__name...
                team_names_loc = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__name']")
                team_names = team_names_loc.all_text_contents()
                
                # 3. Ambil Logo Tim
                # Class: ImageWithSets_of-image__img...
                # Kita ambil atribut 'src' dari tag <img>
                logos_loc = card.locator("img[class*='ImageWithSets_of-image__img']")
                logos = [img.get_attribute("src") for img in logos_loc.all()]

                # 4. Ambil Waktu / Skor
                # Waktu biasanya ada di tag <time> atau skor di span score
                match_time = "N/A"
                time_loc = card.locator("time")
                if time_loc.count() > 0:
                    match_time = time_loc.first.get_attribute("datetime") or time_loc.first.text_content()
                
                # Coba ambil skor jika ada (match sudah berjalan/selesai)
                scores_loc = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__score']")
                scores = scores_loc.all_text_contents()

                # Validasi data tim (harus ada 2 tim)
                if len(team_names) >= 2:
                    home_team = team_names[0].strip()
                    away_team = team_names[1].strip()
                else:
                    continue # Skip jika gagal ambil nama tim

                # Validasi data logo
                home_logo = logos[0] if len(logos) >= 1 else ""
                away_logo = logos[1] if len(logos) >= 2 else ""

                # Format Waktu/Skor
                status = match_time
                if len(scores) >= 2 and scores[0].strip() != "":
                    status = f"{scores[0]} - {scores[1]}"

                match_info = {
                    "home_team": home_team,
                    "home_logo": home_logo,
                    "away_team": away_team,
                    "away_logo": away_logo,
                    "status_or_time": status,
                    "match_link": link,
                    "scraped_at": datetime.now().isoformat()
                }

                matches_data.append(match_info)
                # Print log kecil biar tau progress
                print(f"Scraped: {home_team} vs {away_team}")

            except Exception as e:
                # Jangan stop script kalau ada 1 error, lanjut ke kartu berikutnya
                print(f"Error pada satu kartu: {e}")
                continue

        # Simpan ke JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matches_data, f, indent=2, ensure_ascii=False)

        print(f"Selesai! {len(matches_data)} pertandingan tersimpan di {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    run()
