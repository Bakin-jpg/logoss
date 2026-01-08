import json
import os
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

# --- HELPER FUNCTIONS (TIDAK BERUBAH) ---
def get_high_res_image(url):
    if not url: return ""
    try:
        import re
        new_url = re.sub(r'w=\d+', 'w=128', url)
        new_url = re.sub(r'h=\d+', 'h=128', new_url)
        return new_url
    except:
        return url

def parse_iso_date_to_wib(iso_date_str):
    try:
        if not iso_date_str: return {"date": "TBD", "time": "TBD", "ts": 0}
        clean_iso = iso_date_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_iso)
        dt_wib = dt_utc.astimezone(WIB)
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M"),
            "ts": dt_wib.timestamp()
        }
    except:
        return {"date": "TBD", "time": "TBD", "ts": 0}

def find_matches_in_json(data, matches_found):
    """
    Fungsi Rekursif: Mencari objek pertandingan di kedalaman JSON manapun.
    """
    if isinstance(data, dict):
        # Cek apakah ini match object
        if 'homeTeam' in data and 'awayTeam' in data and 'kickoff' in data:
            matches_found.append(data)
        
        # Cek container matchCards untuk mengambil info liga
        elif 'matchCards' in data and isinstance(data['matchCards'], list):
            header = data.get('sectionHeader', {})
            league_info = {
                'name': header.get('title', ''),
                'round': header.get('subtitle', ''),
                'logo': header.get('entityLogo', {}).get('path', '')
            }
            
            for card in data['matchCards']:
                if isinstance(card, dict):
                    if 'league_info' not in card: 
                        card['league_info'] = league_info
                    find_matches_in_json(card, matches_found)

        for k, v in data.items():
            find_matches_in_json(v, matches_found)
            
    elif isinstance(data, list):
        for item in data:
            find_matches_in_json(item, matches_found)

# --- FITUR BARU: AUTO SCROLL ---
def auto_scroll(page):
    """Melakukan scroll ke bawah secara bertahap untuk memancing Lazy Load."""
    print("⬇️  Sedang melakukan auto-scroll untuk memuat data...")
    
    # Get initial height
    last_height = page.evaluate("document.body.scrollHeight")
    
    while True:
        # Scroll ke bawah
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # Tunggu loading (3 detik agar aman)
        page.wait_for_timeout(3000)
        
        # Hitung height baru
        new_height = page.evaluate("document.body.scrollHeight")
        
        # Jika height tidak bertambah, berarti sudah mentok bawah
        if new_height == last_height:
            # Coba scroll up dikit lalu down lagi (pancingan extra)
            page.mouse.wheel(0, -500)
            page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            final_height = page.evaluate("document.body.scrollHeight")
            if final_height == new_height:
                break
        
        last_height = new_height
    print("✅ Auto-scroll selesai. Halaman termuat penuh.")

def run():
    collected_json_data = []

    # --- FITUR BARU: INTERCEPTOR ---
    def handle_response(response):
        """Menangkap semua respons JSON dari jaringan (API/GraphQL)."""
        # Kita hanya ingin file JSON atau respons GraphQL
        if "application/json" in response.headers.get("content-type", ""):
            try:
                # Ambil body JSON
                data = response.json()
                collected_json_data.append(data)
            except:
                pass

    with sync_playwright() as p:
        print("🚀 Memulai Scraper OneFootball (Mode Canggih: Sniffing & Scrolling)...")
        
        browser = p.chromium.launch(headless=False) # Ubah ke False jika ingin melihat prosesnya
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        # Aktifkan Interceptor SEBELUM buka page
        page = context.new_page()
        page.on("response", handle_response)

        try:
            page.goto("https://onefootball.com/id/pertandingan", wait_until="domcontentloaded", timeout=60000)
            
            # 1. Ambil Data Awal (__NEXT_DATA__)
            print("📦 Mengambil data awal...")
            try:
                initial_json = page.locator("#__NEXT_DATA__").text_content()
                if initial_json:
                    collected_json_data.append(json.loads(initial_json))
            except:
                print("⚠️ Warning: __NEXT_DATA__ tidak ditemukan, mengandalkan Network Sniffing saja.")

            # 2. Lakukan Auto Scroll untuk memicu API call
            auto_scroll(page)

            # 3. Proses SEMUA JSON yang terkumpul
            print(f"📊 Memproses {len(collected_json_data)} paket data JSON yang tertangkap...")
            
            raw_matches = []
            for json_source in collected_json_data:
                find_matches_in_json(json_source, raw_matches)

            print(f"🔍 Total ditemukan {len(raw_matches)} objek pertandingan mentah.")

            clean_matches = []
            seen_links = set()

            for m in raw_matches:
                try:
                    # Filter Duplikat (Sangat penting karena sniffing bisa menangkap data sama berkali-kali)
                    link = "https://onefootball.com" + m.get('link', '')
                    if link in seen_links: continue
                    
                    # Validasi minimal: harus ada nama tim
                    if not m.get('homeTeam') or not m.get('awayTeam'): continue
                    
                    seen_links.add(link)

                    # Parse Waktu
                    kickoff = m.get('kickoff', '')
                    wib = parse_iso_date_to_wib(kickoff)

                    # Logika Metadata Liga (sama seperti sebelumnya)
                    league_meta = m.get('league_info', {})
                    league_name = league_meta.get('name', 'Unknown/Highlight')
                    if not league_name or league_name == 'Unknown/Highlight':
                            league_name = m.get('competitionName', 'Kompetisi Lain')

                    league_round = league_meta.get('round', '')
                    league_logo = get_high_res_image(league_meta.get('logo', ''))
                    
                    if not league_logo:
                            league_logo = "https://images.onefootball.com/icons/leagueColoredCompetition/128/13.png"

                    home = m.get('homeTeam', {})
                    away = m.get('awayTeam', {})
                    
                    item = {
                        "league_name": league_name,
                        "league_round": league_round,
                        "league_logo": league_logo,
                        "match_date": wib['date'],
                        "match_time": wib['time'],
                        "sort_ts": wib['ts'],
                        "home_team": home.get('name', ''),
                        "home_logo": get_high_res_image(home.get('imageObject', {}).get('path', '')),
                        "home_score": home.get('score', ''),
                        "away_team": away.get('name', ''),
                        "away_logo": get_high_res_image(away.get('imageObject', {}).get('path', '')),
                        "away_score": away.get('score', ''),
                        "link": link
                    }
                    clean_matches.append(item)
                except Exception as e:
                    continue

            # Sorting Final
            clean_matches.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
            
            # Hapus helper sorting
            for match in clean_matches:
                del match['sort_ts']

            # Simpan
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR)
                
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                
            print(f"✅ BERHASIL! {len(clean_matches)} pertandingan valid tersimpan di {OUTPUT_FILE}.")

        except Exception as e:
            print(f"❌ Error Fatal: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
