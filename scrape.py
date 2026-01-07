import json
import os
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
# Set Timezone WIB (UTC+7)
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Mengubah URL thumbnail menjadi HD (128px)."""
    if not url: return ""
    try:
        # Ganti ukuran w=... menjadi w=128
        new_url = re.sub(r'w=\d+', 'w=128', url)
        new_url = re.sub(r'h=\d+', 'h=128', new_url)
        return new_url
    except:
        return url

def parse_iso_date_to_wib(iso_date_str):
    """Ubah waktu ISO UTC ke format Tanggal & Jam WIB."""
    try:
        if not iso_date_str: return {"date": "TBD", "time": "TBD"}
        
        # Bersihkan string ISO
        clean_iso = iso_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        
        # Konversi ke WIB
        dt_wib = dt_utc.astimezone(WIB)
        
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M"),
            "timestamp": dt_wib.timestamp() # Untuk sorting
        }
    except:
        return {"date": "TBD", "time": "TBD", "timestamp": 0}

def extract_matches_recursively(data):
    """
    Fungsi 'Sapu Jagat': Mencari objek 'matchCards' di kedalaman JSON manapun.
    Ini menjamin data Lecce vs Roma pasti ketemu di mana pun dia sembunyi.
    """
    extracted_matches = []

    if isinstance(data, dict):
        # Cek apakah dictionary ini adalah container Match Cards
        if 'matchCards' in data and isinstance(data['matchCards'], list):
            # Kita menemukan "Sarang" Pertandingan!
            
            # 1. Ambil Info Liga dari Header di level yang sama
            header = data.get('sectionHeader', {})
            league_name = header.get('title', 'Unknown League')
            league_round = header.get('subtitle', '') # Matchday/Round
            
            # Ambil Logo Liga
            league_logo_obj = header.get('entityLogo', {}) or {}
            league_logo = get_high_res_image(league_logo_obj.get('path', ''))

            # 2. Loop setiap kartu pertandingan
            for card in data['matchCards']:
                try:
                    # Pastikan ini kartu pertandingan (ada homeTeam)
                    if 'homeTeam' not in card:
                        continue
                        
                    # Parse Waktu
                    kickoff = card.get('kickoff')
                    wib_info = parse_iso_date_to_wib(kickoff)

                    # Parse Tim Home
                    home = card.get('homeTeam', {})
                    home_img = home.get('imageObject', {}) or {}
                    
                    # Parse Tim Away
                    away = card.get('awayTeam', {})
                    away_img = away.get('imageObject', {}) or {}

                    match_item = {
                        "league_name": league_name,
                        "league_round": league_round,
                        "league_logo": league_logo,
                        "match_date": wib_info['date'],
                        "match_time": wib_info['time'],
                        "timestamp_sort": wib_info['timestamp'],
                        "home_team": home.get('name', ''),
                        "home_logo": get_high_res_image(home_img.get('path', '')),
                        "home_score": home.get('score', ''),
                        "away_team": away.get('name', ''),
                        "away_logo": get_high_res_image(away_img.get('path', '')),
                        "away_score": away.get('score', ''),
                        "link": "https://onefootball.com" + card.get('link', '')
                    }
                    extracted_matches.append(match_item)
                except Exception as e:
                    continue 

        # Jika bukan container match, cari terus ke anak-anaknya
        for key, value in data.items():
            extracted_matches.extend(extract_matches_recursively(value))

    elif isinstance(data, list):
        # Jika list, iterasi setiap item
        for item in data:
            extracted_matches.extend(extract_matches_recursively(item))

    return extracted_matches

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper OneFootball (Metode: Window Object Injection)...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 1. Buka Halaman
        url = "https://onefootball.com/id/pertandingan"
        try:
            # Kita pakai domcontentloaded, cukup sampai struktur HTML siap
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"❌ Error loading page: {e}")
            browser.close()
            return

        # 2. AMBIL DATA JSON LANGSUNG DARI MEMORI BROWSER
        # Ini adalah kunci keberhasilan. Kita ambil objek __NEXT_DATA__
        print("📦 Mengambil data internal Next.js...")
        
        try:
            # Eksekusi script di browser untuk mengambil data JSON
            raw_json_data = page.evaluate("() => window.__NEXT_DATA__")
            
            if not raw_json_data:
                # Fallback: Coba ambil dari text script tag jika window object null
                print("⚠️ Window object kosong, mencoba ambil dari tag script...")
                json_str = page.locator("#__NEXT_DATA__").text_content()
                raw_json_data = json.loads(json_str)

            if raw_json_data:
                # 3. Ekstrak Data Menggunakan Fungsi Rekursif
                print("🔍 Membongkar struktur JSON...")
                all_matches = extract_matches_recursively(raw_json_data)
                
                # Filter data kosong/invalid (misal iklan yang menyerupai match)
                valid_matches = [m for m in all_matches if m['home_team'] and m['away_team']]
                
                # 4. Sorting
                # Urutkan berdasarkan Waktu (Timestamp) lalu Nama Liga
                valid_matches.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
                
                # Hapus key timestamp_sort sebelum disimpan agar JSON bersih
                for m in valid_matches:
                    del m['timestamp_sort']

                # 5. Simpan
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)

                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(valid_matches, f, indent=2, ensure_ascii=False)

                print(f"\n✅ SUKSES! {len(valid_matches)} pertandingan ditemukan dan disimpan.")
                print(f"📁 File tersimpan di: {OUTPUT_FILE}")
                
            else:
                print("❌ Gagal mendapatkan data JSON dari website.")

        except Exception as e:
            print(f"❌ Terjadi kesalahan fatal saat ekstraksi: {e}")

        browser.close()

if __name__ == "__main__":
    run()
