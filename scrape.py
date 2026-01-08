import json
import os
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

def clean_text(text):
    """Membersihkan teks dari spasi berlebih/newline."""
    if not text: return ""
    return " ".join(text.split())

def parse_flashscore_time(time_str):
    """Mencoba parse waktu dari Flashscore."""
    # Contoh input: "21:30", "Selesai", "45+'", "Tunda"
    try:
        now = datetime.now(WIB)
        
        # Jika format jam (Jadwal)
        if ":" in time_str and len(time_str) <= 5:
            hour, minute = map(int, time_str.split(":"))
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return {
                "date": dt.strftime("%Y-%m-%d"),
                "time": time_str,
                "ts": dt.timestamp(),
                "status": "Jadwal"
            }
        
        # Jika sedang main (angka menit) atau status lain
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"), # Waktu saat ini
            "ts": now.timestamp(),
            "status": time_str # Live 25', HT, FT
        }
    except:
        return {"date": "TBD", "time": "TBD", "ts": 0, "status": time_str}

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper Flashscore...")
        
        # Headless=True WAJIB untuk GitHub Actions
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            url = "https://www.flashscore.co.id/sepak-bola/"
            print(f"🌍 Mengakses {url}...")
            
            page.goto(url, wait_until="networkidle", timeout=90000)
            
            # 1. Tunggu elemen pertandingan muncul
            print("⏳ Menunggu data dimuat...")
            try:
                # Kita tunggu header liga atau match muncul
                page.wait_for_selector(".leagues--live", timeout=20000)
            except:
                print("⚠️ Timeout menunggu .leagues--live, mencoba lanjut...")

            # 2. Ambil semua elemen Baris (Header Liga & Pertandingan)
            # Flashscore menaruh Header Liga dan Pertandingan sejajar dalam satu container
            # Kita akan loop satu per satu.
            
            # Selector CSS pintar: Ambil elemen yang kelasnya mengandung kata kunci tertentu
            # Ini untuk menghindari kode acak (hash) di belakang nama kelas
            rows = page.locator(".leagues--live > div").all()
            
            print(f"🔍 Ditemukan {len(rows)} baris elemen (Liga + Match). Memproses...")

            clean_matches = []
            current_league_info = {
                "name": "Unknown League",
                "country": "",
                "logo": ""
            }

            for row in rows:
                try:
                    class_attr = row.get_attribute("class") or ""
                    
                    # --- KASUS 1: INI ADALAH HEADER LIGA ---
                    if "headerLeague" in class_attr:
                        # Reset info liga saat ini
                        try:
                            # Nama Liga (Contoh: Piala Asia AFC U23)
                            league_el = row.locator("[class*='headerLeague__title-text']").first
                            league_name = league_el.text_content() if league_el.count() > 0 else ""
                            
                            # Negara/Kategori (Contoh: ASIA)
                            cat_el = row.locator("[class*='headerLeague__category-text']").first
                            category_name = cat_el.text_content() if cat_el.count() > 0 else ""
                            
                            # Gabungkan
                            full_name = f"{category_name}: {league_name}" if category_name else league_name
                            
                            current_league_info = {
                                "name": full_name,
                                "logo": "https://www.flashscore.co.id/res/image/data/13_symbols/soccer.svg" # Default Flashscore icon
                            }
                        except Exception as e:
                            print(f"⚠️ Error parsing header: {e}")
                            continue

                    # --- KASUS 2: INI ADALAH PERTANDINGAN ---
                    elif "event__match" in class_attr:
                        try:
                            # Link ID (Penting untuk unicity)
                            match_id = row.get_attribute("id") # format: g_1_KvC7CPR1
                            
                            # Waktu / Status
                            # Bisa berupa jam (21:30) atau status (25', Selesai)
                            time_el = row.locator(".event__time").first
                            stage_el = row.locator(".event__stage--block").first
                            
                            raw_time = ""
                            if stage_el.count() > 0:
                                raw_time = stage_el.text_content() # Sedang main atau selesai/tunda
                            elif time_el.count() > 0:
                                raw_time = time_el.text_content() # Jadwal
                            else:
                                # Kadang status FT ada di elemen lain jika struktur beda
                                raw_time = "TBD"

                            wib_data = parse_flashscore_time(clean_text(raw_time))

                            # Tim Home
                            # Gunakan selector *= untuk mencari kelas yang "mengandung" kata tertentu
                            home_el = row.locator("[class*='event__homeParticipant']").first
                            home_name = clean_text(home_el.text_content())
                            home_img = home_el.locator("img").get_attribute("src") if home_el.locator("img").count() > 0 else ""

                            # Tim Away
                            away_el = row.locator("[class*='event__awayParticipant']").first
                            away_name = clean_text(away_el.text_content())
                            away_img = away_el.locator("img").get_attribute("src") if away_el.locator("img").count() > 0 else ""

                            # Skor (Jika ada)
                            score_home_el = row.locator("[class*='event__score--home']").first
                            score_away_el = row.locator("[class*='event__score--away']").first
                            
                            score_home = score_home_el.text_content() if score_home_el.count() > 0 else "-"
                            score_away = score_away_el.text_content() if score_away_el.count() > 0 else "-"

                            # Validasi data minimal
                            if not home_name or not away_name: continue

                            match_data = {
                                "league_name": current_league_info['name'],
                                "league_logo": current_league_info['logo'],
                                "match_date": wib_data['date'],
                                "match_time": wib_data['time'],
                                "status": wib_data['status'],
                                "home_team": home_name,
                                "home_logo": home_img,
                                "home_score": score_home,
                                "away_team": away_name,
                                "away_logo": away_img,
                                "away_score": score_away,
                                "link": f"https://www.flashscore.co.id/pertandingan/{match_id.replace('g_1_', '')}" if match_id else ""
                            }
                            clean_matches.append(match_data)

                        except Exception as e:
                            # print(f"Skip row error: {e}") 
                            continue

                except Exception as e:
                    continue

            # Sorting
            clean_matches.sort(key=lambda x: (x['league_name'], x['match_time']))

            # Simpan
            if clean_matches:
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ BERHASIL! {len(clean_matches)} pertandingan dari Flashscore tersimpan.")
            else:
                print("❌ Tidak ada data pertandingan yang terekstrak. Cek selector.")

        except Exception as e:
            print(f"❌ Error Fatal: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
