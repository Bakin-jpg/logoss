import json
import os
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

# Base URL untuk gambar/logo di LiveScore
IMG_BASE_URL = "https://lsm-static-prod.livescore.com/medium/"

def parse_livescore_date(date_str):
    """
    Format LiveScore: YYYYMMDDHHmmss (String). Contoh: 20240520213000
    """
    try:
        if not date_str: return {"date": "TBD", "time": "TBD", "ts": 0}
        
        # LiveScore biasanya menggunakan waktu UTC atau lokal tergantung endpoint
        # Kita asumsikan format standar YYYYMMDDHHmmss
        dt = datetime.strptime(str(date_str), "%Y%m%d%H%M%S")
        
        # Tambahkan timezone UTC (karena biasanya data mentah adalah UTC)
        dt = dt.replace(tzinfo=timezone.utc)
        
        # Konversi ke WIB
        dt_wib = dt.astimezone(WIB)
        
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M"),
            "ts": dt_wib.timestamp()
        }
    except:
        return {"date": "TBD", "time": "TBD", "ts": 0}

def get_logo(team_data):
    """Mengambil URL logo dari data tim."""
    try:
        img_id = team_data.get('Img', '')
        if img_id:
            return f"{IMG_BASE_URL}{img_id}.png"
        return "https://www.livescore.com/ls-web-assets/images/live-score-outlined-74d06.webp" # Default
    except:
        return ""

def find_key_in_json(data, target_key):
    """
    Mencari value dari key tertentu secara rekursif di kedalaman JSON.
    Cocok untuk mencari 'Stages' atau 'stages' di struktur yang berubah-ubah.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if k == target_key:
                return v
            result = find_key_in_json(v, target_key)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_key_in_json(item, target_key)
            if result: return result
    return None

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper LiveScore.com (Deep Search Mode)...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            url = "https://www.livescore.com/id/"
            print(f"🌍 Mengakses {url}...")
            
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            print("📦 Mengekstrak data JSON...")
            try:
                json_str = page.locator("#__NEXT_DATA__").text_content()
                raw_data = json.loads(json_str)
            except:
                print("❌ Gagal mengambil __NEXT_DATA__.")
                raw_data = {}

            clean_matches = []
            
            # --- PENCARIAN CERDAS ---
            # Cari key "Stages" (biasanya kapital di LiveScore) atau "stages"
            print("🔍 Mencari data kompetisi ('Stages')...")
            stages = find_key_in_json(raw_data, 'Stages')
            
            if not stages:
                # Coba lowercase jika kapital tidak ketemu
                stages = find_key_in_json(raw_data, 'stages')

            if stages and isinstance(stages, list):
                print(f"✅ Ditemukan {len(stages)} grup kompetisi.")

                for stage in stages:
                    try:
                        # Info Liga (Kamus Singkatan LiveScore)
                        # Cnm = Country Name, Snm = Stage Name (League), Cid = Country ID
                        country_name = stage.get('Cnm', '')
                        league_name = stage.get('Snm', '')
                        full_league = f"{country_name} - {league_name}" if country_name else league_name
                        
                        # Events = Daftar Pertandingan
                        events = stage.get('Events', [])
                        
                        for event in events:
                            try:
                                # Esd = Event Start Date
                                start_date = event.get('Esd', '')
                                wib = parse_livescore_date(start_date)

                                # T1 = Tim Home (List of objects)
                                t1_data = event.get('T1', [{}])[0]
                                home_name = t1_data.get('Nm', 'Unknown')
                                home_logo = get_logo(t1_data)

                                # T2 = Tim Away
                                t2_data = event.get('T2', [{}])[0]
                                away_name = t2_data.get('Nm', 'Unknown')
                                away_logo = get_logo(t2_data)

                                # Skor (Tr1 = Team Runs 1, Tr2 = Team Runs 2)
                                score_home = event.get('Tr1', '0')
                                score_away = event.get('Tr2', '0')
                                
                                # Status (Eps = Event Process Status)
                                status_raw = event.get('Eps', '')
                                status_text = status_raw
                                
                                # Terjemahkan kode status
                                if status_raw == "NS": 
                                    status_text = "Jadwal"
                                    score_home = "-" # Kosongkan skor jika belum main
                                    score_away = "-"
                                elif status_raw == "FT": 
                                    status_text = "Selesai"
                                elif status_raw == "HT": 
                                    status_text = "HT"
                                elif status_raw == "Postp.": 
                                    status_text = "Tunda"
                                else:
                                    # Biasanya angka menit (e.g., "45") atau "AET"
                                    status_text = f"Live {status_raw}'"

                                # Link (Eid = Event ID)
                                event_id = event.get('Eid', '')
                                if event_id:
                                    match_link = f"https://www.livescore.com/id/sepak-bola/match/{event_id}/"
                                else:
                                    match_link = url

                                item = {
                                    "league_name": full_league,
                                    "league_logo": "https://www.livescore.com/ls-web-assets/images/live-score-outlined-74d06.webp", # Placeholder
                                    "match_date": wib['date'],
                                    "match_time": wib['time'],
                                    "status": status_text,
                                    "home_team": home_name,
                                    "home_logo": home_logo,
                                    "home_score": score_home,
                                    "away_team": away_name,
                                    "away_logo": away_logo,
                                    "away_score": score_away,
                                    "link": match_link,
                                    "sort_ts": wib['ts']
                                }
                                clean_matches.append(item)

                            except:
                                continue
                    except:
                        continue
                
                # Sorting: Waktu -> Liga
                clean_matches.sort(key=lambda x: (x['sort_ts'], x['league_name']))
                
                # Hapus helper
                for m in clean_matches:
                    del m['sort_ts']

                # Simpan
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ SUKSES! {len(clean_matches)} pertandingan valid tersimpan.")
            
            else:
                print("❌ Gagal: Data 'Stages' tidak ditemukan di JSON (Struktur mungkin berubah).")
                # Debugging: Uncomment baris di bawah untuk melihat struktur JSON jika gagal
                # print(json.dumps(raw_data, indent=2)[:1000]) 

        except Exception as e:
            print(f"❌ Error Fatal: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
