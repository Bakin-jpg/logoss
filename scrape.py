import json
import os
import time
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_hari_ini.json")
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Ubah URL gambar jadi HD (128px)."""
    if not url: return ""
    # Ganti ukuran w=... menjadi w=128
    new_url = re.sub(r'w=\d+', 'w=128', url)
    new_url = re.sub(r'h=\d+', 'h=128', new_url)
    return new_url

def parse_iso_date_to_wib(iso_date_str):
    """Ubah waktu ISO ke format WIB."""
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

def scroll_to_bottom(page):
    """
    Scroll agresif tapi sabar untuk memuat SEMUA data.
    """
    print("   ⬇️  Mulai scroll halaman...")
    
    last_height = page.evaluate("document.body.scrollHeight")
    retries = 0
    
    while True:
        # Scroll ke bawah 800px
        page.mouse.wheel(0, 800)
        time.sleep(0.8) # Tunggu loading sebentar
        
        new_height = page.evaluate("document.body.scrollHeight")
        current_pos = page.evaluate("window.scrollY + window.innerHeight")
        
        # Cek apakah tinggi halaman bertambah ATAU belum mentok
        if new_height == last_height:
            # Jika tinggi tidak berubah, cek apakah kita sudah di paling bawah
            if current_pos >= new_height - 50:
                retries += 1
                print(f"      ...menunggu loading data ({retries}/5)")
                time.sleep(2) # Tunggu lebih lama (2 detik)
                
                # Cek ulang tinggi setelah menunggu
                new_height_after_wait = page.evaluate("document.body.scrollHeight")
                
                if new_height_after_wait > last_height:
                    # Ada data baru muncul! Reset retry
                    last_height = new_height_after_wait
                    retries = 0
                    continue
                
                if retries >= 5:
                    print("      ✅ Halaman sudah mentok bawah.")
                    break
        else:
            last_height = new_height
            retries = 0

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper OneFootball (Hari Ini)...")
        
        browser = p.chromium.launch(headless=True)
        # Gunakan viewport tinggi agar memuat banyak konten di awal
        context = browser.new_context(viewport={"width": 1366, "height": 1200})
        page = context.new_page()

        # URL Halaman "Hari Ini"
        url = "https://onefootball.com/id/pertandingan"
        
        try:
            # PENTING: wait_until='domcontentloaded' agar tidak timeout nunggu iklan
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Tunggu elemen list pertandingan muncul maksimal 15 detik
            page.wait_for_selector("div[class*='matchCardsList']", timeout=15000)
            
        except Exception as e:
            print(f"❌ Error Loading Page: {e}")
            browser.close()
            return

        # Scroll sampai habis
        scroll_to_bottom(page)
        
        matches_data = []
        
        # Ambil semua kontainer Liga
        league_containers = page.locator("div[class*='matchCardsList']").all()
        print(f"📦 Ditemukan {len(league_containers)} kompetisi/liga hari ini.")

        for container in league_containers:
            try:
                # --- AMBIL INFO LIGA ---
                header_section = container.locator("div[class*='SectionHeader_container']").first
                
                league_name = "Unknown League"
                league_logo = ""
                league_round = "" 

                if header_section.count() > 0:
                    # Nama Liga
                    h2 = header_section.locator("h2").first
                    if h2.count() > 0:
                        league_name = h2.text_content().strip()
                    
                    # Round / Matchday (Contoh: "Matchday 19")
                    h3 = header_section.locator("h3[class*='SectionHeader_subtitle']").first
                    if h3.count() > 0:
                        league_round = h3.text_content().strip()
                    
                    # Logo Liga
                    img = header_section.locator("img").first
                    if img.count() > 0:
                        league_logo = get_high_res_image(img.get_attribute("src"))

                # --- AMBIL LIST PERTANDINGAN ---
                cards = container.locator("li a[class*='MatchCard_matchCard']").all()
                
                for card in cards:
                    try:
                        # Nama Tim
                        teams_els = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__name']").all()
                        if len(teams_els) < 2: continue # Skip jika data rusak
                        
                        home_team = teams_els[0].text_content().strip()
                        away_team = teams_els[1].text_content().strip()
                        
                        # Logo Tim (HD)
                        imgs_els = card.locator("img[class*='ImageWithSets_of-image__img']").all()
                        home_logo = get_high_res_image(imgs_els[0].get_attribute("src")) if len(imgs_els) > 0 else ""
                        away_logo = get_high_res_image(imgs_els[1].get_attribute("src")) if len(imgs_els) > 1 else ""
                        
                        # Waktu & Tanggal
                        time_el = card.locator("time").first
                        # Default jika tidak ada waktu (misal Tunda)
                        wib_info = {"date": datetime.now().strftime("%Y-%m-%d"), "time": "TBD"}
                        
                        if time_el.count() > 0:
                            iso_time = time_el.get_attribute("datetime")
                            if iso_time:
                                wib_info = parse_iso_date_to_wib(iso_time)
                        
                        # Skor (Jika ada)
                        scores_els = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__score']").all()
                        home_score = scores_els[0].text_content().strip() if len(scores_els) > 0 else ""
                        away_score = scores_els[1].text_content().strip() if len(scores_els) > 1 else ""
                        
                        # Link
                        link = "https://onefootball.com" + card.get_attribute("href")

                        # Susun Data
                        match_item = {
                            "league_name": league_name,
                            "league_round": league_round,
                            "league_logo": league_logo,
                            "match_date": wib_info['date'],
                            "match_time": wib_info['time'],
                            "home_team": home_team,
                            "home_logo": home_logo,
                            "home_score": home_score,
                            "away_team": away_team,
                            "away_logo": away_logo,
                            "away_score": away_score,
                            "link": link
                        }
                        matches_data.append(match_item)
                        
                    except Exception:
                        continue # Skip 1 kartu error

            except Exception:
                continue # Skip 1 liga error

        # Simpan JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        # Sorting: Liga -> Jam
        matches_data.sort(key=lambda x: (x['league_name'], x['match_time']))

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matches_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ BERHASIL! {len(matches_data)} pertandingan tersimpan di {OUTPUT_FILE}")
        browser.close()

if __name__ == "__main__":
    run()
