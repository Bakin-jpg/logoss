import json
import os
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

# Base URL untuk gambar di LiveScore (biasanya statis)
IMG_BASE_URL = "https://lsm-static-prod.livescore.com/medium/"

def parse_livescore_date(date_str):
    """
    LiveScore format: YYYYMMDDHHmmss (String) -> Contoh: 20260108213000
    """
    try:
        if not date_str: return {"date": "TBD", "time": "TBD", "ts": 0}
        
        # Parse format YYYYMMDDHHmmss (UTC)
        dt_utc = datetime.strptime(str(date_str), "%Y%m%d%H%M%S")
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        
        # Convert ke WIB
        dt_wib = dt_utc.astimezone(WIB)
        
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M"),
            "ts": dt_wib.timestamp()
        }
    except Exception as e:
        return {"date": "TBD", "time": "TBD", "ts": 0}

def get_logo(team_data):
    """Menyusun URL logo dari hash gambar LiveScore."""
    try:
        img_id = team_data.get('Img', '')
        if img_id:
            return f"{IMG_BASE_URL}{img_id}.png"
        return ""
    except:
        return ""

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper LiveScore.com...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            url = "https://www.livescore.com/id/"
            print(f"🌍 Mengakses {url}...")
            
            # LiveScore sangat cepat, networkidle biasanya cukup
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            print("📦 Mengekstrak __NEXT_DATA__...")
            
            try:
                # Ambil JSON mentah dari script tag
                json_str = page.locator("#__NEXT_DATA__").text_content()
                raw_data = json.loads(json_str)
                
                # Navigasi ke data sepak bola
                # Struktur LiveScore: props -> pageProps -> initialState -> football -> stages
                initial_state = raw_data.get('props', {}).get('pageProps', {}).get('initialState', {})
                
                # Kadang ada di 'football', kadang tergantung halaman
                modules = initial_state.get('football', {}) or initial_state.get('modules', {}).get('football', {})
                stages = modules.get('stages', [])

                print(f"🔍 Ditemukan {len(stages)} kompetisi/liga.")
                
                clean_matches = []

                for stage in stages:
                    try:
                        # Info Liga
                        country_name = stage.get('Cnm', '') # Country Name
                        league_name = stage.get('Snm', '')  # Stage Name (League)
                        full_league = f"{country_name} - {league_name}" if country_name else league_name
                        
                        # ID liga untuk logo (LiveScore tidak selalu kasih URL logo liga di sini, kita pakai default)
                        league_logo = "https://www.livescore.com/ls-web-assets/images/live-score-outlined-74d06.webp" # Default

                        # Loop Pertandingan (Events)
                        events = stage.get('Events', [])
                        for event in events:
                            try:
                                # Parsing Waktu (Esd = Event Start Date)
                                start_date = event.get('Esd', '')
                                wib = parse_livescore_date(start_date)

                                # Tim 1 (Home)
                                t1 = event.get('T1', [{}])[0]
                                home_name = t1.get('Nm', 'Unknown')
                                home_logo = get_logo(t1)

                                # Tim 2 (Away)
                                t2 = event.get('T2', [{}])[0]
                                away_name = t2.get('Nm', 'Unknown')
                                away_logo = get_logo(t2)

                                # Skor (Tr1 = Team Runs 1 / Goals)
                                score_home = event.get('Tr1', '0')
                                score_away = event.get('Tr2', '0')
                                
                                # Status (Eps = Event Process Status)
                                # NS=Not Started, HT=Half Time, FT=Full Time, angka=menit
                                status_raw = event.get('Eps', '')
                                status_text = status_raw
                                if status_raw == "NS": status_text = "Jadwal"
                                elif status_raw == "FT": status_text = "FT"
                                elif status_raw == "Postp.": status_text = "Tunda"
                                else: status_text = f"Live {status_raw}" # Misal: Live 45'

                                # Link Detail (Eid = Event ID)
                                # URL Pattern: /id/sepak-bola/{country}/{league}/{home}-vs-away/{id}/
                                event_id = event.get('Eid', '')
                                event_url = event.get('Eurl', '') # Kadang ada Eurl langsung
                                if not event_url and event_id:
                                     # Buat link sederhana jika Eurl tidak ada
                                     match_link = f"https://www.livescore.com/id/sepak-bola/match/{event_id}/"
                                else:
                                     match_link = f"https://www.livescore.com{event_url}" if event_url else ""

                                # Filter jika belum ada score (opsional, tapi biar data rapi, set 0 jika kosong/NS)
                                if status_raw == "NS":
                                    score_home = "-"
                                    score_away = "-"

                                item = {
                                    "league_name": full_league,
                                    "league_logo": league_logo,
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

                            except Exception as e:
                                continue

                    except Exception as e:
                        continue
                
                # Sorting
                clean_matches.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
                
                # Cleanup
                for m in clean_matches:
                    del m['sort_ts']

                # Save
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ BERHASIL! {len(clean_matches)} pertandingan dari LiveScore tersimpan.")

            except Exception as e:
                print(f"❌ Gagal parsing JSON: {e}")

        except Exception as e:
            print(f"❌ Error Fatal: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
