import json
import os
import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_hari_ini.json")

def get_high_res_image(url):
    """Ubah URL gambar jadi HD (128px)."""
    if not url: return ""
    # Ganti ukuran w=... menjadi w=128
    new_url = re.sub(r'w=\d+', 'w=128', url)
    new_url = re.sub(r'h=\d+', 'h=128', new_url)
    return new_url

def scroll_to_bottom(page):
    """
    Scroll perlahan sampai mentok bawah untuk memicu semua data muncul.
    """
    print("   ⬇️  Sedang scroll halaman agar semua data muncul...")
    
    last_height = page.evaluate("document.body.scrollHeight")
    no_change_count = 0
    
    while True:
        # Scroll turun 800px
        page.mouse.wheel(0, 800)
        time.sleep(1) # Tunggu loading
        
        new_height = page.evaluate("document.body.scrollHeight")
        
        if new_height == last_height:
            # Jika tinggi tidak berubah, coba tunggu lebih lama (cek loading)
            no_change_count += 1
            # print(f"      ...cek data bawah ({no_change_count}/4)")
            time.sleep(1.5)
            
            # Jika 4x cek tidak ada perubahan, berarti sudah mentok
            if no_change_count >= 4:
                print("      ✅ Halaman sudah mentok bawah.")
                break
        else:
            no_change_count = 0
            last_height = new_height

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper OneFootball (Target: Hari Ini - Full Data)...")
        
        # SETTING BROWSER KE INDONESIA (PENTING!)
        # Ini membuat OneFootball merender jam & tanggal sesuai WIB otomatis
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 1000},
            locale="id-ID",
            timezone_id="Asia/Jakarta" 
        )
        page = context.new_page()

        # Akses URL Utama (Otomatis hari ini)
        url = "https://onefootball.com/id/pertandingan"
        
        try:
            # Gunakan domcontentloaded agar lebih cepat (tidak tunggu iklan)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("div[class*='matchCardsList']", timeout=20000)
        except Exception as e:
            print(f"❌ Gagal memuat halaman: {e}")
            browser.close()
            return

        # 1. Scroll sampai habis dulu biar semua match ke-load
        scroll_to_bottom(page)
        
        matches_data = []
        seen_links = set() # Untuk mencegah duplikat
        
        # 2. Ambil semua container Liga
        league_containers = page.locator("div[class*='matchCardsList']").all()
        print(f"📦 Mengambil data dari {len(league_containers)} kompetisi...")

        for container in league_containers:
            try:
                # --- INFO LIGA & ROUND ---
                header_section = container.locator("div[class*='SectionHeader_container']").first
                
                league_name = "Unknown League"
                league_logo = ""
                league_round = "" 

                if header_section.count() > 0:
                    # Nama Liga
                    h2 = header_section.locator("h2").first
                    if h2.count() > 0:
                        league_name = h2.text_content().strip()
                    
                    # Round / Matchday
                    h3 = header_section.locator("h3[class*='SectionHeader_subtitle']").first
                    if h3.count() > 0:
                        league_round = h3.text_content().strip()
                    
                    # Logo Liga
                    img = header_section.locator("img").first
                    if img.count() > 0:
                        league_logo = get_high_res_image(img.get_attribute("src"))

                # --- LIST PERTANDINGAN ---
                cards = container.locator("li a[class*='MatchCard_matchCard']").all()
                
                for card in cards:
                    try:
                        # Cek Link untuk Filter Duplikat
                        link = "https://onefootball.com" + card.get_attribute("href")
                        if link in seen_links:
                            continue # Skip jika sudah ada
                        seen_links.add(link)

                        # Nama Tim
                        teams_els = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__name']").all()
                        if len(teams_els) < 2: continue
                        
                        home_team = teams_els[0].text_content().strip()
                        away_team = teams_els[1].text_content().strip()
                        
                        # Logo Tim
                        imgs_els = card.locator("img[class*='ImageWithSets_of-image__img']").all()
                        home_logo = get_high_res_image(imgs_els[0].get_attribute("src")) if len(imgs_els) > 0 else ""
                        away_logo = get_high_res_image(imgs_els[1].get_attribute("src")) if len(imgs_els) > 1 else ""
                        
                        # Waktu (Ambil datetime attribute untuk akurasi)
                        # Karena browser sudah setting Asia/Jakarta, kita ambil stringnya saja
                        # Tapi lebih aman parse ISO nya
                        time_el = card.locator("time").first
                        match_date = ""
                        match_time = ""
                        
                        if time_el.count() > 0:
                            iso_string = time_el.get_attribute("datetime") # ex: 2026-01-08T00:30:00Z
                            if iso_string:
                                # Parse ISO UTC
                                dt_utc = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
                                # Convert manual ke WIB (UTC+7) di Python agar 100% akurat
                                # meskipun browser sudah setting Jakarta, atribut HTML biasanya tetap UTC
                                dt_wib = dt_utc.astimezone(datetime.now().astimezone().tzinfo) 
                                # Hack: Gunakan logika sederhana tambah 7 jam jika server UTC
                                # Atau parsing string sederhana
                                
                                match_date = dt_utc.strftime("%Y-%m-%d")
                                match_time = dt_utc.strftime("%H:%M")
                                
                                # Note: Karena kita set context Playwright ke Asia/Jakarta, 
                                # text content di layar sebenarnya sudah WIB. 
                                # Tapi mengambil atribut datetime lebih stabil untuk mesin.
                                # Kode di bawah mengkonversi datetime UTC ke string output.
                                
                                # Simple conversion logic
                                from datetime import timedelta
                                dt_wib_manual = dt_utc + timedelta(hours=7)
                                match_date = dt_wib_manual.strftime("%Y-%m-%d")
                                match_time = dt_wib_manual.strftime("%H:%M")

                        # Skor
                        scores_els = card.locator("span[class*='SimpleMatchCardTeam_simpleMatchCardTeam__score']").all()
                        home_score = scores_els[0].text_content().strip() if len(scores_els) > 0 else ""
                        away_score = scores_els[1].text_content().strip() if len(scores_els) > 1 else ""
                        
                        match_item = {
                            "league_name": league_name,
                            "league_round": league_round,
                            "league_logo": league_logo,
                            "match_date": match_date,
                            "match_time": match_time,
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
                        continue

            except Exception:
                continue

        # Simpan JSON
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        # Sorting agar rapi (Tanggal -> Jam -> Liga)
        matches_data.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(matches_data, f, indent=2, ensure_ascii=False)

        print(f"\n✅ BERHASIL! {len(matches_data)} pertandingan tersimpan tanpa duplikat.")
        browser.close()

if __name__ == "__main__":
    run()
