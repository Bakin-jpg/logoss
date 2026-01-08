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
        dt_utc = datetime.fromisoformat(iso_date_str.replace("Z", "+00:00"))
        dt_wib = dt_utc.astimezone(WIB)
        return {
            "date": dt_wib.strftime("%Y-%m-%d"),
            "time": dt_wib.strftime("%H:%M"),
            "ts": dt_wib.timestamp()
        }
    except:
        return {"date": "TBD", "time": "TBD", "ts": 0}

def find_key_in_json(data, target_key):
    """
    Mencari value dari key tertentu di kedalaman JSON manapun.
    Fungsi ini akan mencari 'liveScores' dimanapun dia bersembunyi.
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
        print("🚀 Memulai Scraper Goal.com (Mode Deep Search)...")
        
        # Headless=True WAJIB untuk GitHub Actions
        browser = p.chromium.launch(headless=True)
        
        # Gunakan User Agent Desktop Chrome biasa agar dianggap manusia
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            url = "https://www.goal.com/id/livescore"
            print(f"🌍 Mengakses {url}...")
            
            # Tambahkan timeout lebih lama
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            print("📦 Mengekstrak data JSON internal (__NEXT_DATA__)...")
            try:
                json_str = page.locator("#__NEXT_DATA__").text_content()
            except:
                print("❌ Elemen #__NEXT_DATA__ tidak ditemukan.")
                json_str = None

            clean_matches = []
            
            if json_str:
                raw_data = json.loads(json_str)
                
                # --- LOGIKA BARU: PENCARIAN REKURSIF ---
                # Cari list 'liveScores' di mana saja
                print("🔍 Melakukan Deep Search untuk mencari 'liveScores'...")
                live_scores_list = find_key_in_json(raw_data, 'liveScores')

                if not live_scores_list:
                    print("⚠️ Key 'liveScores' tidak ditemukan, mencoba mencari 'matches' langsung...")
                    # Fallback: Mungkin strukturnya beda lagi, kita cari pattern kompetisi manual jika perlu
                    # Tapi biasanya liveScores pasti ada di Goal.com
                    
                if live_scores_list:
                    print(f"✅ Ditemukan {len(live_scores_list)} grup kompetisi.")
                    
                    for competition_group in live_scores_list:
                        try:
                            # Ambil Info Liga
                            comp_info = competition_group.get('competition', {})
                            area_name = comp_info.get('area', {}).get('name', '')
                            league_name_raw = comp_info.get('name', '')
                            full_league_name = f"{area_name} - {league_name_raw}" if area_name else league_name_raw
                            league_logo = comp_info.get('image', {}).get('url', '')

                            # Loop Matches
                            matches = competition_group.get('matches', [])
                            for m in matches:
                                try:
                                    team_a = m.get('teamA', {})
                                    team_b = m.get('teamB', {})
                                    score_data = m.get('score', {})
                                    status = m.get('status', '')
                                    period_data = m.get('period', {})

                                    # Skor
                                    score_home = score_data.get('teamA', 0) if score_data else 0
                                    score_away = score_data.get('teamB', 0) if score_data else 0

                                    # Status Text
                                    match_status_text = status
                                    if status == "LIVE":
                                        minute = period_data.get('minute', '') if period_data else ''
                                        match_status_text = f"Live {minute}'"
                                    elif status == "RESULT":
                                        match_status_text = "FT"
                                    elif status == "FIXTURE":
                                        match_status_text = "Jadwal"

                                    # Waktu
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
                                        "sort_ts": wib['ts']
                                    }
                                    clean_matches.append(item)
                                except:
                                    continue
                        except:
                            continue
                else:
                    print("❌ Gagal: Data 'liveScores' benar-benar kosong atau struktur berubah total.")

                # Sorting Final
                if clean_matches:
                    clean_matches.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
                    for match in clean_matches:
                        del match['sort_ts']

                    if not os.path.exists(OUTPUT_DIR):
                        os.makedirs(OUTPUT_DIR)

                    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                        json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                    print(f"✅ SUKSES BESAR! {len(clean_matches)} pertandingan tersimpan.")
                else:
                    print("⚠️ Tidak ada data pertandingan yang bisa diproses.")

            else:
                print("❌ JSON String kosong.")

        except Exception as e:
            print(f"❌ Error Fatal: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
