import json
import os
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

def get_high_res_image(url):
    """Mengubah URL thumbnail menjadi HD (128px)."""
    if not url: return ""
    try:
        import re
        new_url = re.sub(r'w=\d+', 'w=128', url)
        new_url = re.sub(r'h=\d+', 'h=128', new_url)
        return new_url
    except:
        return url

def parse_iso_date_to_wib(iso_date_str):
    """Ubah waktu ISO UTC ke WIB."""
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
    Mendeteksi pola: objek yang punya 'homeTeam' DAN 'kickoff'.
    """
    if isinstance(data, dict):
        # Cek apakah ini adalah sebuah pertandingan (Match Object)
        if 'homeTeam' in data and 'awayTeam' in data and 'kickoff' in data:
            matches_found.append(data)
        
        # Cek apakah ini container yang punya list matchCards
        elif 'matchCards' in data and isinstance(data['matchCards'], list):
            # Kita simpan info liganya di setiap match card anak-anaknya agar tidak hilang
            header = data.get('sectionHeader', {})
            league_info = {
                'name': header.get('title', ''),
                'round': header.get('subtitle', ''),
                'logo': header.get('entityLogo', {}).get('path', '')
            }
            
            for card in data['matchCards']:
                if isinstance(card, dict):
                    # Suntikkan info liga ke dalam card agar terbawa
                    if 'league_info' not in card: 
                        card['league_info'] = league_info
                    find_matches_in_json(card, matches_found)

        # Lanjutkan pencarian ke anak-anaknya
        for k, v in data.items():
            find_matches_in_json(v, matches_found)
            
    elif isinstance(data, list):
        for item in data:
            find_matches_in_json(item, matches_found)

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper OneFootball (Metode Deep Search)...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://onefootball.com/id/pertandingan", wait_until="domcontentloaded", timeout=60000)
            
            # Ambil data JSON __NEXT_DATA__
            print("📦 Mengekstrak data internal...")
            json_str = page.locator("#__NEXT_DATA__").text_content()
            
            if json_str:
                raw_data = json.loads(json_str)
                raw_matches = []
                
                # JALANKAN PENCARIAN REKURSIF
                find_matches_in_json(raw_data, raw_matches)
                print(f"🔍 Ditemukan total {len(raw_matches)} objek pertandingan mentah.")

                clean_matches = []
                seen_links = set()

                for m in raw_matches:
                    try:
                        # Filter Duplikat
                        link = "https://onefootball.com" + m.get('link', '')
                        if link in seen_links: continue
                        seen_links.add(link)

                        # Parse Waktu
                        kickoff = m.get('kickoff', '')
                        wib = parse_iso_date_to_wib(kickoff)

                        # Ambil Info Liga (jika ada yang disuntikkan tadi)
                        # Jika tidak ada (misal dari matchScore), pakai default atau cari di objek parent
                        league_meta = m.get('league_info', {})
                        league_name = league_meta.get('name', 'Unknown/Highlight')
                        # Coba fallback ambil competitionName dari match object langsung
                        if not league_name or league_name == 'Unknown/Highlight':
                             league_name = m.get('competitionName', 'Kompetisi Lain')

                        league_round = league_meta.get('round', '')
                        league_logo = get_high_res_image(league_meta.get('logo', ''))
                        
                        # Jika logo liga kosong, coba cari ikon kompetisi default
                        if not league_logo:
                             league_logo = "https://images.onefootball.com/icons/leagueColoredCompetition/128/13.png" # Placeholder/Default

                        # Parse Tim
                        home = m.get('homeTeam', {})
                        away = m.get('awayTeam', {})
                        
                        item = {
                            "league_name": league_name,
                            "league_round": league_round,
                            "league_logo": league_logo,
                            "match_date": wib['date'],
                            "match_time": wib['time'],
                            "sort_ts": wib['ts'], # Helper untuk sorting
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

                # Sorting Final: Tanggal -> Jam -> Liga
                clean_matches.sort(key=lambda x: (x['match_date'], x['match_time'], x['league_name']))
                
                # Hapus helper sorting
                for match in clean_matches:
                    del match['sort_ts']

                # Simpan
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ BERHASIL! {len(clean_matches)} pertandingan valid tersimpan.")
                
            else:
                print("❌ Gagal: Tag __NEXT_DATA__ tidak ditemukan.")

        except Exception as e:
            print(f"❌ Error: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
