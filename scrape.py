import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

# Konfigurasi URL dan Selector
# Catatan: Class name di OneFootball sering berubah (hash). 
# Kita menggunakan pendekatan struktur elemen yang lebih umum.
URL = "https://onefootball.com/id/pertandingan"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "matches.json")

def run():
    with sync_playwright() as p:
        # Launch browser (headless=True untuk GitHub Actions)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"Mengakses {URL}...")
        page.goto(URL, wait_until="networkidle")

        # Scroll ke bawah sedikit untuk memicu lazy loading gambar
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000) # Tunggu 3 detik

        matches_data = []

        # Mencari container pertandingan
        # OneFootball biasanya menggunakan list item <li> atau link <a> untuk match card
        # Kita akan mencari elemen yang memiliki struktur 2 logo tim
        
        # Selector ini mencari elemen kartu pertandingan secara umum
        match_cards = page.locator("a[href*='/pertandingan/']").all()

        print(f"Ditemukan {len(match_cards)} potensi pertandingan.")

        for card in match_cards:
            try:
                # Ambil Link
                link = "https://onefootball.com" + card.get_attribute("href")
                
                # Coba ambil elemen waktu/status
                # Biasanya elemen teks paling atas atau di tengah
                status_element = card.locator("time").first
                match_time = status_element.text_content().strip() if status_element.count() > 0 else "N/A"

                # Ambil Gambar (Logo)
                # Biasanya ada 2 gambar utama dalam kartu pertandingan
                images = card.locator("img").all()
                
                # Filter gambar yang relevan (biasanya ukuran kecil untuk logo)
                logos = [img.get_attribute("src") for img in images if img.get_attribute("src")]
                
                # Ambil Nama Tim
                # Biasanya ada di elemen span atau p
                texts = card.locator("span").all_text_contents()
                # Bersihkan teks kosong
                texts = [t.strip() for t in texts if t.strip()]

                # Logika sederhana untuk menentukan tim (bisa disesuaikan jika struktur berubah)
                home_team = "Unknown"
                away_team = "Unknown"
                home_logo = ""
                away_logo = ""

                if len(logos) >= 2:
                    home_logo = logos[0]
                    away_logo = logos[1]
                
                # Asumsi teks tim biasanya muncul setelah waktu atau di sekitar logo
                # Ini bagian tricky karena struktur OneFootball sangat dinamis
                # Kita ambil 2 teks terpanjang yang kemungkinan adalah nama tim
                team_candidates = [t for t in texts if len(t) > 2 and ":" not in t]
                
                if len(team_candidates) >= 2:
                    home_team = team_candidates[0]
                    away_team = team_candidates[1]

                # Simpan data
                match_info = {
                    "match_time": match_time,
                    "home_team": home_team,
                    "home_logo": home_logo,
                    "away_team": away_team,
                    "away_logo": away_logo,
                    "match_link": link,
                    "scraped_at": datetime.now().isoformat()
                }
                
                matches_data.append(match_info)

            except Exception as e:
                print(f"Error parsing card: {e}")
                continue

        # Simpan ke JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matches_data, f, indent=2, ensure_ascii=False)

        print(f"Berhasil menyimpan {len(matches_data)} jadwal pertandingan ke {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    run()
