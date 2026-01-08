import json
import os
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# --- KONFIGURASI ---
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "jadwal_bola_final.json")
WIB = timezone(timedelta(hours=7))

def clean_text(text):
    if not text: return ""
    return " ".join(text.split())

def parse_flashscore_time(time_str):
    """Mencoba parse waktu/status."""
    try:
        now = datetime.now(WIB)
        # Jika format jam (Jadwal), misal "21:30"
        if ":" in time_str and len(time_str) <= 5:
            hour, minute = map(int, time_str.split(":"))
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return {
                "date": dt.strftime("%Y-%m-%d"),
                "time": time_str,
                "ts": dt.timestamp(),
                "status": "Jadwal"
            }
        # Jika status lain (Selesai, 45+, Tunda)
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "ts": now.timestamp(),
            "status": time_str
        }
    except:
        return {"date": "TBD", "time": "TBD", "ts": 0, "status": time_str}

def run():
    with sync_playwright() as p:
        print("🚀 Memulai Scraper Flashscore (Fix Level Kedalaman)...")
        
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            url = "https://www.flashscore.co.id/sepak-bola/"
            print(f"🌍 Mengakses {url}...")
            
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 1. Tunggu sampai ada setidaknya satu pertandingan (id dimulai dengan g_1_)
            print("⏳ Menunggu elemen pertandingan muncul...")
            try:
                page.wait_for_selector("[id^='g_1_']", timeout=20000)
            except:
                print("⚠️ Waktu tunggu habis, mencoba memproses data yang ada...")

            # 2. SELEKTOR BARU YANG LEBIH CERDAS
            # Kita mengambil elemen Header Liga DAN Elemen Pertandingan sekaligus secara berurutan.
            # Berdasarkan HTML Anda: Mereka adalah anak langsung dari .sportName.soccer
            
            print("📦 Mengambil baris data...")
            
            # Locator ini mengambil semua DIV di dalam container utama
            rows = page.locator(".sportName.soccer > div").all()
            
            print(f"🔍 Ditemukan {len(rows)} baris total (Header + Match).")

            clean_matches = []
            current_league_info = {
                "name": "Lainnya",
                "logo": "https://www.flashscore.co.id/res/image/data/13_symbols/soccer.svg"
            }

            for row in rows:
                try:
                    # Ambil atribut class dan ID untuk identifikasi jenis baris
                    class_attr = row.get_attribute("class") or ""
                    row_id = row.get_attribute("id") or ""

                    # --- KASUS 1: INI HEADER LIGA ---
                    # Ciri: class mengandung 'headerLeague__wrapper'
                    if "headerLeague__wrapper" in class_attr:
                        try:
                            # Ambil Nama Liga
                            league_el = row.locator("[class*='headerLeague__title-text']")
                            cat_el = row.locator("[class*='headerLeague__category-text']")
                            
                            l_name = clean_text(league_el.text_content()) if league_el.count() else ""
                            c_name = clean_text(cat_el.text_content()) if cat_el.count() else ""
                            
                            full_name = f"{c_name}: {l_name}" if c_name else l_name
                            
                            if full_name:
                                current_league_info = {
                                    "name": full_name,
                                    "logo": "https://www.flashscore.co.id/res/image/data/13_symbols/soccer.svg"
                                }
                        except:
                            continue

                    # --- KASUS 2: INI PERTANDINGAN ---
                    # Ciri: ID dimulai dengan 'g_1_' (g_1_KvC7CPR1)
                    elif row_id.startswith("g_1_"):
                        try:
                            # Status/Waktu
                            # Cek apakah sedang Live, Selesai, atau Jadwal
                            stage_block = row.locator(".event__stage--block")
                            time_el = row.locator(".event__time")
                            
                            raw_status = ""
                            if stage_block.count() > 0:
                                raw_status = clean_text(stage_block.text_content()) # 25', Selesai
                            elif time_el.count() > 0:
                                raw_status = clean_text(time_el.text_content()) # 21:30
                            else:
                                # Kadang status FT ada di class hidden, kita anggap selesai jika ada skor
                                raw_status = "FT" 

                            wib = parse_flashscore_time(raw_status)

                            # Tim Home
                            home_el = row.locator(".event__homeParticipant")
                            home_name = clean_text(home_el.text_content())
                            home_img_el = home_el.locator("img")
                            home_logo = home_img_el.get_attribute("src") if home_img_el.count() else ""

                            # Tim Away
                            away_el = row.locator(".event__awayParticipant")
                            away_name = clean_text(away_el.text_content())
                            away_img_el = away_el.locator("img")
                            away_logo = away_img_el.get_attribute("src") if away_img_el.count() else ""

                            # Skor
                            score_home_el = row.locator(".event__score--home")
                            score_away_el = row.locator(".event__score--away")
                            
                            s_home = score_home_el.text_content() if score_home_el.count() else "-"
                            s_away = score_away_el.text_content() if score_away_el.count() else "-"

                            # Link
                            match_link = f"https://www.flashscore.co.id/pertandingan/{row_id.replace('g_1_', '')}"

                            # Validasi: Nama tim harus ada
                            if not home_name or not away_name: continue

                            match_data = {
                                "league_name": current_league_info['name'],
                                "league_logo": current_league_info['logo'],
                                "match_date": wib['date'],
                                "match_time": wib['time'],
                                "status": wib['status'],
                                "home_team": home_name,
                                "home_logo": home_logo,
                                "home_score": s_home,
                                "away_team": away_name,
                                "away_logo": away_logo,
                                "away_score": s_away,
                                "link": match_link
                            }
                            clean_matches.append(match_data)

                        except Exception as e:
                            # print(f"Skip match error: {e}")
                            continue

                except Exception as e:
                    continue

            # Sorting: Liga -> Waktu
            clean_matches.sort(key=lambda x: (x['league_name'], x['match_time']))

            # Simpan
            if clean_matches:
                if not os.path.exists(OUTPUT_DIR):
                    os.makedirs(OUTPUT_DIR)
                    
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_matches, f, indent=2, ensure_ascii=False)
                    
                print(f"✅ BERHASIL! {len(clean_matches)} pertandingan tersimpan.")
            else:
                print("❌ Gagal: Tidak ada data yang terekstrak (List kosong).")
                # Debugging: Cetak HTML container jika gagal untuk analisis
                # try:
                #     print(page.locator(".sportName.soccer").inner_html()[:500])
                # except: pass

        except Exception as e:
            print(f"❌ Error Fatal: {e}")
        
        browser.close()

if __name__ == "__main__":
    run()
