import json
import os
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

def parse_iso_date(iso_date_str):
    """Mengubah format waktu ISO Goal.com ke WIB."""
    try:
        if not iso_date_str: return {"date": "TBD", "time": "TBD", "ts": 0}
        # Format Goal.com biasanya: "2026-01-07T19:30:00.000Z"
        dt_utc = datetime.fromisoformat(iso_date_str.replace("Z", "+00:00"))
        dt_wib = dt_utc.astimezone(WIB)
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M"),
            "ts": dt_wib.timestamp()
        }
    except Exception as e:
        return {"date": "TBD", "time": "TBD", "ts": 0}

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper Goal.com...")
        
        # Headless=True WAJIB untuk GitHub Actions
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            url = "https://www.goal.com/id/livescore"
            print(f"🌍 Mengakses {url}...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # --- EKSTRAKSI DATA NEXT.JS ---
            # Kita langsung tembak script JSON-nya, tidak perlu scraping elemen visual
            print("📦 Mengekstrak data JSON internal (__NEXT_DATA__)...")
            json_str = page.locator("#__NEXT_DATA__").text_content()
            
            clean_matches = []
            
            if json_str:
                raw_data = json.loads(json_str)
                
                # Navigasi ke lokasi data livescore berdasarkan struktur JSON Goal.com
                # Path: props -> pageProps -> page -> content -> liveScores
                try:
                    live_scores_list = raw_data['props']['pageProps']['page']['content']['liveScores']
                except KeyError:
                    live_scores_list = []
                    print("⚠️ Struktur JSON berubah atau data kosong.")

                print(f"🔍 Menemukan {len(live_scores_list)} kategori kompetisi.")

                for competition_group in live_scores_list:
                    try:
                        # Ambil Info Liga
                        comp_info = competition_group.get('competition', {})
                        area_name = comp_info.get('area', {}).get('name', '')
                        league_name_raw = comp_info.get('name', '')
                        
                        # Gabungkan Area + Liga (Contoh: "Inggris Raya - Premier League")
                        full_league_name = f"{area_name} - {league_name_raw}" if area_name else league_name_raw
                        league_logo = comp_info.get('image', {}).get('url', '')

                        # Loop setiap pertandingan di liga ini
                        matches = competition_group.get('matches', [])
                        for m in matches:
                            try:
                                # Data Tim
                                team_a = m.get('teamA', {})
                                team_b = m.get('teamB', {})
                                
                                # Skor & Status
                                score_data = m.get('score', {})
                                status = m.get('status', '') # RESULT, LIVE, FIXTURE
                                period_data = m.get('period', {})
                                
                                # Logika Skor
                                # Jika belum main, score biasanya null atau tidak ada key-nya
                                score_home = score_data.get('teamA', 0) if score_data else 0
                                score_away = score_data.get('teamB', 0) if score_data else 0
                                
                                # Logika Waktu Pertandingan (Menit berjalan jika LIVE)
                                match_status_text = status
                                if status == "LIVE" and period_data:
                                    minute = period_data.get('minute', '')
                                    match_status_text = f"Live {minute}'"
                                elif status == "RESULT":
                                    match_status_text = "FT" # Full Time
                                elif status == "FIXTURE":
                                    match_status_text = "Jadwal"

                                # Waktu Kickoff
                                start_date = m.get('startDate', '')
                                wib = parse_iso_date(start_date)

                                item = {
                                    "league_name": full_league_name,
                                    "league_logo": league_logo,
                                    "match_date": wib['date'],
                                    "match_time": wib['time'],
                                    "status": match_status_text,
                                    "home_team": team_a.get('name', 'Unknown'),
                                    "home_logo": team_a.get('image', {}).get('url', ''),
                                    "home_score": score_home,
                                    "away_team": team_b.get('name', 'Unknown'),
                                    "away_logo": team_b.get('image', {}).get('url', ''),
                                    "away_score": score_away,
                                    "sort_ts": wib['ts'] # Helper sorting
                                }
                                clean_matches.append(item)
                                
                            except Exception as e:
                                continue # Skip match yang error
                                
                    except Exception as e:
                        continue # Skip kompetisi yang error

                # Sorting: Tanggal -> Jam -> Liga
                clean_matches.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
                
                # Hapus helper sorting
                for match in clean_matches:
                    del match['sort_ts']

                # Simpan
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ BERHASIL! {len(clean_matches)} pertandingan tersimpan.")
                
            else:
                print("❌ Gagal: Tag __NEXT_DATA__ tidak ditemukan.")

        except Exception as e:
            print(f"❌ Error: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
